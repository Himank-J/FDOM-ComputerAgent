import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from windowManager.window_manager import WindowManager
import json
from typing import Tuple, List, Optional


class WindowController:
    def __init__(self):
        self.wm = WindowManager()
        self.window_lookup = {}  # Maps last 8 digits to full window data
        self.previous_window_ids = {}  # Track ID changes: hwnd -> previous_id
    
    def refresh_windows(self):
        """Refresh window data and update lookup table"""
        data = self.wm.get_structured_windows()
        self.window_lookup = {}
        
        # Build lookup table with last 8 digits of window ID
        for monitor_data in data["monitors"].values():
            for app_data in monitor_data["applications"].values():
                for window_id, window_data in app_data["windows"].items():
                    last_8 = window_id[-8:]
                    self.window_lookup[last_8] = {
                        'window_data': window_data,
                        'app_name': app_data['process_name'],
                        'full_id': window_id
                    }
        
        return data
    
    def print_windows_summary(self):
        """Print a clean summary of all windows organized by screen"""
        # Use the WindowManager's built-in structured output instead of duplicating logic
        self.refresh_windows()
        self.wm.print_structured_output(show_minimized=True)
        
        # Add the window ID legend for our command system
        print("\n💡 TIP: Use the last 8 characters of any Window ID for commands")
        print("   Example: If ID is 'window_12345678_abcdefgh', use 'abcdefgh' for commands")
    
    def _parse_mouse_args(self, parts: List[str], start_idx: int = 1) -> Tuple[str, Optional[int], Optional[int]]:
        """Parse common mouse command arguments (button, x, y)"""
        button = "left"
        x, y = None, None
        
        current_idx = start_idx
        
        # Check if first argument is a button type
        if (current_idx < len(parts) and 
            parts[current_idx].lower() in ['left', 'right', 'middle']):
            button = parts[current_idx].lower()
            current_idx += 1
        
        # Check for coordinates
        if current_idx + 1 < len(parts):
            try:
                x, y = int(parts[current_idx]), int(parts[current_idx + 1])
            except ValueError:
                pass
        
        return button, x, y
    
    def _handle_introspection_command(self, hwnd: Optional[int] = None) -> Tuple[bool, str]:
        """Handle both global and window-specific introspection commands"""
        if hwnd:
            return self.wm.introspect_window(hwnd)
        else:
            return self.wm.get_element_under_cursor()
    
    def _execute_single_command(self, command_str: str) -> Tuple[bool, str]:
        """Execute a single command - internal method for chaining"""
        parts = command_str.strip().split()
        if not parts:
            return False, "Empty command"
        
        # Global introspection commands (don't need window ID)
        if parts[0].lower() in ['hover', 'detect', 'inspect']:
            return self._handle_introspection_command()
        
        # Cursor commands
        elif parts[0].lower() == 'cursor':
            if len(parts) == 1:
                success, message, pos = self.wm.get_cursor_position()
                return success, message
            elif len(parts) == 3:
                try:
                    x, y = int(parts[1]), int(parts[2])
                    return self.wm.set_cursor_position(x, y)
                except ValueError:
                    return False, "Invalid cursor coordinates"
            else:
                return False, "Invalid cursor command"
        
        # Mouse commands - using helper for parsing
        elif parts[0].lower() == 'click':
            button, x, y = self._parse_mouse_args(parts)
            return self.wm.send_mouse_click(button, x, y)
        
        elif parts[0].lower() == 'doubleclick':
            button, x, y = self._parse_mouse_args(parts)
            return self.wm.send_mouse_double_click(button, x, y)
        
        elif parts[0].lower() == 'longclick':
            button = "left"
            duration = 1.0
            x, y = None, None
            
            try:
                if len(parts) >= 2 and parts[1].lower() in ['left', 'right', 'middle']:
                    button = parts[1].lower()
                    if len(parts) >= 3:
                        duration = float(parts[2])
                    if len(parts) >= 5:
                        x, y = int(parts[3]), int(parts[4])
                elif len(parts) >= 2:
                    duration = float(parts[1])
                    if len(parts) >= 4:
                        x, y = int(parts[2]), int(parts[3])
                
                return self.wm.send_mouse_long_click(button, duration, x, y)
            except ValueError:
                return False, "Invalid longclick parameters"
        
        # Scroll commands
        elif parts[0].lower() == 'scroll':
            if len(parts) < 2:
                return False, "Missing scroll direction"
            
            direction = parts[1].lower()
            amount = 3
            x, y = None, None
            
            try:
                if len(parts) >= 3 and parts[2].isdigit():
                    amount = int(parts[2])
                if len(parts) >= 5:
                    x, y = int(parts[3]), int(parts[4])
                elif len(parts) >= 4 and not parts[2].isdigit():
                    x, y = int(parts[2]), int(parts[3])
                
                return self.wm.send_mouse_scroll(direction, amount, x, y)
            except ValueError:
                return False, "Invalid scroll parameters"
        
        # Drag commands
        elif parts[0].lower() == 'drag':
            if len(parts) < 5:
                return False, "Missing drag coordinates"
            
            try:
                x1, y1, x2, y2 = int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])
                button = "left"
                duration = 0.5
                
                if len(parts) >= 6 and parts[5].lower() in ['left', 'right', 'middle']:
                    button = parts[5].lower()
                if len(parts) >= 7:
                    duration = float(parts[6])
                elif len(parts) >= 6 and parts[5].replace('.', '').isdigit():
                    duration = float(parts[5])
                
                return self.wm.send_mouse_drag(x1, y1, x2, y2, button, duration)
            except ValueError:
                return False, "Invalid drag parameters"
        
        # Keyboard commands
        elif parts[0].lower() == 'send':
            if len(parts) < 2:
                return False, "Missing key combination"
            
            key_combo = ' '.join(parts[1:])
            return self.wm.send_key_combination(key_combo)
        
        elif parts[0].lower() == 'type':
            if len(parts) < 2:
                return False, "Missing text to type"
            
            text = ' '.join(parts[1:])
            return self.wm.send_text(text)
        
        # System commands
        elif parts[0].lower() == 'computer':
            return self.wm.get_computer_name()
        
        elif parts[0].lower() == 'user':
            return self.wm.get_user_name()
        
        elif parts[0].lower() == 'keys':
            return self.wm.get_virtual_key_codes()
        
        # Message box command
        elif parts[0].lower() == 'msgbox':
            if len(parts) < 3:
                return False, "Missing msgbox parameters"
            
            title = parts[1]
            if len(parts) >= 6 and parts[-2:][0].isdigit():
                try:
                    x, y = int(parts[-2]), int(parts[-1])
                    text = ' '.join(parts[2:-2])
                    return self.wm.show_message_box(title, text, x, y)
                except ValueError:
                    text = ' '.join(parts[2:])
                    return self.wm.show_message_box(title, text)
            else:
                text = ' '.join(parts[2:])
                return self.wm.show_message_box(title, text)
        
        # Application launcher command
        elif parts[0].lower() == 'launch':
            if len(parts) < 3:
                return False, "Missing launch parameters. Usage: launch APP_NAME SCREEN_ID [normal]"
            
            app_name = parts[1]
            try:
                screen_id = int(parts[2])
                fullscreen = True if len(parts) < 4 else parts[3].lower() != 'normal'
                return self.wm.launch_application(app_name, screen_id, fullscreen)
            except ValueError:
                return False, "Invalid screen ID"
        
        # Window commands (require window ID)
        elif len(parts) >= 2:
            window_id_suffix = parts[0]
            command = parts[1]
            
            # Find window
            if window_id_suffix not in self.window_lookup:
                return False, f"Window ID '{window_id_suffix}' not found"
            
            window_info = self.window_lookup[window_id_suffix]
            window_data = window_info['window_data']
            hwnd = window_data['hwnd']
            
            # Execute window command
            if command == 'm':
                return self.wm.minimize_window(hwnd)
            elif command == 'M':
                return self.wm.maximize_window(hwnd)
            elif command.lower() == 'c':
                return self.wm.close_window(hwnd)
            elif command.lower() == 'f':
                return self.wm.smart_foreground(hwnd)
            elif command.lower() == 's':
                current_state = self.wm.get_window_state(hwnd)
                return True, f"Size: {window_data['size']['width']}x{window_data['size']['height']} | State: {current_state.upper()}"
            elif command.lower() == 'l':
                current_state = self.wm.get_window_state(hwnd)
                if current_state == "minimized":
                    return True, f"Position: MINIMIZED (last: {window_data['position']['x']}, {window_data['position']['y']}) Screen {window_data['monitor']} | State: {current_state.upper()}"
                else:
                    return True, f"Position: ({window_data['position']['x']}, {window_data['position']['y']}) Screen {window_data['monitor']} | State: {current_state.upper()}"
            elif command.lower() == 'resize' and len(parts) == 4:
                try:
                    width, height = int(parts[2]), int(parts[3])
                    return self.wm.resize_window(hwnd, width, height)
                except ValueError:
                    return False, "Invalid resize dimensions"
            elif command.lower() == 'move' and len(parts) == 4:
                try:
                    x, y = int(parts[2]), int(parts[3])
                    return self.wm.move_window(hwnd, x, y)
                except ValueError:
                    return False, "Invalid move coordinates"
            elif command.lower() == 'screen' and len(parts) == 5:
                try:
                    screen_id, x, y = int(parts[2]), int(parts[3]), int(parts[4])
                    return self.wm.move_window_to_screen_position(hwnd, screen_id, x, y)
                except ValueError:
                    return False, "Invalid screen move parameters"
            elif command.lower() == 'monitor' and len(parts) == 3:
                try:
                    monitor_id = int(parts[2])
                    return self.wm.move_window_to_monitor(hwnd, monitor_id)
                except ValueError:
                    return False, "Invalid monitor ID"
            elif command in ['i', 'inspect']:
                return self._handle_introspection_command(hwnd)
            elif command.lower() == 'tree':
                return self.wm.get_window_hierarchy_tree(hwnd)
            else:
                return False, f"Unknown window command: {command}"
        
        return False, f"Unknown command: {parts[0]}"
    
    def process_command(self, user_input):
        """Process user command (supports chaining with ' : ')"""
        user_input = user_input.strip()
        
        if user_input.lower() == 'q':
            return False, "Goodbye!"
        
        if user_input.lower() == 'r':
            self.print_windows_summary()
            return True, "Window list refreshed"
        
        # Check if this is a command chain
        if ' : ' in user_input:
            commands = [cmd.strip() for cmd in user_input.split(' : ')]
            print(f"🔗 Executing command chain ({len(commands)} steps)...")
            
            overall_success = True
            
            for i, cmd in enumerate(commands):
                if not cmd:
                    continue
                
                print(f"   Step {i+1}: {cmd}")
                success, message = self._execute_single_command(cmd)
                
                if success:
                    print(f"   ✅ {message}")
                else:
                    print(f"   ❌ {message}")
                    overall_success = False
                    print(f"   ⚠️  Chain stopped at step {i+1}")
                    break
                
                # Adaptive delay based on command type
                import time
                if 'click' in cmd.lower() or 'focus' in cmd.lower() or cmd.lower().endswith('f'):
                    time.sleep(0.3)  # Longer delay after focus/click operations
                elif 'send' in cmd.lower() or 'type' in cmd.lower():
                    time.sleep(0.2)  # Medium delay for keyboard operations
                else:
                    time.sleep(0.1)  # Short delay for other operations
            
            if overall_success:
                return True, f"✅ Command chain completed successfully ({len(commands)} steps)"
            else:
                return True, f"⚠️  Command chain stopped at step {i+1}"
        
        # Single command execution
        success, message = self._execute_single_command(user_input)
        
        # Check if ID changed after operation (for window commands)
        self.refresh_windows()
        
        status = "✅" if success else "❌"
        return True, f"{status} {message}"
    
    @staticmethod
    def get_command_legend():
        """Get the command legend from external file"""
        try:
            legend_path = os.path.join(os.path.dirname(__file__), 'legend.txt')
            with open(legend_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            return "❌ Legend file not found. Please ensure legend.txt exists in the windowManager directory."
        except Exception as e:
            return f"❌ Error reading legend file: {e}"
    
    def print_legend(self):
        """Print command legend"""
        print(self.get_command_legend())
    
    def run_interactive_mode(self):
        """Run the interactive window controller"""
        print("🚀 Starting Interactive Window Manager...")
        
        # Initial display
        self.print_windows_summary()
        self.print_legend()
        
        while True:
            try:
                user_input = input("\n💻 Enter command (or 'q' to quit): ").strip()
                
                if not user_input:
                    continue
                
                continue_running, message = self.process_command(user_input)
                print(f"   {message}")
                
                if not continue_running:
                    break
                    
            except KeyboardInterrupt:
                print("\n\n👋 Interrupted by user. Goodbye!")
                break
            except Exception as e:
                print(f"❌ Error: {e}")


def main():
    """Main function to run the window controller"""
    try:
        controller = WindowController()
        controller.run_interactive_mode()
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure window_manager.py is in the correct location")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")


if __name__ == "__main__":
    main()
