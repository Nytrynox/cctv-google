"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { ObjectDetector, FilesetResolver } from "@mediapipe/tasks-vision";

// Color palette for different object categories
const COLORS = [
  "#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7",
  "#DDA0DD", "#98D8C8", "#F7DC6F", "#BB8FCE", "#85C1E9",
  "#F8B500", "#00CED1", "#FF69B4", "#32CD32", "#FF4500"
];

export default function ObjectDetection() {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const detectorRef = useRef(null);
  const animationRef = useRef(null);
  const lastTimeRef = useRef(-1);
  const categoryColorsRef = useRef({});

  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [detections, setDetections] = useState([]);
  const [fps, setFps] = useState(0);
  const [isRunning, setIsRunning] = useState(false);
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.5);
  const [maxResults, setMaxResults] = useState(10);

  // Get consistent color for each category
  const getCategoryColor = useCallback((category) => {
    if (!categoryColorsRef.current[category]) {
      const colorIndex = Object.keys(categoryColorsRef.current).length % COLORS.length;
      categoryColorsRef.current[category] = COLORS[colorIndex];
    }
    return categoryColorsRef.current[category];
  }, []);

  // Initialize the object detector
  const initializeDetector = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);

      // Load MediaPipe vision WASM
      const vision = await FilesetResolver.forVisionTasks(
        "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@latest/wasm"
      );

      // Create object detector with high accuracy settings
      detectorRef.current = await ObjectDetector.createFromOptions(vision, {
        baseOptions: {
          // Using EfficientDet-Lite2 for better accuracy (larger model)
          modelAssetPath: "https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite2/float32/latest/efficientdet_lite2.tflite",
          delegate: "GPU" // Use GPU for faster processing
        },
        runningMode: "VIDEO",
        scoreThreshold: confidenceThreshold,
        maxResults: maxResults
      });

      setIsLoading(false);
      console.log("Object detector initialized successfully");
    } catch (err) {
      console.error("Failed to initialize detector:", err);
      setError(`Failed to initialize: ${err.message}`);
      setIsLoading(false);
    }
  }, [confidenceThreshold, maxResults]);

  // Start webcam
  const startWebcam = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 1280 },
          height: { ideal: 720 },
          facingMode: "environment",
          frameRate: { ideal: 30 }
        }
      });

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
        setIsRunning(true);
      }
    } catch (err) {
      console.error("Webcam error:", err);
      setError(`Camera access failed: ${err.message}`);
    }
  }, []);

  // Draw bounding boxes on canvas
  const drawDetections = useCallback((results) => {
    const canvas = canvasRef.current;
    const video = videoRef.current;
    if (!canvas || !video) return;

    const ctx = canvas.getContext("2d");
    
    // Match canvas size to video
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    // Clear previous drawings
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (!results || !results.detections) return;

    results.detections.forEach((detection) => {
      const bbox = detection.boundingBox;
      const category = detection.categories[0];
      
      if (!bbox || !category) return;

      const color = getCategoryColor(category.categoryName);
      const confidence = Math.round(category.score * 100);

      // Draw bounding box with thicker lines for visibility
      ctx.strokeStyle = color;
      ctx.lineWidth = 3;
      ctx.strokeRect(bbox.originX, bbox.originY, bbox.width, bbox.height);

      // Draw semi-transparent fill
      ctx.fillStyle = color + "20";
      ctx.fillRect(bbox.originX, bbox.originY, bbox.width, bbox.height);

      // Draw label background
      const label = `${category.categoryName} ${confidence}%`;
      ctx.font = "bold 16px Arial";
      const textMetrics = ctx.measureText(label);
      const textWidth = textMetrics.width + 12;
      const textHeight = 24;

      // Position label above box, or inside if at top edge
      let labelY = bbox.originY - textHeight - 4;
      if (labelY < 0) {
        labelY = bbox.originY + 4;
      }

      // Label background
      ctx.fillStyle = color;
      ctx.fillRect(bbox.originX, labelY, textWidth, textHeight);

      // Label text
      ctx.fillStyle = "#FFFFFF";
      ctx.fillText(label, bbox.originX + 6, labelY + 17);

      // Draw corner markers for emphasis
      const cornerSize = 15;
      ctx.strokeStyle = color;
      ctx.lineWidth = 4;
      
      // Top-left corner
      ctx.beginPath();
      ctx.moveTo(bbox.originX, bbox.originY + cornerSize);
      ctx.lineTo(bbox.originX, bbox.originY);
      ctx.lineTo(bbox.originX + cornerSize, bbox.originY);
      ctx.stroke();

      // Top-right corner
      ctx.beginPath();
      ctx.moveTo(bbox.originX + bbox.width - cornerSize, bbox.originY);
      ctx.lineTo(bbox.originX + bbox.width, bbox.originY);
      ctx.lineTo(bbox.originX + bbox.width, bbox.originY + cornerSize);
      ctx.stroke();

      // Bottom-left corner
      ctx.beginPath();
      ctx.moveTo(bbox.originX, bbox.originY + bbox.height - cornerSize);
      ctx.lineTo(bbox.originX, bbox.originY + bbox.height);
      ctx.lineTo(bbox.originX + cornerSize, bbox.originY + bbox.height);
      ctx.stroke();

      // Bottom-right corner
      ctx.beginPath();
      ctx.moveTo(bbox.originX + bbox.width - cornerSize, bbox.originY + bbox.height);
      ctx.lineTo(bbox.originX + bbox.width, bbox.originY + bbox.height);
      ctx.lineTo(bbox.originX + bbox.width, bbox.originY + bbox.height - cornerSize);
      ctx.stroke();
    });
  }, [getCategoryColor]);

  // Detection loop
  const detectObjects = useCallback(async () => {
    const video = videoRef.current;
    const detector = detectorRef.current;

    if (!video || !detector || video.readyState < 2) {
      animationRef.current = requestAnimationFrame(detectObjects);
      return;
    }

    const currentTime = video.currentTime;
    
    // Only process if video time has changed (avoid duplicate frames)
    if (currentTime !== lastTimeRef.current) {
      lastTimeRef.current = currentTime;
      
      const startTime = performance.now();
      
      try {
        // Run detection
        const results = detector.detectForVideo(video, performance.now());
        
        // Calculate FPS
        const endTime = performance.now();
        const inferenceTime = endTime - startTime;
        setFps(Math.round(1000 / inferenceTime));

        // Update detections state
        if (results && results.detections) {
          setDetections(results.detections.map(d => ({
            name: d.categories[0]?.categoryName || "Unknown",
            confidence: d.categories[0]?.score || 0,
            bbox: d.boundingBox
          })));
        }

        // Draw results
        drawDetections(results);
      } catch (err) {
        console.error("Detection error:", err);
      }
    }

    // Continue detection loop
    animationRef.current = requestAnimationFrame(detectObjects);
  }, [drawDetections]);

  // Start detection
  const startDetection = useCallback(() => {
    if (animationRef.current) {
      cancelAnimationFrame(animationRef.current);
    }
    animationRef.current = requestAnimationFrame(detectObjects);
  }, [detectObjects]);

  // Stop detection
  const stopDetection = useCallback(() => {
    if (animationRef.current) {
      cancelAnimationFrame(animationRef.current);
      animationRef.current = null;
    }
    setIsRunning(false);
    
    // Clear canvas
    const canvas = canvasRef.current;
    if (canvas) {
      const ctx = canvas.getContext("2d");
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    }
    
    // Stop video stream
    if (videoRef.current && videoRef.current.srcObject) {
      const tracks = videoRef.current.srcObject.getTracks();
      tracks.forEach(track => track.stop());
      videoRef.current.srcObject = null;
    }
    
    setDetections([]);
  }, []);

  // Update detector settings
  const updateSettings = useCallback(async () => {
    if (detectorRef.current) {
      try {
        await detectorRef.current.setOptions({
          scoreThreshold: confidenceThreshold,
          maxResults: maxResults
        });
      } catch (err) {
        console.error("Failed to update settings:", err);
      }
    }
  }, [confidenceThreshold, maxResults]);

  // Initialize on mount
  useEffect(() => {
    initializeDetector();
    
    return () => {
      stopDetection();
      if (detectorRef.current) {
        detectorRef.current.close();
      }
    };
  }, []);

  // Update settings when changed
  useEffect(() => {
    updateSettings();
  }, [confidenceThreshold, maxResults, updateSettings]);

  // Handle start button
  const handleStart = async () => {
    await startWebcam();
    startDetection();
  };

  // Get confidence class for styling
  const getConfidenceClass = (confidence) => {
    if (confidence >= 0.8) return "confidence-high";
    if (confidence >= 0.6) return "confidence-medium";
    return "confidence-low";
  };

  return (
    <div className="container">
      <h1>🎯 Real-Time Object Detection</h1>
      
      {/* Status indicator */}
      <div className={`status ${isLoading ? "loading" : error ? "error" : "ready"}`}>
        {isLoading ? "⏳ Loading AI model..." : error ? `❌ ${error}` : "✅ Ready"}
      </div>

      {/* Video container */}
      <div className="video-container">
        <video
          ref={videoRef}
          playsInline
          muted
          style={{ transform: "scaleX(-1)" }}
        />
        <canvas
          ref={canvasRef}
          className="canvas-overlay"
          style={{ transform: "scaleX(-1)" }}
        />
      </div>

      {/* Controls */}
      <div className="controls">
        {!isRunning ? (
          <button onClick={handleStart} disabled={isLoading}>
            ▶️ Start Detection
          </button>
        ) : (
          <button onClick={stopDetection}>
            ⏹️ Stop
          </button>
        )}
        
        <select
          value={confidenceThreshold}
          onChange={(e) => setConfidenceThreshold(parseFloat(e.target.value))}
        >
          <option value={0.3}>Low Threshold (30%)</option>
          <option value={0.5}>Medium Threshold (50%)</option>
          <option value={0.7}>High Threshold (70%)</option>
          <option value={0.8}>Very High (80%)</option>
        </select>

        <select
          value={maxResults}
          onChange={(e) => setMaxResults(parseInt(e.target.value))}
        >
          <option value={5}>Max 5 Objects</option>
          <option value={10}>Max 10 Objects</option>
          <option value={20}>Max 20 Objects</option>
        </select>
      </div>

      {/* Performance stats */}
      {isRunning && (
        <div className="stats">
          <span>⚡ FPS: {fps}</span>
          <span>🎯 Objects: {detections.length}</span>
          <span>📊 Threshold: {Math.round(confidenceThreshold * 100)}%</span>
        </div>
      )}

      {/* Detection list */}
      {detections.length > 0 && (
        <div className="detections-list">
          <h3>Detected Objects:</h3>
          {detections.map((det, idx) => (
            <div key={idx} className="detection-item">
              <span>{det.name}</span>
              <span className={getConfidenceClass(det.confidence)}>
                {Math.round(det.confidence * 100)}%
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
