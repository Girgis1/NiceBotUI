"""
Resilient Motor Bus Wrapper
Handles transient power brownout errors gracefully with retry logic
"""

import time
from typing import Any, Optional


class ResilientMotorBus:
    """
    Wrapper around motor bus that handles transient voltage errors gracefully.
    
    Key features:
    - Configurable retry logic with exponential backoff
    - Per-motor failure tracking
    - Graceful degradation (continue with healthy motors)
    - Automatic recovery detection
    """
    
    # Retry configuration
    MAX_RETRIES = 5  # Try up to 5 times for transient errors
    RETRY_DELAY_BASE = 0.05  # Start with 50ms delay
    RETRY_DELAY_MAX = 0.5  # Cap delay at 500ms
    BACKOFF_MULTIPLIER = 1.5  # Exponential backoff factor
    
    # Recovery tracking
    RECOVERY_CHECK_INTERVAL = 1.0  # Check failed motors every 1 second
    MAX_CONSECUTIVE_FAILURES = 10  # After this, consider motor permanently failed
    
    # Error types to retry
    RETRYABLE_ERRORS = [
        "Input voltage error",
        "Incorrect status packet",
        "Port is in use",
        "RxPacketError",
        "TxRxResult",
    ]
    
    def __init__(self, bus):
        """
        Args:
            bus: The underlying motor bus object (from lerobot/HomePos)
        """
        self.bus = bus
        self.motor_failures = {}  # motor_name -> {count, last_error, last_attempt, recovered}
        self.total_retries = 0
        self.successful_recoveries = 0
    
    def _is_retryable_error(self, error: Exception) -> bool:
        """Check if an error should trigger retry logic"""
        error_str = str(error)
        return any(keyword in error_str for keyword in self.RETRYABLE_ERRORS)
    
    def _should_retry_motor(self, motor_name: str) -> bool:
        """Check if we should attempt to read from a failed motor"""
        if motor_name not in self.motor_failures:
            return True  # Never failed before
        
        failure_info = self.motor_failures[motor_name]
        
        # If motor recovered, always retry
        if failure_info.get('recovered', False):
            return True
        
        # If too many consecutive failures, don't spam retries
        if failure_info['count'] >= self.MAX_CONSECUTIVE_FAILURES:
            # But check occasionally to detect recovery
            time_since_last = time.time() - failure_info['last_attempt']
            if time_since_last >= self.RECOVERY_CHECK_INTERVAL:
                return True
            return False
        
        return True
    
    def _record_failure(self, motor_name: str, error: Exception):
        """Record a motor failure"""
        if motor_name not in self.motor_failures:
            self.motor_failures[motor_name] = {
                'count': 0,
                'last_error': None,
                'last_attempt': time.time(),
                'recovered': False
            }
        
        self.motor_failures[motor_name]['count'] += 1
        self.motor_failures[motor_name]['last_error'] = str(error)
        self.motor_failures[motor_name]['last_attempt'] = time.time()
        self.motor_failures[motor_name]['recovered'] = False
    
    def _record_success(self, motor_name: str):
        """Record a successful motor read (recovery)"""
        if motor_name in self.motor_failures:
            was_failed = self.motor_failures[motor_name]['count'] > 0
            if was_failed:
                self.successful_recoveries += 1
                print(f"[RESILIENT] ✅ Motor {motor_name} recovered after {self.motor_failures[motor_name]['count']} failures")
            
            # Reset failure tracking
            self.motor_failures[motor_name] = {
                'count': 0,
                'last_error': None,
                'last_attempt': time.time(),
                'recovered': True
            }
    
    def read(self, register: str, motor_name: str, normalize: bool = True) -> Optional[Any]:
        """
        Read from motor with retry logic
        
        Args:
            register: Register name (e.g., "Present_Position")
            motor_name: Motor name
            normalize: Whether to normalize the value
        
        Returns:
            Register value, or None if all retries failed
        """
        # Check if we should even try this motor
        if not self._should_retry_motor(motor_name):
            return None
        
        delay = self.RETRY_DELAY_BASE
        last_error = None
        
        for attempt in range(self.MAX_RETRIES):
            try:
                value = self.bus.read(register, motor_name, normalize=normalize)
                
                # Success! Record it
                self._record_success(motor_name)
                
                if attempt > 0:
                    # Log recovery after retry
                    print(f"[RESILIENT] ✓ Motor {motor_name}.{register} succeeded after {attempt} retries")
                
                return value
                
            except Exception as e:
                last_error = e
                
                # Check if this is retryable
                if not self._is_retryable_error(e):
                    # Not a transient error, don't retry
                    self._record_failure(motor_name, e)
                    print(f"[RESILIENT] ❌ Motor {motor_name}.{register}: Non-retryable error: {e}")
                    return None
                
                # Transient error - retry with backoff
                if attempt < self.MAX_RETRIES - 1:
                    self.total_retries += 1
                    if attempt == 0:
                        # First retry - just log at debug level
                        pass  # Don't spam logs on first retry
                    else:
                        print(f"[RESILIENT] ⟳ Motor {motor_name}.{register} retry {attempt + 1}/{self.MAX_RETRIES} after {delay*1000:.0f}ms")
                    
                    time.sleep(delay)
                    delay = min(delay * self.BACKOFF_MULTIPLIER, self.RETRY_DELAY_MAX)
        
        # All retries exhausted
        self._record_failure(motor_name, last_error)
        print(f"[RESILIENT] ⚠️ Motor {motor_name}.{register} failed after {self.MAX_RETRIES} attempts: {last_error}")
        return None
    
    def write(self, register: str, motor_name: str, value: Any, normalize: bool = True) -> bool:
        """
        Write to motor with retry logic
        
        Args:
            register: Register name (e.g., "Goal_Position")
            motor_name: Motor name
            value: Value to write
            normalize: Whether to normalize the value
        
        Returns:
            True if successful, False if all retries failed
        """
        # Check if we should even try this motor
        if not self._should_retry_motor(motor_name):
            return False
        
        delay = self.RETRY_DELAY_BASE
        last_error = None
        
        for attempt in range(self.MAX_RETRIES):
            try:
                self.bus.write(register, motor_name, value, normalize=normalize)
                
                # Success!
                self._record_success(motor_name)
                
                if attempt > 0:
                    print(f"[RESILIENT] ✓ Motor {motor_name}.{register} write succeeded after {attempt} retries")
                
                return True
                
            except Exception as e:
                last_error = e
                
                if not self._is_retryable_error(e):
                    self._record_failure(motor_name, e)
                    print(f"[RESILIENT] ❌ Motor {motor_name}.{register} write: Non-retryable error: {e}")
                    return False
                
                if attempt < self.MAX_RETRIES - 1:
                    self.total_retries += 1
                    time.sleep(delay)
                    delay = min(delay * self.BACKOFF_MULTIPLIER, self.RETRY_DELAY_MAX)
        
        # All retries exhausted
        self._record_failure(motor_name, last_error)
        print(f"[RESILIENT] ⚠️ Motor {motor_name}.{register} write failed after {self.MAX_RETRIES} attempts: {last_error}")
        return False
    
    def read_multiple(self, register: str, motor_names: list[str], normalize: bool = True) -> dict[str, Optional[Any]]:
        """
        Read from multiple motors, continuing even if some fail
        
        Args:
            register: Register name
            motor_names: List of motor names
            normalize: Whether to normalize values
        
        Returns:
            Dict of motor_name -> value (or None if failed)
        """
        results = {}
        for motor_name in motor_names:
            results[motor_name] = self.read(register, motor_name, normalize)
        return results
    
    def get_stats(self) -> dict:
        """Get resilience statistics"""
        failed_motors = [name for name, info in self.motor_failures.items() 
                        if info['count'] > 0 and not info.get('recovered', False)]
        
        return {
            'total_retries': self.total_retries,
            'successful_recoveries': self.successful_recoveries,
            'currently_failed_motors': failed_motors,
            'failure_details': self.motor_failures
        }
    
    def print_stats(self):
        """Print resilience statistics"""
        stats = self.get_stats()
        print("\n" + "="*60)
        print("🛡️  RESILIENT MOTOR BUS STATISTICS")
        print("="*60)
        print(f"Total Retries: {stats['total_retries']}")
        print(f"Successful Recoveries: {stats['successful_recoveries']}")
        print(f"Currently Failed Motors: {len(stats['currently_failed_motors'])}")
        if stats['currently_failed_motors']:
            print(f"  Failed: {', '.join(stats['currently_failed_motors'])}")
        print("="*60 + "\n")
    
    def disconnect(self):
        """Disconnect underlying bus"""
        if hasattr(self.bus, 'disconnect'):
            self.bus.disconnect()
    
    def __getattr__(self, name):
        """Forward all other attributes to underlying bus"""
        return getattr(self.bus, name)

