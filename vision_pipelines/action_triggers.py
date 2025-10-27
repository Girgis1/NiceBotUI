"""
Action triggers for vision detection events.

Allows configuring automatic actions when specific objects are detected:
- Emergency pause/stop when person detected
- Count inventory when products pass by
- Alert on defect detection
- Trigger robot actions on object appearance
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, List, Optional


class TriggerAction(Enum):
    """Available trigger actions"""
    EMERGENCY_STOP = "emergency_stop"
    PAUSE = "pause"
    LOG = "log"
    ALERT = "alert"
    COUNT = "count"
    CUSTOM = "custom"


class TriggerCondition(Enum):
    """Trigger conditions"""
    DETECTED = "detected"              # When object appears
    NOT_DETECTED = "not_detected"      # When object disappears
    CONFIDENCE_ABOVE = "confidence_above"  # Confidence > threshold
    COUNT_ABOVE = "count_above"        # More than N objects
    COUNT_BELOW = "count_below"        # Fewer than N objects


@dataclass
class TriggerRule:
    """A single trigger rule configuration"""
    
    # What to detect
    class_names: List[str]  # e.g., ["person", "hand"]
    condition: TriggerCondition = TriggerCondition.DETECTED
    threshold: float = 0.5  # For confidence/count conditions
    
    # What to do
    action: TriggerAction = TriggerAction.LOG
    custom_callback: Optional[Callable] = None
    
    # Additional config
    enabled: bool = True
    cooldown_seconds: float = 1.0  # Minimum time between triggers
    description: str = ""
    
    # Internal state
    _last_trigger_time: float = 0.0
    _trigger_count: int = 0


class VisionActionTrigger:
    """
    Execute actions based on vision detection results.
    
    Example use cases:
    - Emergency stop when person detected
    - Count products passing by
    - Alert on defect detection
    - Trigger robot sequence on object appearance
    """
    
    def __init__(self):
        self.rules: List[TriggerRule] = []
        self._callbacks: Dict[TriggerAction, Callable] = {}
    
    def add_rule(self, rule: TriggerRule):
        """Add a trigger rule"""
        self.rules.append(rule)
    
    def remove_rule(self, rule: TriggerRule):
        """Remove a trigger rule"""
        if rule in self.rules:
            self.rules.remove(rule)
    
    def register_callback(self, action: TriggerAction, callback: Callable):
        """
        Register a callback function for an action.
        
        Args:
            action: The action type
            callback: Function to call, receives (rule, detections)
        """
        self._callbacks[action] = callback
    
    def process_detections(self, detections: List[Dict], timestamp: float) -> List[Dict]:
        """
        Process detection results and trigger actions.
        
        Args:
            detections: List of detection dicts with 'class', 'confidence', etc.
            timestamp: Current timestamp
        
        Returns:
            List of triggered actions with details
        """
        triggered_actions = []
        
        for rule in self.rules:
            if not rule.enabled:
                continue
            
            # Check cooldown
            if timestamp - rule._last_trigger_time < rule.cooldown_seconds:
                continue
            
            # Evaluate condition
            should_trigger = self._evaluate_rule(rule, detections)
            
            if should_trigger:
                # Execute action
                action_result = self._execute_action(rule, detections, timestamp)
                triggered_actions.append(action_result)
                
                # Update state
                rule._last_trigger_time = timestamp
                rule._trigger_count += 1
        
        return triggered_actions
    
    def _evaluate_rule(self, rule: TriggerRule, detections: List[Dict]) -> bool:
        """Evaluate if a rule condition is met"""
        # Filter detections by class
        matching_detections = [
            d for d in detections
            if d.get('class', d.get('class_name')) in rule.class_names
        ]
        
        if rule.condition == TriggerCondition.DETECTED:
            return len(matching_detections) > 0
        
        elif rule.condition == TriggerCondition.NOT_DETECTED:
            return len(matching_detections) == 0
        
        elif rule.condition == TriggerCondition.CONFIDENCE_ABOVE:
            return any(d.get('confidence', 0) > rule.threshold for d in matching_detections)
        
        elif rule.condition == TriggerCondition.COUNT_ABOVE:
            return len(matching_detections) > rule.threshold
        
        elif rule.condition == TriggerCondition.COUNT_BELOW:
            return len(matching_detections) < rule.threshold
        
        return False
    
    def _execute_action(self, rule: TriggerRule, detections: List[Dict], timestamp: float) -> Dict:
        """Execute the rule's action"""
        result = {
            'rule': rule.description or f"Rule for {rule.class_names}",
            'action': rule.action.value,
            'timestamp': timestamp,
            'detections': len([d for d in detections if d.get('class', d.get('class_name')) in rule.class_names]),
        }
        
        # Execute registered callback
        callback = None
        if rule.action == TriggerAction.CUSTOM and rule.custom_callback:
            callback = rule.custom_callback
        elif rule.action in self._callbacks:
            callback = self._callbacks[rule.action]
        
        if callback:
            try:
                callback(rule, detections)
                result['status'] = 'success'
            except Exception as e:
                result['status'] = 'error'
                result['error'] = str(e)
        else:
            result['status'] = 'no_callback'
        
        return result
    
    def get_statistics(self) -> Dict:
        """Get trigger statistics"""
        stats = {
            'total_rules': len(self.rules),
            'enabled_rules': sum(1 for r in self.rules if r.enabled),
            'rules': []
        }
        
        for rule in self.rules:
            stats['rules'].append({
                'description': rule.description,
                'class_names': rule.class_names,
                'trigger_count': rule._trigger_count,
                'enabled': rule.enabled,
            })
        
        return stats


# ============================================================
# Pre-configured trigger templates
# ============================================================

def create_emergency_stop_trigger(
    on_person_detected: Callable,
    confidence_threshold: float = 0.5,
    cooldown_seconds: float = 0.5,
) -> TriggerRule:
    """
    Create trigger for emergency stop when person detected.
    
    Args:
        on_person_detected: Callback function to execute (e.g., robot.emergency_stop())
        confidence_threshold: Minimum confidence to trigger (default 0.5)
        cooldown_seconds: Minimum time between triggers (default 0.5s)
    
    Returns:
        TriggerRule configured for emergency stop
    """
    return TriggerRule(
        class_names=["person"],
        condition=TriggerCondition.CONFIDENCE_ABOVE,
        threshold=confidence_threshold,
        action=TriggerAction.CUSTOM,
        custom_callback=on_person_detected,
        enabled=True,
        cooldown_seconds=cooldown_seconds,
        description="Emergency Stop - Person Detected",
    )


def create_inventory_counter(
    product_classes: List[str],
    on_count_update: Callable,
) -> TriggerRule:
    """
    Create trigger for counting products.
    
    Args:
        product_classes: List of product class names (e.g., ["bottle", "box"])
        on_count_update: Callback receives (rule, detections) with count
    
    Returns:
        TriggerRule configured for counting
    """
    return TriggerRule(
        class_names=product_classes,
        condition=TriggerCondition.DETECTED,
        action=TriggerAction.CUSTOM,
        custom_callback=on_count_update,
        enabled=True,
        cooldown_seconds=0.1,  # Count frequently
        description=f"Count {', '.join(product_classes)}",
    )


def create_defect_alert(
    defect_class: str,
    on_defect_found: Callable,
    confidence_threshold: float = 0.7,
) -> TriggerRule:
    """
    Create trigger for defect detection.
    
    Args:
        defect_class: Name of defect class (e.g., "defect", "damage")
        on_defect_found: Callback function
        confidence_threshold: Minimum confidence (default 0.7 for defects)
    
    Returns:
        TriggerRule configured for defect alerts
    """
    return TriggerRule(
        class_names=[defect_class],
        condition=TriggerCondition.CONFIDENCE_ABOVE,
        threshold=confidence_threshold,
        action=TriggerAction.CUSTOM,
        custom_callback=on_defect_found,
        enabled=True,
        cooldown_seconds=2.0,
        description=f"Alert on {defect_class}",
    )


__all__ = [
    "VisionActionTrigger",
    "TriggerRule",
    "TriggerAction",
    "TriggerCondition",
    "create_emergency_stop_trigger",
    "create_inventory_counter",
    "create_defect_alert",
]

