"""
Resilient Motor Controller - OPTIONAL wrapper for handling transient errors

This is a SEPARATE implementation that you can opt-in to use.
Your existing MotorController remains UNCHANGED and UNAFFECTED.

Usage (Opt-in):
    from utils.resilient_motor_controller import ResilientMotorController
    
    # Use this instead of MotorController
    controller = ResilientMotorController(config, arm_index=0)
    
    # Everything else works the same
    controller.connect()
    positions = controller.read_positions()
"""

from utils.motor_controller import MotorController
from utils.resilient_motor_bus import ResilientMotorBus
import time


class ResilientMotorController(MotorController):
    """
    Extended MotorController with resilient error handling.
    
    ONLY use this if you want the resilient behavior.
    Your existing MotorController is UNCHANGED.
    """
    
    def __init__(self, config: dict = None, arm_index: int = 0, enable_resilience: bool = True):
        """
        Args:
            config: Robot configuration dict
            arm_index: Index of arm to control
            enable_resilience: If False, behaves exactly like MotorController
        """
        super().__init__(config, arm_index)
        self.enable_resilience = enable_resilience
        self._last_known_positions = [None] * 6
        self._logged_failures = set()
    
    def connect(self):
        """Connect to motor bus with optional resilience wrapper"""
        if not super().connect():
            return False
        
        # Only wrap if resilience is enabled
        if self.enable_resilience and self.bus:
            from utils.resilient_motor_bus import ResilientMotorBus
            if isinstance(self.bus, ResilientMotorBus):
                return True
            print(f"[RESILIENT] Wrapping bus with resilient layer (max {ResilientMotorBus.MAX_RETRIES} retries)")
            self.bus = ResilientMotorBus(self.bus)
        
        return True
    
    def read_positions_from_bus(self) -> list[int]:
        """
        Read positions with optional resilient fallback
        
        If resilience enabled: Uses last known positions as fallback
        If resilience disabled: Original behavior (raises exception on error)
        """
        if not self.enable_resilience:
            # Original behavior - no resilience
            return super().read_positions_from_bus()
        
        # Resilient behavior
        if not self.bus:
            return []
        
        positions = []
        failed_count = 0
        
        for idx, name in enumerate(self.motor_names):
            try:
                pos = self.bus.read("Present_Position", name, normalize=False)
                
                if pos is not None:
                    # Success - update last known position
                    self._last_known_positions[idx] = int(pos)
                    positions.append(int(pos))
                    
                    # Clear failure flag if this motor was previously failing
                    if idx in self._logged_failures:
                        self._logged_failures.discard(idx)
                        print(f"[RESILIENT] ✅ Motor {idx+1} ({name}) recovered")
                else:
                    # Failed - use fallback
                    self._handle_motor_read_failure(idx, name, "Returned None")
                    failed_count += 1
                    positions.append(self._get_fallback_position(idx, name))
                    
            except Exception as e:
                # Exception - use fallback
                self._handle_motor_read_failure(idx, name, str(e))
                failed_count += 1
                positions.append(self._get_fallback_position(idx, name))
        
        # Only return empty if ALL motors failed and we have no history
        if failed_count == 6 and all(p is None for p in self._last_known_positions):
            print(f"[RESILIENT] ❌ All motors failed to read with no position history")
            return []
        
        return positions
    
    def _handle_motor_read_failure(self, idx: int, name: str, error: str):
        """Handle a motor read failure"""
        # Only log the first failure, not subsequent ones
        if idx not in self._logged_failures:
            self._logged_failures.add(idx)
            print(f"[RESILIENT] ⚠️ Motor {idx+1} ({name}) failed: {error}")
    
    def _get_fallback_position(self, idx: int, name: str) -> int:
        """Get fallback position for a failed motor"""
        if self._last_known_positions[idx] is not None:
            # Use last known position
            return self._last_known_positions[idx]
        else:
            # Never successfully read this motor - use 0 as safe default
            print(f"[RESILIENT] ⚠️ Motor {idx+1} ({name}) has no position history, using 0")
            return 0
    
    def disconnect(self):
        """Disconnect and optionally print stats"""
        if self.bus and self.enable_resilience:
            try:
                if isinstance(self.bus, ResilientMotorBus):
                    stats = self.bus.get_stats()
                    if stats['total_retries'] > 0 or stats['successful_recoveries'] > 0:
                        self.bus.print_stats()
            except:
                pass
        
        super().disconnect()


# Configuration helper
def create_motor_controller(config: dict = None, arm_index: int = 0, resilient: bool = False):
    """
    Factory function to create the appropriate motor controller
    
    Args:
        config: Robot configuration
        arm_index: Arm index
        resilient: If True, use ResilientMotorController. If False, use standard MotorController.
    
    Returns:
        MotorController or ResilientMotorController
    """
    if resilient:
        return ResilientMotorController(config, arm_index, enable_resilience=True)
    else:
        return MotorController(config, arm_index)
