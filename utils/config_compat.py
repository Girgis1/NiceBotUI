"""
Configuration compatibility layer for multi-arm support.

This module provides helper functions to access robot configuration
in both the old single-arm format and the new multi-arm array format.

Old format:
    config["robot"]["port"] = "/dev/ttyACM0"
    config["robot"]["id"] = "follower_arm"
    config["rest_position"]["positions"] = [...]

New format:
    config["robot"]["arms"][0]["port"] = "/dev/ttyACM0"
    config["robot"]["arms"][0]["id"] = "follower_arm"
    config["robot"]["arms"][0]["home_positions"] = [...]
"""

from typing import Any, Dict, Iterator, List, Optional, Tuple


def is_multi_arm_config(config: Dict[str, Any]) -> bool:
    """Check if config uses the new multi-arm array format.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        True if using new multi-arm format, False if old single-arm format
    """
    robot_cfg = config.get("robot", {})
    return "arms" in robot_cfg and isinstance(robot_cfg["arms"], list)


def get_enabled_arms(config: Dict[str, Any], arm_type: str = "robot") -> List[Dict[str, Any]]:
    """Get all enabled arms from config.
    
    Args:
        config: Configuration dictionary
        arm_type: "robot" for follower arms, "teleop" for leader arms
        
    Returns:
        List of enabled arm configurations
    """
    cfg = config.get(arm_type, {})
    
    # New format: arms array
    if "arms" in cfg and isinstance(cfg["arms"], list):
        return [arm for arm in cfg["arms"] if arm.get("enabled", True)]
    
    # Old format: single arm (treat as single enabled arm)
    if "port" in cfg:
        return [cfg]
    
    return []


def _get_arm_array(config: Dict[str, Any], arm_type: str = "robot") -> List[Dict[str, Any]]:
    """Return the canonical list of arm configs for the requested type."""
    cfg = config.get(arm_type, {})
    arms = cfg.get("arms")
    if isinstance(arms, list) and arms:
        return arms
    if "port" in cfg:
        return [cfg]
    return []


def iter_arm_configs(
    config: Dict[str, Any],
    arm_type: str = "robot",
    *,
    enabled_only: bool = False,
) -> Iterator[Tuple[int, Dict[str, Any]]]:
    """Yield ``(index, arm_config)`` pairs for the requested arm group."""
    for idx, arm in enumerate(_get_arm_array(config, arm_type)):
        if enabled_only and not arm.get("enabled", True):
            continue
        yield idx, arm


def get_active_arm_index(
    config: Dict[str, Any],
    preferred: Optional[int] = None,
    arm_type: str = "robot",
) -> int:
    """Resolve the active arm index using config hints and fallbacks."""
    arms = _get_arm_array(config, arm_type)
    if not arms:
        return 0

    def _is_valid(idx: Optional[int]) -> bool:
        return isinstance(idx, int) and 0 <= idx < len(arms) and arms[idx].get("enabled", True)

    candidates: List[Optional[int]] = [preferred]

    state = config.get("dashboard_state", {})
    state_key = "active_robot_arm_index" if arm_type == "robot" else "active_teleop_arm_index"
    candidates.append(state.get(state_key))

    cfg_hint = config.get(arm_type, {}).get("active_arm_index")
    candidates.append(cfg_hint)

    for candidate in candidates:
        if _is_valid(candidate):
            return int(candidate)  # type: ignore[arg-type]

    for idx, arm in enumerate(arms):
        if arm.get("enabled", True):
            return idx
    return 0


def set_active_arm_index(
    config: Dict[str, Any],
    arm_index: int,
    arm_type: str = "robot",
) -> int:
    """Clamp and persist the active arm index in config/dash state."""
    resolved = get_active_arm_index(config, preferred=arm_index, arm_type=arm_type)
    cfg = config.setdefault(arm_type, {})
    cfg["active_arm_index"] = resolved

    state = config.setdefault("dashboard_state", {})
    state_key = "active_robot_arm_index" if arm_type == "robot" else "active_teleop_arm_index"
    state[state_key] = resolved
    return resolved


def format_arm_label(index: int, arm_cfg: Dict[str, Any]) -> str:
    """Return a user-friendly label for the arm selection widgets."""
    arm_id = arm_cfg.get("arm_id", index + 1)
    name = arm_cfg.get("name") or f"Arm {arm_id}"
    port = arm_cfg.get("port")
    if port:
        return f"{name} ({port})"
    return name


def get_arm_config(config: Dict[str, Any], arm_index: int = 0, arm_type: str = "robot") -> Optional[Dict[str, Any]]:
    """Get configuration for a specific arm.
    
    Args:
        config: Configuration dictionary
        arm_index: Index of the arm (0 for first arm)
        arm_type: "robot" for follower arms, "teleop" for leader arms
        
    Returns:
        Arm configuration dict, or None if not found
    """
    cfg = config.get(arm_type, {})
    
    # New format: arms array
    if "arms" in cfg and isinstance(cfg["arms"], list):
        if arm_index < len(cfg["arms"]):
            return cfg["arms"][arm_index]
        return None
    
    # Old format: single arm (only valid for arm_index=0)
    if arm_index == 0 and "port" in cfg:
        return cfg
    
    return None


def get_first_enabled_arm(config: Dict[str, Any], arm_type: str = "robot") -> Optional[Dict[str, Any]]:
    """Get the first enabled arm configuration.
    
    Args:
        config: Configuration dictionary
        arm_type: "robot" for follower arms, "teleop" for leader arms
        
    Returns:
        First enabled arm config, or None if no enabled arms
    """
    enabled_arms = get_enabled_arms(config, arm_type)
    return enabled_arms[0] if enabled_arms else None


def get_arm_port(config: Dict[str, Any], arm_index: int = 0, arm_type: str = "robot") -> Optional[str]:
    """Get the port for a specific arm.
    
    Args:
        config: Configuration dictionary
        arm_index: Index of the arm (0 for first arm)
        arm_type: "robot" for follower arms, "teleop" for leader arms
        
    Returns:
        Port path string, or None if not found
    """
    arm = get_arm_config(config, arm_index, arm_type)
    return arm.get("port") if arm else None


def get_arm_id(config: Dict[str, Any], arm_index: int = 0, arm_type: str = "robot") -> Optional[str]:
    """Get the calibration ID for a specific arm.
    
    Args:
        config: Configuration dictionary
        arm_index: Index of the arm (0 for first arm)
        arm_type: "robot" for follower arms, "teleop" for leader arms
        
    Returns:
        Calibration ID string, or None if not found
    """
    arm = get_arm_config(config, arm_index, arm_type)
    return arm.get("id") if arm else None


def get_arm_type_name(config: Dict[str, Any], arm_index: int = 0, arm_type: str = "robot") -> Optional[str]:
    """Get the robot type for a specific arm.
    
    Args:
        config: Configuration dictionary
        arm_index: Index of the arm (0 for first arm)
        arm_type: "robot" for follower arms, "teleop" for leader arms
        
    Returns:
        Robot type string (e.g., "so100_follower"), or None if not found
    """
    arm = get_arm_config(config, arm_index, arm_type)
    return arm.get("type") if arm else None


def get_home_positions(config: Dict[str, Any], arm_index: int = 0) -> Optional[List[int]]:
    """Get home positions for a specific arm.
    
    Args:
        config: Configuration dictionary
        arm_index: Index of the arm (0 for first arm)
        
    Returns:
        List of 6 motor positions, or None if not configured
    """
    robot_cfg = config.get("robot", {})
    
    # New format: per-arm home_positions
    if "arms" in robot_cfg and isinstance(robot_cfg["arms"], list):
        if arm_index < len(robot_cfg["arms"]):
            arm = robot_cfg["arms"][arm_index]
            return arm.get("home_positions")
        return None
    
    # Old format: rest_position (only valid for arm_index=0)
    if arm_index == 0:
        rest_pos = config.get("rest_position", {})
        return rest_pos.get("positions")
    
    return None


def get_home_velocity(config: Dict[str, Any], arm_index: int = 0) -> int:
    """Get home movement velocity for a specific arm.
    
    Args:
        config: Configuration dictionary
        arm_index: Index of the arm (0 for first arm)
        
    Returns:
        Velocity value (default 600 if not configured)
    """
    robot_cfg = config.get("robot", {})
    
    # New format: per-arm home_velocity
    if "arms" in robot_cfg and isinstance(robot_cfg["arms"], list):
        if arm_index < len(robot_cfg["arms"]):
            arm = robot_cfg["arms"][arm_index]
            return arm.get("home_velocity", 600)
        return 600
    
    # Old format: rest_position velocity (only valid for arm_index=0)
    if arm_index == 0:
        rest_pos = config.get("rest_position", {})
        return rest_pos.get("velocity", 600)
    
    return 600


def set_home_positions(config: Dict[str, Any], positions: List[int], arm_index: int = 0) -> None:
    """Set home positions for a specific arm (modifies config in-place).
    
    Args:
        config: Configuration dictionary
        positions: List of 6 motor positions
        arm_index: Index of the arm (0 for first arm)
    """
    robot_cfg = config.get("robot", {})
    
    # New format: per-arm home_positions
    if "arms" in robot_cfg and isinstance(robot_cfg["arms"], list):
        if arm_index < len(robot_cfg["arms"]):
            robot_cfg["arms"][arm_index]["home_positions"] = positions
    
    # Old format: rest_position (only valid for arm_index=0)
    elif arm_index == 0:
        if "rest_position" not in config:
            config["rest_position"] = {}
        config["rest_position"]["positions"] = positions


def migrate_to_multi_arm(config: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate old single-arm config to new multi-arm format with solo/bimanual mode.
    
    Args:
        config: Configuration dictionary in old format
        
    Returns:
        New configuration dictionary with arms array and mode
    """
    if is_multi_arm_config(config):
        # Already in new format, but ensure arm_id and mode exist
        robot_cfg = config.get("robot", {})
        if "arms" in robot_cfg:
            # Add mode if missing (default to solo)
            if "mode" not in robot_cfg:
                robot_cfg["mode"] = "solo"
            
            for i, arm in enumerate(robot_cfg["arms"]):
                if "arm_id" not in arm:
                    arm["arm_id"] = i + 1  # 1-indexed arm IDs
        
        teleop_cfg = config.get("teleop", {})
        if "arms" in teleop_cfg:
            # Add mode if missing (default to solo)
            if "mode" not in teleop_cfg:
                teleop_cfg["mode"] = "solo"
            
            for i, arm in enumerate(teleop_cfg["arms"]):
                if "arm_id" not in arm:
                    arm["arm_id"] = i + 1
        
        return config
    
    # Migrate robot config
    robot_cfg = config.get("robot", {})
    if "port" in robot_cfg:
        arm1 = {
            "enabled": True,
            "name": "Follower 1",
            "type": robot_cfg.get("type", "so100_follower"),
            "port": robot_cfg["port"],
            "id": robot_cfg.get("id", "follower_arm"),
            "arm_id": 1,
            "home_positions": [],
            "home_velocity": 600
        }
        
        # Migrate old rest_position to home_positions
        rest_pos = config.get("rest_position", {})
        if "positions" in rest_pos:
            arm1["home_positions"] = rest_pos["positions"]
        if "velocity" in rest_pos:
            arm1["home_velocity"] = rest_pos["velocity"]
        
        # Create a second arm slot (disabled by default)
        arm2 = {
            "enabled": False,
            "name": "Follower 2",
            "type": "so100_follower",
            "port": "/dev/ttyACM1",
            "id": "follower_arm_2",
            "arm_id": 2,
            "home_positions": [2082, 1106, 2994, 2421, 1044, 2054],
            "home_velocity": 600
        }
        
        # Keep shared settings, replace with arms array and mode
        new_robot_cfg = {
            "mode": "solo",  # Default to solo mode
            "arms": [arm1, arm2],
            "fps": robot_cfg.get("fps", 60),
            "min_time_to_move_multiplier": robot_cfg.get("min_time_to_move_multiplier", 3.0),
            "enable_motor_torque": robot_cfg.get("enable_motor_torque", True),
            "position_tolerance": robot_cfg.get("position_tolerance", 45),
            "position_verification_enabled": robot_cfg.get("position_verification_enabled", True)
        }
        config["robot"] = new_robot_cfg
        
        # Remove old rest_position
        if "rest_position" in config:
            del config["rest_position"]
    
    # Migrate teleop config
    teleop_cfg = config.get("teleop", {})
    if "port" in teleop_cfg:
        arm1 = {
            "enabled": True,
            "name": "Leader 1",
            "type": teleop_cfg.get("type", "so100_leader"),
            "port": teleop_cfg["port"],
            "id": teleop_cfg.get("id", "leader_arm"),
            "arm_id": 1
        }
        arm2 = {
            "enabled": False,
            "name": "Leader 2",
            "type": "so100_leader",
            "port": "/dev/ttyACM3",
            "id": "leader_arm_2",
            "arm_id": 2
        }
        config["teleop"] = {
            "mode": "solo",
            "arms": [arm1, arm2]
        }
    elif "arms" not in teleop_cfg:
        # No teleop configured, create empty structure
        config["teleop"] = {
            "mode": "solo",
            "arms": []
        }
    
    return config


def ensure_multi_arm_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure config is in multi-arm format, migrating if necessary.
    
    This is a convenience function that can be called at app startup.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        Configuration in multi-arm format
    """
    return migrate_to_multi_arm(config)
