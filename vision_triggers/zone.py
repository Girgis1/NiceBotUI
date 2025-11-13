"""
Zone - Geometric region of interest for object detection

Supports:
- Polygon definition with vertices
- Point-in-polygon testing
- Bounding box calculation
- JSON serialization
- Validation
"""

import json
import uuid
from typing import List, Tuple, Optional, Dict
from pathlib import Path

from utils.logging_utils import log_exception


class Zone:
    """Represents a detection zone (region of interest)"""
    
    # Zone types
    TYPE_TRIGGER = "trigger"        # Presence/absence detection
    TYPE_COUNT = "count"            # Count objects inside
    TYPE_QUALITY = "quality_check"  # Future: quality inspection
    
    VALID_TYPES = [TYPE_TRIGGER, TYPE_COUNT, TYPE_QUALITY]
    
    def __init__(
        self,
        name: str,
        polygon: List[Tuple[int, int]],
        zone_type: str = TYPE_TRIGGER,
        zone_id: Optional[str] = None,
        enabled: bool = True,
        notes: str = ""
    ):
        """
        Initialize a zone
        
        Args:
            name: Human-readable name
            polygon: List of (x, y) vertices defining the zone
            zone_type: Type of zone (trigger, count, quality_check)
            zone_id: Unique identifier (generated if None)
            enabled: Whether zone is active
            notes: Optional description
        """
        self.zone_id = zone_id or f"zone_{uuid.uuid4().hex[:8]}"
        self.name = name
        self.polygon = polygon
        self.zone_type = zone_type
        self.enabled = enabled
        self.notes = notes
        
        # Validate
        self._validate()
    
    def _validate(self):
        """Validate zone data"""
        if not self.name:
            raise ValueError("Zone name cannot be empty")
        
        if self.zone_type not in self.VALID_TYPES:
            raise ValueError(f"Invalid zone type: {self.zone_type}. Must be one of {self.VALID_TYPES}")
        
        if len(self.polygon) < 3:
            raise ValueError(f"Polygon must have at least 3 vertices, got {len(self.polygon)}")
        
        # Validate vertices
        for i, vertex in enumerate(self.polygon):
            if not isinstance(vertex, (list, tuple)) or len(vertex) != 2:
                raise ValueError(f"Vertex {i} must be (x, y) tuple, got {vertex}")
            
            x, y = vertex
            if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
                raise ValueError(f"Vertex {i} coordinates must be numeric, got ({x}, {y})")
    
    def point_in_polygon(self, x: float, y: float) -> bool:
        """
        Test if a point is inside the polygon using ray casting algorithm
        
        Args:
            x: X coordinate
            y: Y coordinate
        
        Returns:
            True if point is inside polygon
        """
        n = len(self.polygon)
        inside = False
        
        p1x, p1y = self.polygon[0]
        for i in range(1, n + 1):
            p2x, p2y = self.polygon[i % n]
            
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            
            p1x, p1y = p2x, p2y
        
        return inside
    
    def get_bounding_box(self) -> Tuple[int, int, int, int]:
        """
        Get axis-aligned bounding box of polygon
        
        Returns:
            (x_min, y_min, x_max, y_max)
        """
        xs = [v[0] for v in self.polygon]
        ys = [v[1] for v in self.polygon]
        
        return (
            int(min(xs)),
            int(min(ys)),
            int(max(xs)),
            int(max(ys))
        )
    
    def get_center(self) -> Tuple[float, float]:
        """Get center point of bounding box"""
        x_min, y_min, x_max, y_max = self.get_bounding_box()
        return (
            (x_min + x_max) / 2.0,
            (y_min + y_max) / 2.0
        )
    
    def get_area(self) -> float:
        """Calculate approximate area using bounding box"""
        x_min, y_min, x_max, y_max = self.get_bounding_box()
        return (x_max - x_min) * (y_max - y_min)
    
    def to_dict(self) -> Dict:
        """Serialize zone to dictionary"""
        return {
            "zone_id": self.zone_id,
            "name": self.name,
            "type": self.zone_type,
            "polygon": self.polygon,
            "enabled": self.enabled,
            "notes": self.notes
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Zone':
        """
        Deserialize zone from dictionary
        
        Args:
            data: Dictionary with zone data
        
        Returns:
            Zone instance
        """
        return cls(
            name=data["name"],
            polygon=data["polygon"],
            zone_type=data.get("type", cls.TYPE_TRIGGER),
            zone_id=data.get("zone_id"),
            enabled=data.get("enabled", True),
            notes=data.get("notes", "")
        )
    
    def to_json(self) -> str:
        """Serialize zone to JSON string"""
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'Zone':
        """Deserialize zone from JSON string"""
        data = json.loads(json_str)
        return cls.from_dict(data)
    
    def save(self, filepath: Path):
        """Save zone to JSON file"""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w') as f:
            f.write(self.to_json())
    
    @classmethod
    def load(cls, filepath: Path) -> Optional['Zone']:
        """Load zone from JSON file"""
        try:
            if not filepath.exists():
                return None
            
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            return cls.from_dict(data)
        except Exception as exc:
            log_exception(f"Zone: failed to load {filepath}", exc)
            return None
    
    def __repr__(self) -> str:
        return f"Zone(id={self.zone_id}, name='{self.name}', type={self.zone_type}, vertices={len(self.polygon)})"
    
    def __str__(self) -> str:
        bbox = self.get_bounding_box()
        return f"{self.name} ({self.zone_type}): {len(self.polygon)} vertices, bbox={bbox}"


# Test the Zone class
if __name__ == "__main__":
    print("=== Zone Model Tests ===\n")
    
    # Test 1: Create a simple rectangular zone
    print("1. Creating rectangular zone...")
    rect_zone = Zone(
        name="Work Area",
        polygon=[(100, 100), (400, 100), (400, 300), (100, 300)],
        zone_type=Zone.TYPE_TRIGGER
    )
    print(f"   {rect_zone}")
    print(f"   Center: {rect_zone.get_center()}")
    print(f"   Area: {rect_zone.get_area()} px²\n")
    
    # Test 2: Point-in-polygon testing
    print("2. Testing point-in-polygon...")
    test_points = [
        (250, 200, "inside"),
        (50, 50, "outside"),
        (100, 100, "on vertex"),
        (450, 200, "outside")
    ]
    for x, y, expected in test_points:
        result = rect_zone.point_in_polygon(x, y)
        status = "✓" if (result and expected == "inside") or (not result and expected != "inside") else "✗"
        print(f"   {status} Point ({x}, {y}): {result} (expected {expected})")
    print()
    
    # Test 3: JSON serialization
    print("3. Testing JSON serialization...")
    json_str = rect_zone.to_json()
    print(f"   Serialized length: {len(json_str)} characters")
    
    loaded_zone = Zone.from_json(json_str)
    print(f"   Loaded: {loaded_zone}")
    print(f"   Names match: {loaded_zone.name == rect_zone.name}")
    print(f"   IDs match: {loaded_zone.zone_id == rect_zone.zone_id}\n")
    
    # Test 4: Multiple zone types
    print("4. Creating zones of different types...")
    zones = [
        Zone("Box 1", [(50, 50), (150, 50), (150, 150), (50, 150)], Zone.TYPE_TRIGGER),
        Zone("Count Area", [(200, 200), (400, 200), (400, 400), (200, 400)], Zone.TYPE_COUNT),
        Zone("Quality Check", [(500, 100), (700, 100), (700, 300), (500, 300)], Zone.TYPE_QUALITY)
    ]
    for zone in zones:
        print(f"   - {zone}")
    print()
    
    # Test 5: Validation
    print("5. Testing validation...")
    try:
        invalid_zone = Zone("", [(0, 0)])  # Empty name, too few vertices
        print("   ✗ Should have raised validation error")
    except ValueError as e:
        print(f"   ✓ Validation error caught: {e}")
    
    print("\n✓ Zone model tests complete!")
