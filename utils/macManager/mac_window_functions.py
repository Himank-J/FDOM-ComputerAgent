import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from macManager.mac_window_manager import MacWindowManager
import json
from typing import Tuple, List, Optional

class MacWindowController:
    def __init__(self):
        self.wm = MacWindowManager()
        self.window_lookup = {}  # Maps last 8 digits to full window data
        self.previous_window_ids = {}  # Track ID changes
    
    def refresh_windows(self):
        """Refresh window data and update lookup table"""
        data = self.wm.get_structured_windows()
        self.window_lookup = {}
        
        # Build lookup table with last 8 digits of window ID
        for display_data in data["displays"].values():
            for app_data in display_data["applications"].values():
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
        self.refresh_windows()
        self.wm.print_structured_output(show_minimized=True)
        
        print("\n💡 TIP: Use the last 8 characters of any Window ID for commands")
        print("   Example: If ID is 'window_12345678_abcdefgh', use 'abcdefgh' for commands")
    
    def _parse_mouse_args(self, parts: List[str], start_idx: int = 1) -> Tuple[str, Optional[int], Optional[int]]:
        """Parse common mouse command arguments (button, x, y)"""
        button = "left"
        x, y = None, None
        
        current_idx = start_idx
        
        if (current_idx < len(parts) and 
            parts[current_idx].lower() in ['left', 'right', 'middle']):
            button = parts[current_idx].lower()
            current_idx += 1
        
        if current_idx + 1 < len(parts):
            try:
                x, y = int(parts[current_idx]), int(parts[current_idx + 1])
            except ValueError:
                pass
        
        return button, x, y
    
    def _execute_single_command(self, command_str: str) -> Tuple[bool, str]:
        """Execute a single command"""
        parts = command_str.strip().split()
        if not parts:
            return False, "Empty command"
        
        # Global introspection commands
        if parts[0].lower() in ['hover', 'detect', 'inspect']:
            return self.wm.get_element_under_cursor()
        
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
        
        # Mouse commands
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
            except (ValueError, IndexError):
                return False, "Invalid longclick parameters"
        
        elif parts[0].lower() == 'drag':
            if len(parts) < 5:
                return False, "Missing drag coordinates. Usage: drag X1 Y1 X2 Y2 [button] [duration]"
            
            try:
                x1, y1, x2, y2 = int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])
                button = "left"
                duration = 0.5
                
                if len(parts) >= 6 and parts[5].lower() in ['left', 'right', 'middle']:
                    button = parts[5].lower()
                if len(parts) >= 7:
                    duration = float(parts[6])
                
                return self.wm.send_mouse_drag(x1, y1, x2, y2, button, duration)
            except (ValueError, IndexError):
                return False, "Invalid drag parameters"
        
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
                return False, "Missing msgbox parameters. Usage: msgbox TITLE \"MESSAGE\""
            
            title = parts[1]
            text = ' '.join(parts[2:])
            return self.wm.show_message_box(title, text)
        
        # Launch command
        elif parts[0].lower() == 'launch':
            if len(parts) < 3:
                return False, "Missing launch parameters. Usage: launch APP_NAME DISPLAY_ID [normal]"
            
            app_name = parts[1]
            try:
                display_id = int(parts[2])
                fullscreen = True if len(parts) < 4 else parts[3].lower() != 'normal'
                return self.wm.launch_application(app_name, display_id, fullscreen)
            except ValueError:
                return False, "Invalid display ID"
        
        # Window commands (require window ID)
        elif len(parts) >= 2:
            window_id_suffix = parts[0]
            command = parts[1]
            
            if window_id_suffix not in self.window_lookup:
                return False, f"Window ID '{window_id_suffix}' not found"
            
            window_info = self.window_lookup[window_id_suffix]
            window_data = window_info['window_data']
            window_number = window_data['window_number']
            
            if command == 'm':
                return self.wm.minimize_window(window_number)
            elif command == 'M':
                return self.wm.maximize_window(window_number)
            elif command.lower() == 'c':
                return self.wm.close_window(window_number)
            elif command.lower() == 'f':
                return self.wm.bring_to_foreground(window_number)
            elif command.lower() == 's':
                current_state = self.wm.get_window_state(window_number)
                size = window_data['size']
                return True, f"State: {current_state.upper()} | Size: {size['width']}x{size['height']}"
            elif command.lower() == 'l':
                pos = window_data['position']
                return True, f"Location: ({pos['x']}, {pos['y']})"
            elif command.lower() == 'resize':
                if len(parts) != 4:
                    return False, "Invalid resize command. Usage: ID resize WIDTH HEIGHT"
                try:
                    width, height = int(parts[2]), int(parts[3])
                    return self.wm.resize_window(window_number, width, height)
                except ValueError:
                    return False, "Invalid width or height for resize"
            elif command.lower() == 'tree':
                return self.wm.get_window_hierarchy_tree(window_number)
            elif command.lower().startswith('move'):
                try:
                    parts = command.split(':')
                    if len(parts) != 3:
                        return False, "Invalid move command. Use: move:DISPLAY_ID:X,Y"
                    display_id = int(parts[1])
                    x, y = map(int, parts[2].split(','))
                    return self.wm.move_window_to_screen_position(window_number, display_id, x, y)
                except (ValueError, IndexError):
                    return False, "Invalid move parameters"
            else:
                return False, f"Unknown window command: {command}"
        
        return False, "Unknown command"
    
    def process_command(self, user_input: str) -> Tuple[bool, str]:
        """Process a command string, which may contain multiple commands"""
        commands = user_input.split(';')
        results = []
        success = True
        
        for cmd in commands:
            cmd_success, message = self._execute_single_command(cmd.strip())
            success = success and cmd_success
            results.append(message)
        
        return success, '; '.join(results)
    
    @staticmethod
    def get_command_legend():
        """Return the command legend text"""
        return """
Available Commands:
------------------
Global Commands:
  cursor                     - Get cursor position
  cursor X Y                 - Move cursor to position
  click [btn] [X Y]          - Click (left/right/middle)
  doubleclick [btn] [X Y]    - Double click
  longclick [btn] [DUR] [X Y]- Long click (duration in sec)
  drag X1 Y1 X2 Y2 [btn] [DUR]- Drag mouse
  scroll up/down [amt] [X Y] - Scroll
  launch APP DISPLAY [mode]  - Launch application (mode: normal)
  send KEY+COMBO             - Send keyboard combination (e.g., cmd+c)
  type "TEXT TO TYPE"        - Type out a string of text
  hover/detect/inspect       - Get element under cursor
  keys                       - List all available virtual key names
  msgbox "TITLE" "MESSAGE"   - Show a simple message box
  computer                   - Get computer name
  user                       - Get current user name

Window Commands (use last 8 chars of window ID):
  ID m                       - Minimize window
  ID M                       - Maximize window
  ID c                       - Close window
  ID f                       - Bring to foreground
  ID s                       - Get window size and state
  ID l                       - Get window location
  ID resize WIDTH HEIGHT    - Resize window
  ID tree                     - Show window accessibility hierarchy
  ID move:DISPLAY:X,Y       - Move to position on display

Multiple commands can be chained with semicolons (;)
Example: cursor 100 100; click; type "hello"
"""
    
    def print_legend(self):
        """Print the command legend"""
        print(self.get_command_legend())
    
    def run_interactive_mode(self):
        """Run an interactive command prompt"""
        print("🖥️  Mac Window Controller Interactive Mode")
        print("Type 'help' for commands, 'list' for windows, or 'exit' to quit")
        
        while True:
            try:
                user_input = input("\n> ").strip()
                if not user_input:
                    continue
                
                if user_input.lower() == 'exit':
                    break
                elif user_input.lower() == 'help':
                    self.print_legend()
                elif user_input.lower() == 'list':
                    self.print_windows_summary()
                else:
                    success, message = self.process_command(user_input)
                    print(f"{'✅' if success else '❌'} {message}")
            
            except KeyboardInterrupt:
                print("\nUse 'exit' to quit")
            except Exception as e:
                print(f"❌ Error: {str(e)}")

def main():
    controller = MacWindowController()
    controller.run_interactive_mode()

if __name__ == "__main__":
    main()