"""
Simple Window API - Clean interface for window management
"""
import sys
from pathlib import Path
from typing import Optional, Tuple, List, Dict

# Add parent directory to path to access the top-level 'utils' package
sys.path.append(str(Path(__file__).parent.parent))

try:
    # This will import the correct controller (Mac or Win) based on OS
    from utils import WindowController
except ImportError as e:
    print(f"Error: {e}")
    print("Could not import the appropriate WindowController for your OS.")
    sys.exit(1)

class SimpleWindowAPI:
    """
    A simplified, unified API for interacting with GUI elements.
    This class acts as a wrapper around the OS-specific WindowController.
    """

    def __init__(self):
        """Initialize the API by creating an instance of the correct controller."""
        self.controller = WindowController()
        # Initial refresh to populate window list
        self.refresh()
    
    def refresh(self):
        """Refresh the window list and internal lookup tables."""
        self.controller.refresh_windows()
    
    # Window Discovery
    def get_windows(self) -> Dict:
        """Get all windows - returns clean dictionary"""
        self.refresh()
        return self.controller.window_lookup
    
    def find_window(self, title_substring: str) -> Optional[str]:
        """Find the first window ID whose title contains the given substring (case-insensitive)."""
        self.refresh()  # Always get the latest window list
        title_substring_lower = title_substring.lower()

        for window_id, info in self.controller.window_lookup.items():
            window_title = info['window_data'].get('title', '').lower()
            if title_substring_lower in window_title:
                return info['full_id']
        return None
    
    def list_windows(self):
        """Print all windows with their IDs for easy discovery"""
        self.controller.print_windows_summary()
    
    # Window Control (return True/False for simplicity)
    def focus_window(self, window_id: str) -> bool:
        """Focus a window"""
        success, _ = self.controller._execute_single_command(f"{window_id} f")
        return success
    
    def close_window(self, window_id: str) -> bool:
        """Close a window"""
        short_id = window_id[-8:]
        success, _ = self.controller._execute_single_command(f"{short_id} c")
        return success
    
    def minimize_window(self, window_id: str) -> bool:
        """Minimize a window"""
        success, _ = self.controller._execute_single_command(f"{window_id} m")
        return success
    
    def maximize_window(self, window_id: str) -> bool:
        """Maximize a window"""
        short_id = window_id[-8:]
        success, _ = self.controller._execute_single_command(f"{short_id} M")
        return success
    
    def resize_window(self, window_id: str, width: int, height: int) -> bool:
        """Resize a window"""
        success, _ = self.controller._execute_single_command(f"{window_id} resize {width} {height}")
        return success
    
    def move_window(self, window_id: str, x: int, y: int) -> bool:
        """Move a window. Note: This is a direct move, not display relative."""
        short_id = window_id[-8:]
        # The base controllers do not have a direct 'move' command string, so we need to call the method.
        # This requires getting the internal handle/number, which is a bit tricky.
        # For now, we will use the display-relative move command.
        # This assumes we want to move it on its current display.
        window_info = self.get_window_info(window_id)
        if not window_info:
            return False
        
        display_id = window_info['window_data'].get('display', 1)
        
        # We need the position relative to the display, not absolute.
        # This is a simplification; a true 'move' would need direct access.
        # For now, we assume the x,y are relative to the top-left of the display.
        return self.move_window_to_display_pos(window_id, display_id, x, y)
    
    def move_window_to_display_pos(self, window_id: str, display_id: int, x: int, y: int) -> bool:
        """Move window to a specific position on a given display."""
        short_id = window_id[-8:]
        success, _ = self.controller._execute_single_command(f"{short_id} move:{display_id}:{x},{y}")
        return success
    
    # Mouse Control
    def click(self, x: int, y: int, button: str = "left") -> bool:
        """Perform a mouse click."""
        success, _ = self.controller._execute_single_command(f"click {button} {x} {y}")
        return success
    
    def double_click(self, x: int = None, y: int = None, button: str = "left") -> bool:
        """Double click at position"""
        if x is not None and y is not None:
            success, _ = self.controller._execute_single_command(f"doubleclick {button} {x} {y}")
        else:
            success, _ = self.controller._execute_single_command(f"doubleclick {button}")
        return success
    
    def long_click(self, duration: float = 1.0, x: int = None, y: int = None, button: str = "left") -> bool:
        """Long click (hold) at position"""
        if x is not None and y is not None:
            success, _ = self.controller._execute_single_command(f"longclick {button} {duration} {x} {y}")
        else:
            success, _ = self.controller._execute_single_command(f"longclick {button} {duration}")
        return success
    
    def drag(self, start_x: int, start_y: int, end_x: int, end_y: int, button: str = "left", duration: float = 0.5) -> bool:
        """Drag from start to end position"""
        success, _ = self.controller._execute_single_command(f"drag {start_x} {start_y} {end_x} {end_y} {button} {duration}")
        return success
    
    def scroll(self, direction: str, amount: int = 3, x: int = None, y: int = None) -> bool:
        """Scroll up/down/left/right"""
        if x is not None and y is not None:
            success, _ = self.controller._execute_single_command(f"scroll {direction} {amount} {x} {y}")
        else:
            success, _ = self.controller._execute_single_command(f"scroll {direction} {amount}")
        return success
    
    # Keyboard Control
    def type_text(self, text: str) -> bool:
        """Type text"""
        success, _ = self.controller._execute_single_command(f"type {text}")
        return success
    
    def send_keys(self, keys: str) -> bool:
        """Send key combination (e.g., 'ctrl+c', 'alt+tab')"""
        success, _ = self.controller._execute_single_command(f"send {keys}")
        return success
    
    # Cursor Control
    def get_cursor_position(self) -> Optional[Tuple[int, int]]:
        """Get current cursor position"""
        success, message, pos = self.controller.wm.get_cursor_position()
        return pos if success else None
    
    def set_cursor_position(self, x: int, y: int) -> bool:
        """Set cursor position"""
        success, _ = self.controller._execute_single_command(f"cursor {x} {y}")
        return success
    
    # Introspection and Detection
    def inspect_cursor(self) -> Tuple[bool, str]:
        """Inspect element under cursor"""
        return self.controller._execute_single_command('hover')
    
    def inspect_window(self, window_id: str) -> Tuple[bool, str]:
        """Inspect specific window"""
        short_id = window_id[-8:]
        if short_id not in self.controller.window_lookup:
            return False, f"Window ID '{short_id}' not found"
        
        # This requires the hwnd/window_number, which we can get from the lookup
        window_info = self.controller.window_lookup[short_id]['window_data']
        internal_id = window_info.get('hwnd') or window_info.get('window_number')

        if hasattr(self.controller.wm, 'introspect_window'):
             return self.controller.wm.introspect_window(internal_id)
        return False, "Introspection not available"
    
    def get_window_hierarchy(self, window_id: str) -> Tuple[bool, str]:
        """Get window hierarchy tree"""
        short_id = window_id[-8:]
        success, message = self.controller._execute_single_command(f"{short_id} tree")
        return success, message
    
    # System Information
    def get_computer_name(self) -> str:
        """Get computer name"""
        success, message = self.controller._execute_single_command("computer")
        return message if success else ""
    
    def get_user_name(self) -> str:
        """Get current user name"""
        success, message = self.controller._execute_single_command("user")
        return message if success else ""
    
    # Application Launcher
    def launch_app(self, app_name: str, screen_id: int, fullscreen: bool = True) -> bool:
        """Launch application on specific screen"""
        mode = "fullscreen" if fullscreen else "normal"
        success, _ = self.controller._execute_single_command(f"launch \"{app_name}\" {screen_id} {mode}")
        return success
    
    # Message Box
    def show_message(self, title: str, message: str, x: int = None, y: int = None) -> bool:
        """Show message box"""
        if x is not None and y is not None:
            success, _ = self.controller._execute_single_command(f"msgbox {title} {message} {x} {y}")
        else:
            success, _ = self.controller._execute_single_command(f"msgbox {title} {message}")
        return success
    
    # Command Chaining
    def execute_chain(self, commands: List[str]) -> bool:
        """Execute a chain of commands"""
        command_string = " : ".join(commands)
        continue_running, message = self.controller.process_command(command_string)
        print(message)  # Print the chain execution results
        return continue_running
    
    # Utility Methods
    def get_window_info(self, window_id: str) -> Optional[Dict]:
        """Get detailed window information"""
        self.refresh()
        # The window_id from find_window is the full one, but our lookup uses the last 8 chars
        short_id = window_id[-8:]
        return self.controller.window_lookup.get(short_id)
    
    def get_window_state(self, window_id: str) -> str:
        """Get window state (maximized, minimized, normal)"""
        short_id = window_id[-8:]
        success, message = self.controller._execute_single_command(f"{short_id} s")
        if success:
            # Message is "State: NORMAL | Size: 100x100", extract the state
            try:
                return message.split('|')[0].split(':')[1].strip().lower()
            except IndexError:
                return "unknown"
        return "unknown"
    
    def get_window_position(self, window_id: str) -> Optional[Tuple[int, int]]:
        """Get window position"""
        info = self.get_window_info(window_id)
        if info:
            pos = info['window_data']['position']
            return (pos['x'], pos['y'])
        return None
    
    def get_window_size(self, window_id: str) -> Optional[Tuple[int, int]]:
        """Get window size"""
        info = self.get_window_info(window_id)
        if info:
            size = info['window_data']['size']
            return (size['width'], size['height'])
        return None
    
    def move_window_to_monitor(self, window_id: str, monitor_id: int) -> bool:
        """Move window to specific monitor"""
        success, _ = self.controller._execute_single_command(f"{window_id} monitor {monitor_id}")
        return success
    
    def send_esc_enhanced(self) -> bool:
        """Enhanced ESC key for dialogs and modal windows"""
        success, _ = self.controller.wm.send_esc_enhanced()
        return success

# Convenience function for quick access
def get_window_api() -> SimpleWindowAPI:
    """Get a SimpleWindowAPI instance"""
    return SimpleWindowAPI()

# Quick test function
def quick_test():
    """Quick test to verify the API works"""
    print("🚀 Testing Simple Window API...")
    api = get_window_api()
    
    # List available windows
    print("\n📋 Available Windows:")
    api.list_windows()
    
    # Get cursor position
    pos = api.get_cursor_position()
    print(f"\n🖱️ Current cursor position: {pos}")
    
    # Get system info
    computer = api.get_computer_name()
    user = api.get_user_name()
    print(f"\n💻 System: {computer} (User: {user})")
    
    print("\n✅ Simple Window API is working!")

if __name__ == "__main__":
    quick_test()
