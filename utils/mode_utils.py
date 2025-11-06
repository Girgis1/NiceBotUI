"""
Utility functions for Solo/Bimanual mode handling
"""

def get_mode_icon(mode: str) -> str:
    """Get icon for mode display
    
    Args:
        mode: "solo" or "bimanual"
    
    Returns:
        Icon string: 👤 for solo, 👥 for bimanual
    """
    if mode == "bimanual":
        return "👥"
    return "👤"


def get_mode_display_name(mode: str) -> str:
    """Get display name for mode
    
    Args:
        mode: "solo" or "bimanual"
    
    Returns:
        Display name with icon
    """
    icon = get_mode_icon(mode)
    return f"{icon} {mode.capitalize()}"


def get_current_robot_mode(config: dict) -> str:
    """Get current robot mode from config
    
    Args:
        config: Application config dictionary
    
    Returns:
        "solo" or "bimanual"
    """
    return config.get("robot", {}).get("mode", "solo")


def get_current_teleop_mode(config: dict) -> str:
    """Get current teleop mode from config
    
    Args:
        config: Application config dictionary
    
    Returns:
        "solo" or "bimanual"
    """
    return config.get("teleop", {}).get("mode", "solo")


def validate_bimanual_config(config: dict) -> tuple[bool, str]:
    """Validate that bimanual mode is properly configured
    
    Args:
        config: Application config dictionary
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    robot_cfg = config.get("robot", {})
    mode = robot_cfg.get("mode", "solo")
    
    if mode != "bimanual":
        return True, ""  # Solo mode doesn't need validation
    
    # Check robot arms
    arms = robot_cfg.get("arms", [])
    if len(arms) < 2:
        return False, "Bimanual mode requires 2 robot arms configured"
    
    enabled_count = sum(1 for arm in arms if arm.get("enabled", False))
    if enabled_count < 2:
        return False, "Bimanual mode requires both robot arms enabled"
    
    # Check both arms have ports
    for i, arm in enumerate(arms[:2]):
        if not arm.get("port"):
            return False, f"Arm {i+1} is missing a port configuration"
    
    # Check teleop (if used)
    teleop_cfg = config.get("teleop", {})
    teleop_mode = teleop_cfg.get("mode", "solo")
    
    if teleop_mode == "bimanual":
        teleop_arms = teleop_cfg.get("arms", [])
        if len(teleop_arms) < 2:
            return False, "Bimanual teleop requires 2 leader arms configured"
        
        teleop_enabled = sum(1 for arm in teleop_arms if arm.get("enabled", False))
        if teleop_enabled < 2:
            return False, "Bimanual teleop requires both leader arms enabled"
    
    return True, ""

