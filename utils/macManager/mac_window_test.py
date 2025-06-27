#!/usr/bin/env python3
"""
Mac Window Test - Interactive interface for Mac Window Manager
Equivalent to window_test.py but for macOS
"""

import sys
import os
import time
from typing import Tuple

# Import our Mac window manager
from mac_window_manager import MacWindowManager


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
        """Print a clean summary of all windows organized by display"""
        data = self.refresh_windows()
        
        print("\n" + "="*80)
        print(f"🍎 MAC WINDOW SUMMARY - {data['summary']['total_windows']} windows across {data['summary']['total_displays']} displays")
        print("="*80)
        
        for display_key, display_data in data["displays"].items():
            main_indicator = " (MAIN)" if display_data['is_main'] else ""
            print(f"\n🖥️  DISPLAY {display_data['id']}{main_indicator} - {display_data['size']['width']}x{display_data['size']['height']}")
            print(f"   Origin: ({display_data['origin']['x']}, {display_data['origin']['y']})")
            print("-" * 60)
            
            if not display_data["applications"]:
                print("   No applications on this display")
                continue
            
            # Collect all windows for this display
            all_windows = []
            for app_name, app_data in display_data["applications"].items():
                for window_data in app_data["windows"].values():
                    all_windows.append({
                        'app': app_name,
                        'window': window_data
                    })
            
            # Sort by app name, then by title
            all_windows.sort(key=lambda x: (x['app'], x['window']['title']))
            
            current_app = None
            for item in all_windows:
                app_name = item['app']
                window = item['window']
                window_number = window['window_number']
                
                # Print app header if it's a new app
                if app_name != current_app:
                    print(f"\n   📱 {app_name}")
                    current_app = app_name
                
                # Get current window state
                current_state = self.wm.get_window_state(window_number)
                
                # Window info with state indicators
                if current_state == "minimized":
                    status = "📦 MIN"
                elif current_state == "maximized":
                    status = "🔳 MAX"
                else:
                    status = "👁️  NOR"
                
                title = window['title'][:40] + "..." if len(window['title']) > 40 else window['title']
                last_8 = window['window_id'][-8:]
                
                print(f"      {status} {title}")
                print(f"         ID: ...{last_8} | Pos: ({window['position']['x']}, {window['position']['y']}) | Size: {window['size']['width']}x{window['size']['height']}")
        
        print("\n" + "="*80)
        print("   States: 📦 MIN=Minimized | 🔳 MAX=Maximized | 👁️  NOR=Normal")
    
    def print_legend(self):
        """Print command legend for Mac"""
        print("\n📋 MAC COMMAND LEGEND:")
        print("   🪟 WINDOW COMMANDS:")
        print("   • M            - Maximize window (resize to screen)")
        print("   • m            - Minimize window") 
        print("   • c            - Close window")
        print("   • s            - Show current size & state")
        print("   • l            - Show location on display")
        print("   • f            - Bring to foreground")
        print("   • i            - Deep introspection (accessibility analysis)")
        print("   • resize W H   - Resize to width x height")
        print("   • move X Y     - Move to absolute position")
        print("   • display D    - Move to display D (centered)")
        print("\n   🔍 INTROSPECTION COMMANDS:")
        print("   • hover        - Analyze element under mouse cursor")
        print("   • inspect      - Same as 'i' - full window analysis")
        print("   • detect       - Real-time cursor element detection")
        print("\n   🖱️  CURSOR & MOUSE COMMANDS:")
        print("   • cursor       - Get current cursor position")
        print("   • cursor X Y   - Set cursor position")
        print("   • click [left|right|middle] [X Y] - Click at position or cursor")
        print("   • doubleclick [left|right|middle] [X Y] - Double click")
        print("   • longclick [left|right|middle] DURATION [X Y] - Long click (hold)")
        print("   • scroll [up|down|left|right] [AMOUNT] [X Y] - Scroll")
        print("   • drag X1 Y1 X2 Y2 [left|right|middle] [DURATION] - Drag")
        print("\n   ⌨️  KEYBOARD & SYSTEM:")
        print("   • msgbox TITLE TEXT - Show message box")
        print("   • computer     - Get computer name")
        print("   • user         - Get user name")
        print("   • keys         - Show virtual key codes (Mac)")
        print("   • send KEYS    - Send key combination (e.g., send cmd+c)")
        print("   • type TEXT    - Type text")
        print("\n   ⚡ COMMAND CHAINING:")
        print("   • Use ' : ' to chain multiple commands")
        print("   • Commands execute in sequence with small delays")
        print("   • Chain stops if any command fails")
        print("\n   🔧 CONTROL:")
        print("   • r            - Refresh window list")
        print("   • q            - Quit")
        print("\n   Examples:")
        print("   • click 500 300 : send cmd+v                     - Click then paste")
        print("   • 1a2b3c4d f : click 100 100 : type hello       - Focus, click, type")
        print("   • cursor 200 200 : click : send cmd+c : send cmd+v - Move, click, copy, paste")
        print("   • 1a2b3c4d i                                     - Deep introspect window")
        print("   • hover                                          - Analyze what's under cursor")
        print("\n   🍎 MAC-SPECIFIC NOTES:")
        print("   • Use 'cmd' instead of 'ctrl' for most shortcuts")
        print("   • Accessibility permissions required for window control")
        print("   • Some apps may not support all window operations")
        print("-" * 80)
    
    def _execute_single_command(self, command_str: str) -> Tuple[bool, str]:
        """Execute a single command - internal method for chaining"""
        parts = command_str.strip().split()
        if not parts:
            return False, "Empty command"
        
        # Global introspection commands (don't need window ID)
        if parts[0].lower() in ['hover', 'detect']:
            return self.wm.get_element_under_cursor()
        elif parts[0].lower() == 'inspect' and len(parts) == 1:
            return self.wm.get_element_under_cursor()
        
        # Window listing commands
        elif parts[0].lower() == 'windows':
            self.print_windows_summary()
            return True, "Window list displayed"
        elif parts[0].lower() == 'apps':
            data = self.refresh_windows()
            app_summary = {}
            for display_data in data["displays"].values():
                for app_name, app_data in display_data["applications"].items():
                    if app_name not in app_summary:
                        app_summary[app_name] = {"total": 0, "visible": 0, "minimized": 0}
                    app_summary[app_name]["total"] += app_data["window_count"]
                    app_summary[app_name]["visible"] += app_data["visible_count"]
                    app_summary[app_name]["minimized"] += app_data["minimized_count"]
            
            result = ["📱 APPLICATION SUMMARY:"]
            for app, counts in sorted(app_summary.items()):
                result.append(f"   {app}: {counts['total']} total | {counts['visible']} visible | {counts['minimized']} minimized")
            return True, "\n".join(result)
        elif parts[0].lower() == 'displays':
            result = ["🖥️  DISPLAY INFORMATION:"]
            for i, display in enumerate(self.wm.displays):
                main_text = " (MAIN)" if display['is_main'] else ""
                result.append(f"   Display {display['index']}{main_text}: {display['size']['width']}x{display['size']['height']} at ({display['origin']['x']}, {display['origin']['y']})")
            return True, "\n".join(result)
        elif parts[0].lower() == 'help':
            self.print_legend()
            return True, "Help displayed"
        
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
        
        # Click commands
        elif parts[0].lower() == 'click':
            button = "left"
            x, y = None, None
            
            if len(parts) >= 2 and parts[1].lower() in ['left', 'right', 'middle']:
                button = parts[1].lower()
                if len(parts) >= 4:
                    try:
                        x, y = int(parts[2]), int(parts[3])
                    except ValueError:
                        return False, "Invalid coordinates"
            elif len(parts) >= 3:
                try:
                    x, y = int(parts[1]), int(parts[2])
                except ValueError:
                    return False, "Invalid coordinates"
            
            return self.wm.send_mouse_click(button, x, y)
        
        # Double click commands
        elif parts[0].lower() == 'doubleclick':
            button = "left"
            x, y = None, None
            
            if len(parts) >= 2 and parts[1].lower() in ['left', 'right', 'middle']:
                button = parts[1].lower()
                if len(parts) >= 4:
                    try:
                        x, y = int(parts[2]), int(parts[3])
                    except ValueError:
                        return False, "Invalid coordinates"
            elif len(parts) >= 3:
                try:
                    x, y = int(parts[1]), int(parts[2])
                except ValueError:
                    return False, "Invalid coordinates"
            
            return self.wm.send_mouse_double_click(button, x, y)
        
        # Long click commands
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
            text = ' '.join(parts[2:])
            return self.wm.show_message_box(title, text)
        
        # Window commands (require window ID)
        elif len(parts) >= 2:
            window_id_part = parts[0]
            
            # Find the matching window
            target_window = None
            for key in self.window_lookup:
                if key.startswith(window_id_part.lower()):
                    target_window = self.window_lookup[key]
                    break
            
            if not target_window:
                return False, f"Window ID starting with '{window_id_part}' not found"
            
            window_data = target_window['window_data']
            window_number = window_data['window_number']
            
            if len(parts) == 1:
                return False, "No command specified for the window"
            
            command = parts[1].lower()
            
            if command == "m":
                return self.wm.minimize_window(window_number)
            elif command == "M":
                return self.wm.maximize_window(window_number)
            elif command == "c":
                return self.wm.close_window(window_number)
            elif command == "f":
                return self.wm.bring_to_foreground(window_number)
            elif command == "i":
                return self.wm.introspect_window(window_number)
            elif command == "s":
                state = self.wm.get_window_state(window_number)
                return True, f"Size: {window_data['size']['width']}x{window_data['size']['height']} | State: {state.upper()}"
            elif command == "l":
                state = self.wm.get_window_state(window_number)
                if state == "minimized":
                    return True, f"Position: MINIMIZED (last: {window_data['position']['x']}, {window_data['position']['y']}) Display {window_data['display']} | State: {state.upper()}"
                else:
                    return True, f"Position: ({window_data['position']['x']}, {window_data['position']['y']}) Display {window_data['display']} | State: {state.upper()}"
            elif command.lower() == 'resize' and len(parts) == 4:
                try:
                    width, height = int(parts[2]), int(parts[3])
                    return self.wm.resize_window(window_number, width, height)
                except ValueError:
                    return False, "Invalid resize dimensions"
            elif command.lower() == 'move' and len(parts) == 4:
                try:
                    x, y = int(parts[2]), int(parts[3])
                    return self.wm.move_window(window_number, x, y)
                except ValueError:
                    return False, "Invalid move coordinates"
            elif command.lower() == 'display' and len(parts) == 3:
                try:
                    display_id = int(parts[2])
                    return self.wm.move_window_to_display(window_number, display_id)
                except ValueError:
                    return False, "Invalid display ID"
            elif command == 'hover' or command == 'detect':
                # Analyze element under cursor
                success, result = self.wm.get_element_under_cursor()
                return success, result
            else:
                return False, f"Unknown window command: {command}"
        
        return False, f"Unknown command: {parts[0]}"
    
    def process_command(self, user_input):
        """Process user command (supports chaining with ' : ')"""
        user_input = user_input.strip()
        
        if user_input.lower() == 'q':
            return False, "Goodbye! 👋"
        
        if user_input.lower() == 'r':
            self.print_windows_summary()
            return True, "Window list refreshed"
        
        # Check if this is a command chain
        if ' : ' in user_input:
            commands = [cmd.strip() for cmd in user_input.split(' : ')]
            print(f"🔗 Executing command chain ({len(commands)} steps)...")
            
            results = []
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
    
    def run_interactive_mode(self):
        """Run the interactive Mac window controller"""
        print("🍎 Starting Interactive Mac Window Manager...")
        print("⚠️  Note: Make sure you've granted accessibility permissions!")
        print("   Go to: System Preferences → Security & Privacy → Privacy → Accessibility")
        print("   Add your terminal application (Terminal, iTerm2, etc.)")
        
        # Initial display
        self.print_windows_summary()
        self.print_legend()
        
        while True:
            try:
                user_input = input("\n🍎 Enter command (or 'q' to quit): ").strip()
                
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
                print("💡 Tip: Make sure you have accessibility permissions enabled")


def main():
    """Main function to run the Mac window controller"""
    try:
        controller = MacWindowController()
        controller.run_interactive_mode()
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Please install PyObjC:")
        print("  pip install pyobjc")
        print("  pip install pyobjc-core")
        print("  pip install pyobjc-framework-Cocoa")
        print("  pip install pyobjc-framework-Quartz")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        print("💡 Common issues:")
        print("  • Make sure you're running on macOS")
        print("  • Grant accessibility permissions to your terminal")
        print("  • Ensure PyObjC is properly installed")


if __name__ == "__main__":
    main() 