"""
Kiosk Mode Styles - Centralized style definitions
Minimalist dark mode design for 1024x600px touchscreen
"""

# Color Palette
class Colors:
    """Minimalist dark mode color palette"""
    # Backgrounds
    BG_DARKEST = "#1a1a1a"      # Main background
    BG_DARK = "#252525"         # Panel background
    BG_MEDIUM = "#2d2d2d"       # Card background
    BG_LIGHT = "#3a3a3a"        # Hover/active
    
    # Borders
    BORDER_DARK = "#3a3a3a"
    BORDER_LIGHT = "#505050"
    
    # Text
    TEXT_PRIMARY = "#ffffff"
    TEXT_SECONDARY = "#a0a0a0"
    TEXT_DISABLED = "#606060"
    
    # Status Colors
    SUCCESS = "#4CAF50"         # Green
    SUCCESS_DARK = "#2e7d32"
    SUCCESS_HOVER = "#388E3C"
    
    ERROR = "#f44336"           # Red
    ERROR_DARK = "#c62828"
    ERROR_HOVER = "#d32f2f"
    
    INFO = "#2196F3"            # Blue
    INFO_DARK = "#1565C0"
    INFO_HOVER = "#1976D2"
    
    WARNING = "#FFC107"         # Yellow
    WARNING_DARK = "#f57f17"
    WARNING_HOVER = "#FFA000"
    
    # Status Indicators
    INDICATOR_CONNECTED = "#2e7d32"
    INDICATOR_ERROR = "#c62828"
    INDICATOR_WARNING = "#f57f17"
    INDICATOR_DISABLED = "#757575"


# Font Sizes
class FontSizes:
    """Touch-friendly font sizes"""
    HUGE = "32px"           # Giant buttons
    LARGE = "24px"          # Large buttons
    MEDIUM = "18px"         # Status text
    NORMAL = "16px"         # Body text
    SMALL = "14px"          # Secondary text


# Component Styles
class Styles:
    """Pre-defined component styles"""
    
    @staticmethod
    def get_base_style():
        """Base application style"""
        return f"""
            QWidget {{
                background-color: {Colors.BG_DARKEST};
                color: {Colors.TEXT_PRIMARY};
                font-family: "Roboto", "Segoe UI", sans-serif;
                font-size: {FontSizes.NORMAL};
            }}
        """
    
    @staticmethod
    def get_giant_button(bg_color, hover_color, text_color=Colors.TEXT_PRIMARY):
        """Giant touch-friendly button style"""
        return f"""
            QPushButton {{
                background-color: {bg_color};
                color: {text_color};
                border: none;
                border-radius: 12px;
                font-size: {FontSizes.HUGE};
                font-weight: bold;
                min-height: 150px;
                padding: 10px;
            }}
            QPushButton:hover {{
                background-color: {hover_color};
            }}
            QPushButton:pressed {{
                background-color: {bg_color};
                border: 3px solid {text_color};
            }}
            QPushButton:disabled {{
                background-color: {Colors.BG_LIGHT};
                color: {Colors.TEXT_DISABLED};
            }}
        """
    
    @staticmethod
    def get_large_button(bg_color, hover_color, text_color=Colors.TEXT_PRIMARY):
        """Large touch-friendly button style"""
        return f"""
            QPushButton {{
                background-color: {bg_color};
                color: {text_color};
                border: none;
                border-radius: 10px;
                font-size: {FontSizes.LARGE};
                font-weight: bold;
                min-height: 80px;
                min-width: 80px;
                padding: 10px 20px;
            }}
            QPushButton:hover {{
                background-color: {hover_color};
            }}
            QPushButton:pressed {{
                background-color: {bg_color};
                border: 2px solid {text_color};
            }}
            QPushButton:disabled {{
                background-color: {Colors.BG_LIGHT};
                color: {Colors.TEXT_DISABLED};
            }}
        """
    
    @staticmethod
    def get_dropdown_style():
        """Large dropdown/combobox style"""
        return f"""
            QComboBox {{
                background-color: {Colors.BG_MEDIUM};
                color: {Colors.TEXT_PRIMARY};
                border: 2px solid {Colors.BORDER_LIGHT};
                border-radius: 8px;
                padding: 10px 50px 10px 20px;
                font-size: {FontSizes.MEDIUM};
                font-weight: bold;
                min-height: 100px;
            }}
            QComboBox:hover {{
                border-color: {Colors.INFO};
            }}
            QComboBox:focus {{
                border-color: {Colors.SUCCESS};
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 50px;
                border: none;
                padding-right: 10px;
            }}
            QComboBox::down-arrow {{
                width: 0;
                height: 0;
                border-style: solid;
                border-width: 12px 10px 0 10px;
                border-color: {Colors.TEXT_PRIMARY} transparent transparent transparent;
            }}
            QComboBox QAbstractItemView {{
                background-color: {Colors.BG_MEDIUM};
                color: {Colors.TEXT_PRIMARY};
                selection-background-color: {Colors.SUCCESS};
                selection-color: {Colors.TEXT_PRIMARY};
                border: 2px solid {Colors.BORDER_LIGHT};
                font-size: {FontSizes.NORMAL};
                min-height: 60px;
            }}
            QComboBox QAbstractItemView::item {{
                min-height: 60px;
                padding: 10px;
            }}
        """
    
    @staticmethod
    def get_spinbox_style():
        """Touch-friendly spinbox style"""
        return f"""
            QSpinBox {{
                background-color: {Colors.BG_MEDIUM};
                color: {Colors.TEXT_PRIMARY};
                border: 2px solid {Colors.BORDER_LIGHT};
                border-radius: 8px;
                padding: 10px;
                font-size: {FontSizes.LARGE};
                font-weight: bold;
                min-height: 80px;
            }}
            QSpinBox:hover {{
                border-color: {Colors.INFO};
            }}
            QSpinBox:focus {{
                border-color: {Colors.SUCCESS};
            }}
            QSpinBox::up-button {{
                subcontrol-origin: border;
                subcontrol-position: top right;
                width: 60px;
                height: 40px;
                border-left: 2px solid {Colors.BORDER_LIGHT};
                border-bottom: 1px solid {Colors.BORDER_LIGHT};
                border-top-right-radius: 6px;
                background-color: {Colors.BG_LIGHT};
            }}
            QSpinBox::up-button:hover {{
                background-color: {Colors.INFO};
            }}
            QSpinBox::up-arrow {{
                width: 0;
                height: 0;
                border-style: solid;
                border-width: 0 8px 12px 8px;
                border-color: transparent transparent {Colors.TEXT_PRIMARY} transparent;
            }}
            QSpinBox::down-button {{
                subcontrol-origin: border;
                subcontrol-position: bottom right;
                width: 60px;
                height: 40px;
                border-left: 2px solid {Colors.BORDER_LIGHT};
                border-top: 1px solid {Colors.BORDER_LIGHT};
                border-bottom-right-radius: 6px;
                background-color: {Colors.BG_LIGHT};
            }}
            QSpinBox::down-button:hover {{
                background-color: {Colors.INFO};
            }}
            QSpinBox::down-arrow {{
                width: 0;
                height: 0;
                border-style: solid;
                border-width: 12px 8px 0 8px;
                border-color: {Colors.TEXT_PRIMARY} transparent transparent transparent;
            }}
        """
    
    @staticmethod
    def get_status_panel_style():
        """Status panel/card style"""
        return f"""
            QFrame {{
                background-color: {Colors.BG_MEDIUM};
                border: 1px solid {Colors.BORDER_DARK};
                border-radius: 8px;
                padding: 15px;
            }}
        """
    
    @staticmethod
    def get_log_display_style():
        """Read-only log display style"""
        return f"""
            QTextEdit {{
                background-color: {Colors.BG_DARK};
                color: {Colors.TEXT_SECONDARY};
                font-family: "Consolas", "Courier New", monospace;
                font-size: {FontSizes.SMALL};
                border: 1px solid {Colors.BORDER_DARK};
                border-radius: 6px;
                padding: 10px;
            }}
        """
    
    @staticmethod
    def get_modal_overlay_style():
        """Semi-transparent modal overlay"""
        return f"""
            QWidget {{
                background-color: rgba(0, 0, 0, 180);
            }}
        """
    
    @staticmethod
    def get_modal_panel_style():
        """Modal dialog panel style"""
        return f"""
            QFrame {{
                background-color: {Colors.BG_DARK};
                border: 2px solid {Colors.BORDER_LIGHT};
                border-radius: 15px;
                padding: 30px;
            }}
        """
    
    @staticmethod
    def get_label_style(size="normal", bold=False):
        """Label style"""
        font_size = {
            "huge": FontSizes.HUGE,
            "large": FontSizes.LARGE,
            "medium": FontSizes.MEDIUM,
            "normal": FontSizes.NORMAL,
            "small": FontSizes.SMALL
        }.get(size, FontSizes.NORMAL)
        
        weight = "bold" if bold else "normal"
        
        return f"""
            QLabel {{
                color: {Colors.TEXT_PRIMARY};
                font-size: {font_size};
                font-weight: {weight};
                background: transparent;
            }}
        """
    
    @staticmethod
    def get_status_label_style():
        """Highlighted status label"""
        return f"""
            QLabel {{
                color: {Colors.TEXT_PRIMARY};
                font-size: {FontSizes.MEDIUM};
                font-weight: bold;
                background-color: {Colors.BG_LIGHT};
                border-radius: 8px;
                padding: 15px 25px;
            }}
        """


class StatusIndicator:
    """Status indicator dot styles"""
    
    @staticmethod
    def get_style(connected=False, warning=False, disabled=False):
        """Get status indicator style based on state"""
        if disabled:
            color = Colors.INDICATOR_DISABLED
            border = Colors.BORDER_DARK
        elif warning:
            color = Colors.INDICATOR_WARNING
            border = Colors.WARNING_DARK
        elif connected:
            color = Colors.INDICATOR_CONNECTED
            border = Colors.SUCCESS_DARK
        else:
            color = Colors.INDICATOR_ERROR
            border = Colors.ERROR_DARK
        
        return f"""
            QLabel {{
                background-color: {color};
                border: 1px solid {border};
                border-radius: 10px;
                min-width: 20px;
                max-width: 20px;
                min-height: 20px;
                max-height: 20px;
            }}
        """


