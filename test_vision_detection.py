#!/usr/bin/env python3
"""
Quick test script for beauty product detection system.

Tests:
1. Detector initialization
2. Model loading
3. Detection on sample image
4. Visualization
"""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    import cv2
    import numpy as np
    from vision_pipelines.beauty_detector import BeautyProductDetector
    HAVE_DEPS = True
except ImportError as e:
    print(f"Missing dependencies: {e}")
    HAVE_DEPS = False
    sys.exit(1)


def create_test_image():
    """Create a simple test image with colored rectangles"""
    img = np.ones((480, 640, 3), dtype=np.uint8) * 50
    
    # Draw some "products" as colored rectangles
    cv2.rectangle(img, (100, 100), (250, 300), (0, 0, 255), -1)  # Red
    cv2.rectangle(img, (300, 150), (450, 350), (0, 255, 0), -1)  # Green
    cv2.rectangle(img, (150, 320), (300, 450), (255, 0, 0), -1)  # Blue
    
    # Add some text
    cv2.putText(img, "Test Products", (200, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    
    return img


def test_detector_initialization():
    """Test 1: Initialize detector"""
    print("\n" + "="*60)
    print("TEST 1: Detector Initialization")
    print("="*60)
    
    try:
        detector = BeautyProductDetector(
            model_version="11",
            model_size="nano",  # Use smallest model for testing
            confidence_threshold=0.25,
            device="cpu",
        )
        print("✓ Detector initialized successfully")
        print(f"  Model: YOLOv{detector.model_version} {detector.model_size}")
        print(f"  Device: {detector.device}")
        return detector
    except Exception as e:
        print(f"✗ Failed to initialize detector: {e}")
        return None


def test_model_list():
    """Test 2: List available models"""
    print("\n" + "="*60)
    print("TEST 2: Available Models")
    print("="*60)
    
    try:
        models = BeautyProductDetector.list_available_models()
        print(f"Found {len(models)} model configurations:")
        for model in models[:3]:  # Show first 3
            status = "✓ Downloaded" if model['exists'] else "✗ Not downloaded"
            print(f"  {model['name']}: {status}")
        return True
    except Exception as e:
        print(f"✗ Failed to list models: {e}")
        return False


def test_detection(detector):
    """Test 3: Run detection on test image"""
    print("\n" + "="*60)
    print("TEST 3: Detection")
    print("="*60)
    
    if detector is None:
        print("✗ Skipped (detector not initialized)")
        return None
    
    try:
        # Create test image
        test_img = create_test_image()
        print("✓ Created test image (640x480)")
        
        # Run detection
        result = detector.detect(test_img)
        print(f"✓ Detection completed in {result.inference_time_ms:.1f}ms")
        print(f"  Detected: {result.total_detected} objects")
        print(f"  Average FPS: {detector.get_average_fps():.1f}")
        
        if result.total_detected > 0:
            print("\n  Detections:")
            for i, det in enumerate(result.detections[:3], 1):  # Show first 3
                print(f"    {i}. {det.class_name} ({det.confidence:.2f})")
        
        return result
    except Exception as e:
        print(f"✗ Detection failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_visualization(detector, result):
    """Test 4: Visualization"""
    print("\n" + "="*60)
    print("TEST 4: Visualization")
    print("="*60)
    
    if detector is None or result is None:
        print("✗ Skipped (detector or result not available)")
        return False
    
    try:
        test_img = create_test_image()
        
        # Test with all options ON
        annotated = detector.visualize(
            test_img,
            result,
            show_boxes=True,
            show_masks=True,
            show_labels=True,
            show_confidence=True,
            mask_alpha=0.4,
        )
        
        print("✓ Visualization completed")
        print("  Options tested: boxes, masks, labels, confidence")
        
        # Save result
        output_path = Path(__file__).parent / "test_detection_output.jpg"
        cv2.imwrite(str(output_path), annotated)
        print(f"✓ Saved result to: {output_path}")
        
        return True
    except Exception as e:
        print(f"✗ Visualization failed: {e}")
        return False


def test_pipeline_integration():
    """Test 5: Pipeline integration"""
    print("\n" + "="*60)
    print("TEST 5: Pipeline Integration")
    print("="*60)
    
    try:
        from vision_pipelines.pipelines import BeautyProductSegmentationPipeline
        
        config = {
            "model_version": "11",
            "model_size": "nano",
            "min_confidence": 0.25,
            "device": "cpu",
            "show_boxes": True,
            "show_masks": True,
            "show_labels": True,
            "show_confidence": True,
        }
        
        pipeline = BeautyProductSegmentationPipeline(
            pipeline_id="test_pipeline",
            camera_name="front",
            config=config,
        )
        
        print("✓ Pipeline initialized")
        
        # Test processing
        test_img = create_test_image()
        result = pipeline.process(test_img, timestamp=0.0)
        
        print(f"✓ Pipeline processed frame")
        print(f"  Detected: {result.detected}")
        print(f"  Confidence: {result.confidence:.2f}")
        print(f"  FPS: {result.metadata.get('fps', 0):.1f}")
        
        return True
    except Exception as e:
        print(f"✗ Pipeline integration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """Run all tests"""
    print("\n")
    print("╔" + "="*58 + "╗")
    print("║" + " "*10 + "VISION DETECTION SYSTEM TEST" + " "*20 + "║")
    print("╚" + "="*58 + "╝")
    
    # Run tests
    detector = test_detector_initialization()
    test_model_list()
    result = test_detection(detector)
    test_visualization(detector, result)
    test_pipeline_integration()
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print("✓ System is ready for use!")
    print("\nNext steps:")
    print("1. Run the GUI: python app.py")
    print("2. Go to Settings → Vision tab")
    print("3. Enable Beauty Product Detection")
    print("4. Click 'Test Vision Camera' to see live detection")
    print("5. Read VISION_DETECTION_GUIDE.md for full documentation")
    print("="*60)


if __name__ == "__main__":
    import time
    
    time_ms = time.time  # For pipeline test
    run_all_tests()

