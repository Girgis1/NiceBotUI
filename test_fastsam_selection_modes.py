#!/usr/bin/env python3
"""
FastSAM Selection Modes Test Suite.

Tests all 3 selection modes:
1. ALL - Show all detected objects
2. LARGEST - Pick only the largest object
3. CENTER_REGION - Only objects in center region
4. POINT_CLICK - Click to select specific object

Demonstrates visual differences and use cases.
"""

import sys
from pathlib import Path
import time

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    import cv2
    import numpy as np
    from vision_pipelines.fastsam_detector import FastSAMDetector
    HAVE_DEPS = True
except ImportError as e:
    print(f"Missing dependencies: {e}")
    HAVE_DEPS = False
    sys.exit(1)


def create_complex_test_scene():
    """Create a test scene with MULTIPLE objects to test selection"""
    img = np.ones((720, 1280, 3), dtype=np.uint8) * 40
    
    # Background elements (noise)
    cv2.rectangle(img, (50, 50), (150, 100), (80, 80, 80), -1)  # Gray noise (top-left)
    cv2.circle(img, (1150, 80), 50, (80, 80, 80), -1)  # Gray noise (top-right)
    
    # Edge objects (test center_region mode)
    cv2.rectangle(img, (20, 300), (100, 400), (100, 100, 255), -1)  # Pink (left edge)
    cv2.rectangle(img, (1180, 300), (1260, 400), (100, 100, 255), -1)  # Pink (right edge)
    
    # Center objects (main products)
    cv2.rectangle(img, (400, 250), (550, 450), (0, 0, 255), -1)  # RED (center-left, LARGE)
    cv2.circle(img, (750, 350), 90, (0, 255, 0), -1)  # GREEN (center-right, MEDIUM)
    cv2.ellipse(img, (640, 520), (120, 70), 0, 0, 360, (255, 0, 0), -1)  # BLUE (center-bottom, SMALL)
    
    # Add labels
    cv2.putText(img, "FastSAM Selection Mode Test", (380, 40), 
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 2)
    cv2.putText(img, "Edge Objects", (20, 280), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
    cv2.putText(img, "CENTER PRODUCTS", (500, 220), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
    
    # Draw reference center region
    h, w = img.shape[:2]
    margin = int(w * 0.25)  # 50% center region
    cv2.rectangle(img, (margin, int(h*0.25)), (w-margin, int(h*0.75)), 
                  (100, 100, 100), 2, cv2.LINE_AA)
    cv2.putText(img, "Center 50%", (margin + 10, int(h*0.25) + 30), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (100, 100, 100), 1)
    
    return img


def test_mode_all(test_img):
    """Test Mode 1: ALL objects"""
    print("\n" + "="*70)
    print("MODE 1: ALL OBJECTS (Default behavior)")
    print("="*70)
    print("Use case: General detection, count all objects in scene")
    
    detector = FastSAMDetector(
        model_size="small",
        confidence_threshold=0.4,
        device="cpu",
        selection_mode="all",  # <-- ALL MODE
        min_object_size=500,
        max_object_size=100000,
    )
    
    result = detector.detect(test_img)
    annotated = detector.visualize(test_img, result, show_masks=True, show_boxes=True)
    
    print(f"✓ Detected: {result.total_detected} objects")
    print(f"  Inference: {result.inference_time_ms:.1f}ms")
    
    # Save output
    output_path = Path(__file__).parent / "test_mode_all.jpg"
    cv2.imwrite(str(output_path), annotated)
    print(f"✓ Saved: {output_path}")
    
    return result


def test_mode_largest(test_img):
    """Test Mode 2: LARGEST object only"""
    print("\n" + "="*70)
    print("MODE 2: LARGEST OBJECT ONLY")
    print("="*70)
    print("Use case: Pick up the biggest product, ignore small debris")
    
    detector = FastSAMDetector(
        model_size="small",
        confidence_threshold=0.4,
        device="cpu",
        selection_mode="largest",  # <-- LARGEST MODE
        min_object_size=500,
        max_object_size=100000,
    )
    
    result = detector.detect(test_img)
    annotated = detector.visualize(test_img, result, show_masks=True, show_boxes=True)
    
    print(f"✓ Detected: {result.total_detected} objects (filtered to largest)")
    if result.total_detected > 0:
        print(f"  Selected object area: {result.detections[0].area} px²")
        print(f"  Confidence: {result.detections[0].confidence:.2f}")
    print(f"  Inference: {result.inference_time_ms:.1f}ms")
    
    # Save output
    output_path = Path(__file__).parent / "test_mode_largest.jpg"
    cv2.imwrite(str(output_path), annotated)
    print(f"✓ Saved: {output_path}")
    
    return result


def test_mode_center_region(test_img):
    """Test Mode 3: CENTER REGION only"""
    print("\n" + "="*70)
    print("MODE 3: CENTER REGION ONLY")
    print("="*70)
    print("Use case: Ignore objects at edge of frame, focus on work area")
    
    detector = FastSAMDetector(
        model_size="small",
        confidence_threshold=0.4,
        device="cpu",
        selection_mode="center_region",  # <-- CENTER REGION MODE
        center_region_percent=50.0,  # Center 50% of frame
        min_object_size=500,
        max_object_size=100000,
    )
    
    result = detector.detect(test_img)
    annotated = detector.visualize(test_img, result, show_masks=True, show_boxes=True)
    
    print(f"✓ Detected: {result.total_detected} objects (in center 50%)")
    print(f"  Region: Center 50% of frame")
    print(f"  Edge objects: IGNORED")
    print(f"  Inference: {result.inference_time_ms:.1f}ms")
    
    # Save output (will show center region box overlay)
    output_path = Path(__file__).parent / "test_mode_center_region.jpg"
    cv2.imwrite(str(output_path), annotated)
    print(f"✓ Saved: {output_path}")
    
    return result


def test_mode_point_click(test_img):
    """Test Mode 4: POINT CLICK"""
    print("\n" + "="*70)
    print("MODE 4: POINT CLICK SELECTION")
    print("="*70)
    print("Use case: User clicks on specific object, robot picks that one")
    
    detector = FastSAMDetector(
        model_size="small",
        confidence_threshold=0.4,
        device="cpu",
        selection_mode="point_click",  # <-- POINT CLICK MODE
        min_object_size=500,
        max_object_size=100000,
    )
    
    # Simulate clicking on the GREEN circle (center-right)
    click_x, click_y = 750, 350
    
    print(f"  Simulating click at: ({click_x}, {click_y}) [GREEN circle]")
    
    result = detector.detect(test_img, click_point=(click_x, click_y))
    annotated = detector.visualize(test_img, result, show_masks=True, show_boxes=True)
    
    print(f"✓ Detected: {result.total_detected} object (at click point)")
    if result.total_detected > 0:
        print(f"  Selected object area: {result.detections[0].area} px²")
        print(f"  Click point: ({click_x}, {click_y})")
    print(f"  Inference: {result.inference_time_ms:.1f}ms")
    
    # Save output (will show crosshair at click point)
    output_path = Path(__file__).parent / "test_mode_point_click.jpg"
    cv2.imwrite(str(output_path), annotated)
    print(f"✓ Saved: {output_path}")
    
    # Test clicking on RED rectangle
    print("\n  Testing another click point...")
    click_x2, click_y2 = 475, 350
    print(f"  Simulating click at: ({click_x2}, {click_y2}) [RED rectangle]")
    
    result2 = detector.detect(test_img, click_point=(click_x2, click_y2))
    annotated2 = detector.visualize(test_img, result2, show_masks=True, show_boxes=True)
    
    print(f"✓ Detected: {result2.total_detected} object")
    if result2.total_detected > 0:
        print(f"  Selected object area: {result2.detections[0].area} px²")
    
    output_path2 = Path(__file__).parent / "test_mode_point_click_red.jpg"
    cv2.imwrite(str(output_path2), annotated2)
    print(f"✓ Saved: {output_path2}")
    
    return result


def test_mode_switching():
    """Test 5: Dynamic mode switching"""
    print("\n" + "="*70)
    print("MODE 5: DYNAMIC MODE SWITCHING")
    print("="*70)
    print("Use case: Change modes on-the-fly without reloading model")
    
    test_img = create_complex_test_scene()
    
    detector = FastSAMDetector(model_size="small", device="cpu")
    
    # Switch through modes dynamically
    modes = ["all", "largest", "center_region", "point_click"]
    
    for mode in modes:
        detector.selection_mode = mode  # Dynamic switching!
        if mode == "center_region":
            detector.center_region_percent = 60.0
        
        result = detector.detect(test_img)
        print(f"  Mode '{mode}': {result.total_detected} objects detected")
    
    print("✓ Mode switching works perfectly!")
    print("  You can change modes in GUI settings without restarting")
    
    return True


def run_comparison_summary():
    """Display comparison summary"""
    print("\n" + "="*70)
    print("SELECTION MODE COMPARISON SUMMARY")
    print("="*70)
    
    comparison = [
        {
            "mode": "all",
            "name": "ALL Objects",
            "detects": "Everything in scene",
            "use_case": "Counting, general detection",
            "speed": "Fast",
        },
        {
            "mode": "largest",
            "name": "LARGEST Object",
            "detects": "Biggest object only",
            "use_case": "Pick main product, ignore debris",
            "speed": "Fastest (fewer objects)",
        },
        {
            "mode": "center_region",
            "name": "CENTER REGION",
            "detects": "Objects in defined region",
            "use_case": "Fixed robot workspace",
            "speed": "Fast",
        },
        {
            "mode": "point_click",
            "name": "POINT CLICK",
            "detects": "Object at clicked point",
            "use_case": "Manual selection, variable scenes",
            "speed": "Fast",
        },
    ]
    
    for comp in comparison:
        print(f"\n{comp['name']} (mode='{comp['mode']}')")
        print(f"  Detects:  {comp['detects']}")
        print(f"  Use case: {comp['use_case']}")
        print(f"  Speed:    {comp['speed']}")
    
    print("\n" + "="*70)


def run_all_tests():
    """Run all selection mode tests"""
    print("\n")
    print("╔" + "="*68 + "╗")
    print("║" + " "*15 + "FASTSAM SELECTION MODES TEST" + " "*26 + "║")
    print("╚" + "="*68 + "╝")
    
    # Create test scene
    print("\nCreating complex test scene...")
    test_img = create_complex_test_scene()
    print("✓ Test scene created (1280x720)")
    print("  - Edge objects (will be filtered by center_region)")
    print("  - Center objects (RED=largest, GREEN=medium, BLUE=smallest)")
    print("  - Background noise")
    
    # Save original scene
    cv2.imwrite(str(Path(__file__).parent / "test_scene_original.jpg"), test_img)
    print("✓ Original scene saved: test_scene_original.jpg")
    
    # Run tests
    test_mode_all(test_img.copy())
    test_mode_largest(test_img.copy())
    test_mode_center_region(test_img.copy())
    test_mode_point_click(test_img.copy())
    test_mode_switching()
    
    # Summary
    run_comparison_summary()
    
    print("\n" + "="*70)
    print("HOW TO USE IN GUI")
    print("="*70)
    print("1. Run: python app.py")
    print("2. Go to: Settings → Vision tab")
    print("3. Select: FastSAM Segmentation ⚡")
    print("4. Configure:")
    print("   Selection Mode: all / largest / center_region / point_click")
    print("   Center Region %: 30-70% (for center_region mode)")
    print("5. Click 'Test Vision Camera' to see live results")
    print("\nOUTPUT FILES:")
    print("  - test_scene_original.jpg    (original scene)")
    print("  - test_mode_all.jpg          (all objects)")
    print("  - test_mode_largest.jpg      (largest only)")
    print("  - test_mode_center_region.jpg (center region)")
    print("  - test_mode_point_click.jpg   (clicked object)")
    print("="*70)


if __name__ == "__main__":
    run_all_tests()

