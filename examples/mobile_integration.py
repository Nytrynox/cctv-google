"""
Mobile App Integration Example
Demonstrates how to integrate with the Video Intelligence Agent from a mobile app.
"""

# Flutter/Dart Example for Firebase Cloud Messaging integration
FLUTTER_EXAMPLE = '''
// pubspec.yaml dependencies:
// firebase_messaging: ^14.7.0
// http: ^1.1.0

import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';

class VideoIntelligenceService {
  final String baseUrl;
  final FirebaseMessaging _messaging = FirebaseMessaging.instance;
  
  VideoIntelligenceService(this.baseUrl);
  
  // Register device for push notifications
  Future<String?> registerDevice() async {
    // Request permission
    NotificationSettings settings = await _messaging.requestPermission(
      alert: true,
      badge: true,
      sound: true,
      criticalAlert: true,
    );
    
    if (settings.authorizationStatus == AuthorizationStatus.authorized) {
      // Get FCM token
      String? token = await _messaging.getToken();
      return token;
    }
    return null;
  }
  
  // Subscribe to camera alerts
  Future<void> subscribeToCamera(String cameraId) async {
    await _messaging.subscribeToTopic('camera_$cameraId');
  }
  
  // Create a monitoring task
  Future<Map<String, dynamic>> createTask({
    required String name,
    required String prompt,
    required List<String> cameraIds,
    required String deviceToken,
  }) async {
    final response = await http.post(
      Uri.parse('$baseUrl/tasks'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'name': name,
        'description': name,
        'camera_ids': cameraIds,
        'prompt': prompt,
        'severity': 'medium',
        'notify_users': [deviceToken],
        'cooldown_minutes': 5,
      }),
    );
    
    return jsonDecode(response.body);
  }
  
  // Get recent alerts
  Future<List<dynamic>> getAlerts({String? severity}) async {
    String url = '$baseUrl/alerts';
    if (severity != null) {
      url += '?severity=$severity';
    }
    
    final response = await http.get(Uri.parse(url));
    return jsonDecode(response.body);
  }
  
  // Acknowledge an alert
  Future<void> acknowledgeAlert(String alertId, String userId) async {
    await http.put(
      Uri.parse('$baseUrl/alerts/$alertId/status'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'status': 'acknowledged',
        'user_id': userId,
      }),
    );
  }
  
  // Handle incoming notifications
  void setupNotificationHandlers() {
    // Foreground messages
    FirebaseMessaging.onMessage.listen((RemoteMessage message) {
      print('Got a message in foreground!');
      print('Title: ${message.notification?.title}');
      print('Body: ${message.notification?.body}');
      
      // Extract alert data
      final data = message.data;
      final alertId = data['alert_id'];
      final videoUrl = data['video_url'];
      final severity = data['severity'];
      
      // Show local notification or update UI
    });
    
    // Background/terminated messages
    FirebaseMessaging.onMessageOpenedApp.listen((RemoteMessage message) {
      // Navigate to alert details
      final alertId = message.data['alert_id'];
      // Navigate to alert detail screen
    });
  }
}

// Usage in your app:
// 
// final service = VideoIntelligenceService('https://your-api-url');
// 
// // Register for notifications
// final token = await service.registerDevice();
// 
// // Create a monitoring task
// await service.createTask(
//   name: 'My Custom Monitor',
//   prompt: 'Alert if anyone enters after 10 PM',
//   cameraIds: ['cam-001'],
//   deviceToken: token!,
// );
// 
// // Set up notification handlers
// service.setupNotificationHandlers();
'''

# React Native Example
REACT_NATIVE_EXAMPLE = '''
// Install: npm install @react-native-firebase/messaging axios

import messaging from '@react-native-firebase/messaging';
import axios from 'axios';

const API_BASE_URL = 'https://your-api-url';

// Request notification permissions
async function requestPermissions() {
  const authStatus = await messaging().requestPermission();
  const enabled =
    authStatus === messaging.AuthorizationStatus.AUTHORIZED ||
    authStatus === messaging.AuthorizationStatus.PROVISIONAL;
    
  if (enabled) {
    const token = await messaging().getToken();
    return token;
  }
  return null;
}

// Create monitoring task
async function createMonitoringTask(name, prompt, cameraIds, deviceToken) {
  const response = await axios.post(`${API_BASE_URL}/tasks`, {
    name,
    description: name,
    camera_ids: cameraIds,
    prompt,
    severity: 'medium',
    notify_users: [deviceToken],
    cooldown_minutes: 5,
  });
  
  return response.data;
}

// Get alerts
async function getAlerts(severity = null) {
  const url = severity 
    ? `${API_BASE_URL}/alerts?severity=${severity}`
    : `${API_BASE_URL}/alerts`;
  
  const response = await axios.get(url);
  return response.data;
}

// Handle notifications
function setupNotificationHandlers(navigation) {
  // Foreground handler
  const unsubscribe = messaging().onMessage(async remoteMessage => {
    console.log('Notification received:', remoteMessage);
    
    const { alert_id, video_url, severity } = remoteMessage.data;
    
    // Show in-app notification
    // Update alert badge
  });
  
  // Background handler
  messaging().setBackgroundMessageHandler(async remoteMessage => {
    console.log('Background message:', remoteMessage);
  });
  
  // When app opened from notification
  messaging().onNotificationOpenedApp(remoteMessage => {
    const { alert_id } = remoteMessage.data;
    navigation.navigate('AlertDetail', { alertId: alert_id });
  });
  
  return unsubscribe;
}

export { 
  requestPermissions, 
  createMonitoringTask, 
  getAlerts, 
  setupNotificationHandlers 
};
'''

# Swift/iOS Example
SWIFT_EXAMPLE = '''
import Foundation
import FirebaseMessaging
import UserNotifications

class VideoIntelligenceService {
    static let shared = VideoIntelligenceService()
    
    let baseURL = "https://your-api-url"
    var deviceToken: String?
    
    // Register for push notifications
    func registerForNotifications() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .badge, .sound]) { granted, error in
            if granted {
                DispatchQueue.main.async {
                    UIApplication.shared.registerForRemoteNotifications()
                }
            }
        }
        
        Messaging.messaging().token { token, error in
            if let token = token {
                self.deviceToken = token
                print("FCM Token: \\(token)")
            }
        }
    }
    
    // Create monitoring task
    func createTask(name: String, prompt: String, cameraIds: [String], completion: @escaping (Result<[String: Any], Error>) -> Void) {
        guard let token = deviceToken else {
            completion(.failure(NSError(domain: "", code: -1, userInfo: [NSLocalizedDescriptionKey: "No device token"])))
            return
        }
        
        let url = URL(string: "\\(baseURL)/tasks")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let body: [String: Any] = [
            "name": name,
            "description": name,
            "camera_ids": cameraIds,
            "prompt": prompt,
            "severity": "medium",
            "notify_users": [token],
            "cooldown_minutes": 5
        ]
        
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        
        URLSession.shared.dataTask(with: request) { data, response, error in
            if let error = error {
                completion(.failure(error))
                return
            }
            
            if let data = data,
               let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                completion(.success(json))
            }
        }.resume()
    }
    
    // Fetch alerts
    func getAlerts(severity: String? = nil, completion: @escaping (Result<[[String: Any]], Error>) -> Void) {
        var urlString = "\\(baseURL)/alerts"
        if let severity = severity {
            urlString += "?severity=\\(severity)"
        }
        
        let url = URL(string: urlString)!
        
        URLSession.shared.dataTask(with: url) { data, response, error in
            if let error = error {
                completion(.failure(error))
                return
            }
            
            if let data = data,
               let json = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]] {
                completion(.success(json))
            }
        }.resume()
    }
    
    // Acknowledge alert
    func acknowledgeAlert(alertId: String, userId: String, completion: @escaping (Result<Void, Error>) -> Void) {
        let url = URL(string: "\\(baseURL)/alerts/\\(alertId)/status")!
        var request = URLRequest(url: url)
        request.httpMethod = "PUT"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let body: [String: Any] = [
            "status": "acknowledged",
            "user_id": userId
        ]
        
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        
        URLSession.shared.dataTask(with: request) { data, response, error in
            if let error = error {
                completion(.failure(error))
            } else {
                completion(.success(()))
            }
        }.resume()
    }
}

// AppDelegate setup:
// 
// func application(_ application: UIApplication, didFinishLaunchingWithOptions...) {
//     FirebaseApp.configure()
//     VideoIntelligenceService.shared.registerForNotifications()
//     Messaging.messaging().delegate = self
//     UNUserNotificationCenter.current().delegate = self
// }
'''

if __name__ == "__main__":
    print("Mobile Integration Examples for Video Intelligence Agent")
    print("=" * 60)
    print("\n📱 Flutter/Dart Example:")
    print(FLUTTER_EXAMPLE)
    print("\n📱 React Native Example:")
    print(REACT_NATIVE_EXAMPLE)
    print("\n📱 Swift/iOS Example:")
    print(SWIFT_EXAMPLE)
