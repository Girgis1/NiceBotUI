"""
Trigger Rules - Evaluate trigger conditions

Supports:
- Presence detection (object present/absent in zone)
- Count-based triggers (N objects in zone)
- Multi-zone logic (AND/OR combinations)
- Cumulative counting
"""

from typing import List, Dict, Optional
from dataclasses import dataclass

try:
    from .detectors.base import DetectionResult
except ImportError:
    from detectors.base import DetectionResult


@dataclass
class TriggerEvaluation:
    """Result of trigger condition evaluation"""
    triggered: bool
    reason: str
    details: Dict
    
    def __repr__(self) -> str:
        return f"TriggerEvaluation(triggered={self.triggered}, reason='{self.reason}')"


class TriggerEvaluator:
    """Evaluate trigger conditions based on detection results"""
    
    def __init__(self):
        # Cumulative counters for count-based triggers
        self.cumulative_counts = {}
    
    def evaluate_presence(
        self,
        detection_results: List[DetectionResult],
        zone_id: str,
        min_objects: int = 1
    ) -> TriggerEvaluation:
        """
        Evaluate presence-based trigger
        
        Args:
            detection_results: List of detection results from detector
            zone_id: Zone to check
            min_objects: Minimum objects required
        
        Returns:
            TriggerEvaluation with result
        """
        # Find result for this zone
        zone_result = None
        for result in detection_results:
            if result.metadata.get("zone_id") == zone_id:
                zone_result = result
                break
        
        if not zone_result:
            return TriggerEvaluation(
                triggered=False,
                reason=f"Zone {zone_id} not found in detection results",
                details={"zone_id": zone_id}
            )
        
        object_count = zone_result.metadata.get("object_count", 0)
        triggered = object_count >= min_objects
        
        return TriggerEvaluation(
            triggered=triggered,
            reason=f"{'Found' if triggered else 'Need'} {min_objects} object(s), got {object_count}",
            details={
                "zone_id": zone_id,
                "zone_name": zone_result.metadata.get("zone_name", "unknown"),
                "object_count": object_count,
                "min_objects": min_objects,
                "boxes": zone_result.boxes,
                "confidence": zone_result.confidence
            }
        )
    
    def evaluate_count(
        self,
        detection_results: List[DetectionResult],
        zone_id: str,
        target_count: int,
        operator: str = ">=",
        cumulative: bool = False,
        trigger_id: Optional[str] = None
    ) -> TriggerEvaluation:
        """
        Evaluate count-based trigger
        
        Args:
            detection_results: Detection results
            zone_id: Zone to check
            target_count: Target object count
            operator: Comparison operator (>=, <=, ==, >, <)
            cumulative: Whether to accumulate counts across frames
            trigger_id: Trigger ID for cumulative tracking
        
        Returns:
            TriggerEvaluation with result
        """
        # Find zone result
        zone_result = None
        for result in detection_results:
            if result.metadata.get("zone_id") == zone_id:
                zone_result = result
                break
        
        if not zone_result:
            return TriggerEvaluation(
                triggered=False,
                reason=f"Zone {zone_id} not found",
                details={"zone_id": zone_id}
            )
        
        current_count = zone_result.metadata.get("object_count", 0)
        
        # Handle cumulative counting
        if cumulative and trigger_id:
            if trigger_id not in self.cumulative_counts:
                self.cumulative_counts[trigger_id] = 0
            
            # Add current count to cumulative
            if current_count > 0:
                self.cumulative_counts[trigger_id] += current_count
            
            count_to_check = self.cumulative_counts[trigger_id]
        else:
            count_to_check = current_count
        
        # Evaluate operator
        triggered = self._compare(count_to_check, target_count, operator)
        
        return TriggerEvaluation(
            triggered=triggered,
            reason=f"Count {count_to_check} {operator} {target_count}: {triggered}",
            details={
                "zone_id": zone_id,
                "zone_name": zone_result.metadata.get("zone_name", "unknown"),
                "current_count": current_count,
                "cumulative_count": count_to_check if cumulative else None,
                "target_count": target_count,
                "operator": operator,
                "boxes": zone_result.boxes
            }
        )
    
    def evaluate_multi_zone(
        self,
        detection_results: List[DetectionResult],
        zone_rules: List[Dict],
        logic: str = "AND"
    ) -> TriggerEvaluation:
        """
        Evaluate multi-zone trigger with AND/OR logic
        
        Args:
            detection_results: Detection results
            zone_rules: List of {"zone": zone_id, "min_objects": n} dicts
            logic: "AND" or "OR"
        
        Returns:
            TriggerEvaluation with result
        """
        if not zone_rules:
            return TriggerEvaluation(
                triggered=False,
                reason="No zone rules specified",
                details={}
            )
        
        # Evaluate each zone rule
        zone_results = []
        for rule in zone_rules:
            zone_id = rule.get("zone")
            min_objects = rule.get("min_objects", 1)
            
            # Find zone result
            zone_result = None
            for result in detection_results:
                if result.metadata.get("zone_id") == zone_id:
                    zone_result = result
                    break
            
            if zone_result:
                object_count = zone_result.metadata.get("object_count", 0)
                satisfied = object_count >= min_objects
                zone_results.append({
                    "zone_id": zone_id,
                    "zone_name": zone_result.metadata.get("zone_name", "unknown"),
                    "satisfied": satisfied,
                    "object_count": object_count,
                    "min_objects": min_objects
                })
            else:
                zone_results.append({
                    "zone_id": zone_id,
                    "satisfied": False,
                    "object_count": 0,
                    "min_objects": min_objects,
                    "error": "Zone not found"
                })
        
        # Apply logic
        if logic == "AND":
            triggered = all(zr["satisfied"] for zr in zone_results)
            reason = "All zones satisfied" if triggered else "Not all zones satisfied"
        elif logic == "OR":
            triggered = any(zr["satisfied"] for zr in zone_results)
            reason = "At least one zone satisfied" if triggered else "No zones satisfied"
        else:
            return TriggerEvaluation(
                triggered=False,
                reason=f"Invalid logic operator: {logic}",
                details={}
            )
        
        return TriggerEvaluation(
            triggered=triggered,
            reason=reason,
            details={
                "logic": logic,
                "zone_results": zone_results,
                "total_zones": len(zone_rules),
                "satisfied_count": sum(1 for zr in zone_results if zr["satisfied"])
            }
        )
    
    def evaluate_trigger(
        self,
        trigger_data: Dict,
        detection_results: List[DetectionResult]
    ) -> TriggerEvaluation:
        """
        Evaluate a complete trigger based on its configuration
        
        Args:
            trigger_data: Full trigger data from TriggersManager
            detection_results: Detection results from detector
        
        Returns:
            TriggerEvaluation with result
        """
        trigger_type = trigger_data.get("type")
        conditions = trigger_data.get("conditions", {})
        
        if trigger_type == "presence":
            # Presence-based trigger
            rules = conditions.get("rules", {})
            zone_id = rules.get("zone")
            min_objects = rules.get("min_objects", 1)
            
            return self.evaluate_presence(detection_results, zone_id, min_objects)
        
        elif trigger_type == "count":
            # Count-based trigger
            rules = conditions.get("rules", {})
            zone_id = rules.get("zone")
            target_count = rules.get("count", 10)
            operator = rules.get("operator", ">=")
            cumulative = rules.get("cumulative", False)
            trigger_id = trigger_data.get("trigger_id")
            
            return self.evaluate_count(
                detection_results,
                zone_id,
                target_count,
                operator,
                cumulative,
                trigger_id
            )
        
        elif trigger_type == "multi_zone":
            # Multi-zone trigger
            rules = conditions.get("rules", {})
            zone_rules = rules.get("zones", [])
            logic = rules.get("logic", "AND")
            
            return self.evaluate_multi_zone(detection_results, zone_rules, logic)
        
        else:
            return TriggerEvaluation(
                triggered=False,
                reason=f"Unknown trigger type: {trigger_type}",
                details={"trigger_type": trigger_type}
            )
    
    def _compare(self, value: float, target: float, operator: str) -> bool:
        """Compare values with operator"""
        if operator == ">=":
            return value >= target
        elif operator == "<=":
            return value <= target
        elif operator == "==":
            return value == target
        elif operator == ">":
            return value > target
        elif operator == "<":
            return value < target
        else:
            return False
    
    def reset_cumulative_count(self, trigger_id: str):
        """Reset cumulative count for a trigger"""
        if trigger_id in self.cumulative_counts:
            del self.cumulative_counts[trigger_id]
    
    def get_cumulative_count(self, trigger_id: str) -> int:
        """Get current cumulative count for a trigger"""
        return self.cumulative_counts.get(trigger_id, 0)


# Test the trigger evaluator
if __name__ == "__main__":
    print("=== Trigger Evaluator Tests ===\n")
    
    from detectors.base import DetectionResult
    
    evaluator = TriggerEvaluator()
    
    # Create mock detection results
    results = [
        DetectionResult(
            detected=True,
            boxes=[(100, 100, 50, 50)],
            confidence=0.9,
            metadata={
                "zone_id": "work_area",
                "zone_name": "Work Area",
                "object_count": 1
            }
        ),
        DetectionResult(
            detected=True,
            boxes=[(200, 200, 30, 30), (250, 250, 30, 30)],
            confidence=0.85,
            metadata={
                "zone_id": "box_1",
                "zone_name": "Box 1",
                "object_count": 2
            }
        ),
        DetectionResult(
            detected=False,
            boxes=[],
            confidence=0.0,
            metadata={
                "zone_id": "box_2",
                "zone_name": "Box 2",
                "object_count": 0
            }
        )
    ]
    
    # Test 1: Presence evaluation
    print("1. Testing presence evaluation...")
    eval_result = evaluator.evaluate_presence(results, "work_area", min_objects=1)
    print(f"   Result: {eval_result}")
    print(f"   Triggered: {eval_result.triggered}")
    print(f"   Reason: {eval_result.reason}\n")
    
    # Test 2: Count evaluation
    print("2. Testing count evaluation...")
    eval_result = evaluator.evaluate_count(results, "box_1", target_count=2, operator="==")
    print(f"   Result: {eval_result}")
    print(f"   Triggered: {eval_result.triggered}\n")
    
    # Test 3: Multi-zone AND
    print("3. Testing multi-zone AND logic...")
    zone_rules = [
        {"zone": "box_1", "min_objects": 1},
        {"zone": "box_2", "min_objects": 1}
    ]
    eval_result = evaluator.evaluate_multi_zone(results, zone_rules, logic="AND")
    print(f"   Result: {eval_result}")
    print(f"   Triggered: {eval_result.triggered}")
    print(f"   Details: {eval_result.details['zone_results']}\n")
    
    # Test 4: Multi-zone OR
    print("4. Testing multi-zone OR logic...")
    eval_result = evaluator.evaluate_multi_zone(results, zone_rules, logic="OR")
    print(f"   Result: {eval_result}")
    print(f"   Triggered: {eval_result.triggered}\n")
    
    # Test 5: Cumulative counting
    print("5. Testing cumulative counting...")
    for i in range(3):
        eval_result = evaluator.evaluate_count(
            results, "work_area", target_count=3,
            operator=">=", cumulative=True, trigger_id="test_count"
        )
        cumulative = evaluator.get_cumulative_count("test_count")
        print(f"   Iteration {i+1}: Cumulative = {cumulative}, Triggered = {eval_result.triggered}")
    print()
    
    # Test 6: Full trigger evaluation
    print("6. Testing full trigger evaluation...")
    trigger_data = {
        "trigger_id": "idle_standby",
        "type": "presence",
        "conditions": {
            "rules": {
                "zone": "work_area",
                "min_objects": 1
            }
        }
    }
    eval_result = evaluator.evaluate_trigger(trigger_data, results)
    print(f"   Result: {eval_result}")
    print(f"   Triggered: {eval_result.triggered}\n")
    
    print("✓ Trigger evaluator tests complete!")

