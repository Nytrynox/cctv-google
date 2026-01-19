"""
Alert System - Sends real-time mobile alerts via Firebase Cloud Messaging.
Also supports webhooks and other notification channels.
"""
import asyncio
import json
from datetime import datetime
from typing import List, Optional, Dict, Any
import structlog
import httpx
import firebase_admin
from firebase_admin import credentials, messaging

from .config import settings
from .models import Alert, AlertSeverity, AlertStatus

logger = structlog.get_logger(__name__)


class FirebaseAlertSender:
    """Send mobile push notifications via Firebase Cloud Messaging."""
    
    def __init__(self):
        self.logger = logger.bind(component="FirebaseAlertSender")
        self._initialized = False
        self._initialize_firebase()
    
    def _initialize_firebase(self):
        """Initialize Firebase Admin SDK."""
        if self._initialized:
            return
            
        try:
            if settings.firebase_credentials_path:
                cred = credentials.Certificate(settings.firebase_credentials_path)
                firebase_admin.initialize_app(cred)
                self._initialized = True
                self.logger.info("Firebase initialized successfully")
            else:
                self.logger.warning("Firebase credentials not configured")
        except Exception as e:
            self.logger.error("Failed to initialize Firebase", error=str(e))
    
    async def send_alert(
        self,
        alert: Alert,
        device_tokens: List[str]
    ) -> Dict[str, Any]:
        """
        Send push notification to mobile devices.
        
        Args:
            alert: The alert to send
            device_tokens: List of FCM device tokens
            
        Returns:
            Dictionary with success/failure status for each token
        """
        if not self._initialized:
            self.logger.error("Firebase not initialized")
            return {"error": "Firebase not initialized"}
        
        if not device_tokens:
            return {"error": "No device tokens provided"}
        
        # Build notification payload
        notification = messaging.Notification(
            title=self._get_notification_title(alert),
            body=alert.description[:200],  # Truncate for push notification
            image=alert.thumbnail_url
        )
        
        # Build data payload for app handling
        data = {
            "alert_id": alert.alert_id,
            "camera_id": alert.camera_id,
            "task_id": alert.task_id,
            "severity": alert.severity.value,
            "location": alert.location,
            "timestamp": alert.timestamp.isoformat(),
            "video_url": alert.video_clip_url or "",
            "click_action": "OPEN_ALERT_DETAIL"
        }
        
        # Android-specific configuration
        android_config = messaging.AndroidConfig(
            priority="high",
            notification=messaging.AndroidNotification(
                icon="ic_security_alert",
                color=self._get_severity_color(alert.severity),
                sound="alert_sound",
                channel_id="security_alerts",
                click_action="OPEN_ALERT_DETAIL"
            )
        )
        
        # iOS-specific configuration
        apns_config = messaging.APNSConfig(
            payload=messaging.APNSPayload(
                aps=messaging.Aps(
                    alert=messaging.ApsAlert(
                        title=self._get_notification_title(alert),
                        body=alert.description[:200]
                    ),
                    badge=1,
                    sound="alert_sound.wav",
                    category="SECURITY_ALERT"
                )
            )
        )
        
        results = {"success": [], "failure": []}
        
        # Send to each device
        for token in device_tokens:
            try:
                message = messaging.Message(
                    notification=notification,
                    data=data,
                    android=android_config,
                    apns=apns_config,
                    token=token
                )
                
                # Send message
                response = await asyncio.to_thread(
                    messaging.send, message
                )
                
                results["success"].append({
                    "token": token[:20] + "...",
                    "message_id": response
                })
                
            except messaging.UnregisteredError:
                results["failure"].append({
                    "token": token[:20] + "...",
                    "error": "Device token unregistered"
                })
            except Exception as e:
                results["failure"].append({
                    "token": token[:20] + "...",
                    "error": str(e)
                })
        
        self.logger.info(
            "Push notifications sent",
            alert_id=alert.alert_id,
            success_count=len(results["success"]),
            failure_count=len(results["failure"])
        )
        
        return results
    
    async def send_to_topic(self, alert: Alert, topic: str) -> Optional[str]:
        """Send alert to a topic (for broadcast notifications)."""
        if not self._initialized:
            return None
        
        message = messaging.Message(
            notification=messaging.Notification(
                title=self._get_notification_title(alert),
                body=alert.description[:200]
            ),
            data={
                "alert_id": alert.alert_id,
                "severity": alert.severity.value,
                "video_url": alert.video_clip_url or ""
            },
            topic=topic
        )
        
        try:
            response = await asyncio.to_thread(messaging.send, message)
            self.logger.info("Topic message sent", topic=topic, message_id=response)
            return response
        except Exception as e:
            self.logger.error("Failed to send topic message", error=str(e))
            return None
    
    def _get_notification_title(self, alert: Alert) -> str:
        """Generate notification title based on severity."""
        severity_prefix = {
            AlertSeverity.LOW: "ℹ️",
            AlertSeverity.MEDIUM: "⚠️",
            AlertSeverity.HIGH: "🚨",
            AlertSeverity.CRITICAL: "🔴 CRITICAL:"
        }
        prefix = severity_prefix.get(alert.severity, "")
        return f"{prefix} {alert.title}"
    
    def _get_severity_color(self, severity: AlertSeverity) -> str:
        """Get color for Android notification based on severity."""
        colors = {
            AlertSeverity.LOW: "#4CAF50",      # Green
            AlertSeverity.MEDIUM: "#FF9800",    # Orange
            AlertSeverity.HIGH: "#F44336",      # Red
            AlertSeverity.CRITICAL: "#9C27B0"   # Purple
        }
        return colors.get(severity, "#2196F3")


class WebhookAlertSender:
    """Send alerts via webhooks (Slack, Teams, custom endpoints)."""
    
    def __init__(self):
        self.logger = logger.bind(component="WebhookAlertSender")
        self.http_client = httpx.AsyncClient(timeout=30.0)
    
    async def send_alert(
        self,
        alert: Alert,
        webhook_url: str,
        format_type: str = "generic"
    ) -> bool:
        """
        Send alert to a webhook endpoint.
        
        Args:
            alert: The alert to send
            webhook_url: The webhook URL
            format_type: Format type ('generic', 'slack', 'teams')
            
        Returns:
            True if successful
        """
        try:
            if format_type == "slack":
                payload = self._format_slack_message(alert)
            elif format_type == "teams":
                payload = self._format_teams_message(alert)
            else:
                payload = self._format_generic_message(alert)
            
            response = await self.http_client.post(
                webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code in (200, 201, 204):
                self.logger.info(
                    "Webhook alert sent",
                    alert_id=alert.alert_id,
                    webhook_url=webhook_url[:50]
                )
                return True
            else:
                self.logger.error(
                    "Webhook failed",
                    status_code=response.status_code,
                    response=response.text[:200]
                )
                return False
                
        except Exception as e:
            self.logger.error("Webhook error", error=str(e))
            return False
    
    def _format_slack_message(self, alert: Alert) -> Dict[str, Any]:
        """Format alert for Slack webhook."""
        severity_emoji = {
            AlertSeverity.LOW: ":information_source:",
            AlertSeverity.MEDIUM: ":warning:",
            AlertSeverity.HIGH: ":rotating_light:",
            AlertSeverity.CRITICAL: ":red_circle:"
        }
        
        return {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{severity_emoji.get(alert.severity, '')} Security Alert: {alert.title}"
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Location:*\n{alert.location}"},
                        {"type": "mrkdwn", "text": f"*Severity:*\n{alert.severity.value.upper()}"},
                        {"type": "mrkdwn", "text": f"*Camera:*\n{alert.camera_id}"},
                        {"type": "mrkdwn", "text": f"*Time:*\n{alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"}
                    ]
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Description:*\n{alert.description}"
                    }
                }
            ]
        }
        
        # Add video link if available
        if alert.video_clip_url:
            return {
                "blocks": [
                    *self._format_slack_message(alert)["blocks"],
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "View Video Clip"},
                                "url": alert.video_clip_url,
                                "style": "primary"
                            }
                        ]
                    }
                ]
            }
    
    def _format_teams_message(self, alert: Alert) -> Dict[str, Any]:
        """Format alert for Microsoft Teams webhook."""
        severity_colors = {
            AlertSeverity.LOW: "good",
            AlertSeverity.MEDIUM: "warning",
            AlertSeverity.HIGH: "attention",
            AlertSeverity.CRITICAL: "attention"
        }
        
        return {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": severity_colors.get(alert.severity, "0076D7"),
            "summary": f"Security Alert: {alert.title}",
            "sections": [{
                "activityTitle": f"🚨 {alert.title}",
                "activitySubtitle": f"Location: {alert.location}",
                "facts": [
                    {"name": "Severity", "value": alert.severity.value.upper()},
                    {"name": "Camera", "value": alert.camera_id},
                    {"name": "Time", "value": alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')},
                    {"name": "Confidence", "value": f"{alert.confidence:.1%}"}
                ],
                "text": alert.description
            }],
            "potentialAction": [
                {
                    "@type": "OpenUri",
                    "name": "View Video",
                    "targets": [{"os": "default", "uri": alert.video_clip_url}]
                }
            ] if alert.video_clip_url else []
        }
    
    def _format_generic_message(self, alert: Alert) -> Dict[str, Any]:
        """Format alert as generic JSON payload."""
        return {
            "alert_id": alert.alert_id,
            "title": alert.title,
            "description": alert.description,
            "severity": alert.severity.value,
            "status": alert.status.value,
            "camera_id": alert.camera_id,
            "task_id": alert.task_id,
            "task_name": alert.task_name,
            "location": alert.location,
            "confidence": alert.confidence,
            "timestamp": alert.timestamp.isoformat(),
            "video_clip_url": alert.video_clip_url,
            "thumbnail_url": alert.thumbnail_url,
            "metadata": alert.metadata
        }
    
    async def close(self):
        """Close the HTTP client."""
        await self.http_client.aclose()


class AlertManager:
    """Manages alert creation and distribution."""
    
    def __init__(self):
        self.firebase_sender = FirebaseAlertSender()
        self.webhook_sender = WebhookAlertSender()
        self.logger = logger.bind(component="AlertManager")
        
        # Alert history for deduplication and cooldown
        self.recent_alerts: Dict[str, datetime] = {}
    
    def should_send_alert(
        self,
        camera_id: str,
        task_id: str,
        cooldown_minutes: int = 5
    ) -> bool:
        """Check if alert should be sent based on cooldown."""
        key = f"{camera_id}:{task_id}"
        
        if key in self.recent_alerts:
            last_alert_time = self.recent_alerts[key]
            elapsed = (datetime.utcnow() - last_alert_time).total_seconds() / 60
            
            if elapsed < cooldown_minutes:
                self.logger.info(
                    "Alert suppressed (cooldown)",
                    camera_id=camera_id,
                    task_id=task_id,
                    minutes_remaining=cooldown_minutes - elapsed
                )
                return False
        
        return True
    
    def record_alert_sent(self, camera_id: str, task_id: str):
        """Record that an alert was sent for cooldown tracking."""
        key = f"{camera_id}:{task_id}"
        self.recent_alerts[key] = datetime.utcnow()
    
    async def send_alert(
        self,
        alert: Alert,
        device_tokens: List[str] = None,
        webhook_url: str = None,
        topic: str = None
    ) -> Dict[str, Any]:
        """
        Send alert through all configured channels.
        
        Args:
            alert: The alert to send
            device_tokens: FCM device tokens for push notifications
            webhook_url: Optional webhook URL
            topic: Optional FCM topic for broadcast
            
        Returns:
            Results from all channels
        """
        results = {
            "push_notifications": None,
            "webhook": None,
            "topic": None
        }
        
        # Send push notifications
        if device_tokens:
            results["push_notifications"] = await self.firebase_sender.send_alert(
                alert, device_tokens
            )
        
        # Send to webhook
        webhook = webhook_url or settings.alert_webhook_url
        if webhook:
            results["webhook"] = await self.webhook_sender.send_alert(
                alert, webhook
            )
        
        # Send to topic
        if topic:
            results["topic"] = await self.firebase_sender.send_to_topic(
                alert, topic
            )
        
        # Record for cooldown
        self.record_alert_sent(alert.camera_id, alert.task_id)
        
        # Update alert status
        alert.status = AlertStatus.SENT
        alert.notified_users = device_tokens or []
        
        self.logger.info(
            "Alert distributed",
            alert_id=alert.alert_id,
            results=results
        )
        
        return results
    
    async def close(self):
        """Cleanup resources."""
        await self.webhook_sender.close()
