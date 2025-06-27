# Mac Window Manager

A comprehensive macOS window management and automation system, equivalent to the Windows `window_manager.py` but designed specifically for macOS using native APIs.

## Features

### 🪟 Window Management
- **Multi-display support** - Works across multiple monitors/displays
- **Window detection** - Find and enumerate all visible windows
- **Window control** - Minimize, maximize, close, resize, move windows
- **Application grouping** - Organize windows by application and display

### 🖱️ Mouse & Cursor Automation
- **Cursor control** - Get/set cursor position across displays
- **Mouse clicks** - Left, right, middle click with position control
- **Advanced clicks** - Double-click, long-click (press and hold)
- **Mouse scrolling** - Scroll in any direction at any position
- **Mouse dragging** - Drag from point A to point B with timing control

### ⌨️ Keyboard Automation
- **Key combinations** - Send complex key combinations (e.g., `cmd+c`, `option+tab`)
- **Text input** - Type text as if entered from keyboard
- **Mac key codes** - Comprehensive mapping of macOS virtual key codes
- **Modifier keys** - Full support for Cmd, Option, Control, Shift, Fn

### 🔍 UI Introspection
- **Element detection** - Analyze UI elements under cursor (ShareX-style)
- **Window introspection** - Deep analysis of window structure and properties
- **Accessibility analysis** - Use macOS Accessibility APIs for detailed inspection
- **Application information** - Get bundle IDs, launch dates, process info

### ⚡ Advanced Features
- **Command chaining** - Execute multiple commands in sequence
- **Real-time updates** - Live window state monitoring
- **Error handling** - Graceful fallbacks and comprehensive error messages
- **JSON output** - Structured data format for integration

## Installation

### Prerequisites
1. **macOS** (tested on macOS 10.14+)
2. **Python 3.7+**
3. **PyObjC** framework

### Install Dependencies
```bash
# Install PyObjC (required for macOS APIs)
pip install pyobjc
pip install pyobjc-core
pip install pyobjc-framework-Cocoa
pip install pyobjc-framework-Quartz
pip install pyobjc-framework-ApplicationServices
```

### Grant Accessibility Permissions
⚠️ **IMPORTANT**: This tool requires accessibility permissions to control windows and input.

1. Go to **System Preferences** → **Security & Privacy** → **Privacy** → **Accessibility**
2. Click the lock icon and enter your password
3. Add your terminal application (Terminal, iTerm2, etc.) to the allowed applications
4. Restart your terminal application

## Usage

### Basic Usage
```python
from mac_window_manager import MacWindowManager

# Create window manager instance
wm = MacWindowManager()

# Get all windows organized by display and application
windows = wm.get_structured_windows()

# Print a clean summary
wm.print_structured_output()

# Find windows by application name
chrome_windows = wm.find_window_by_app("Chrome")
```

### Interactive Mode
```bash
python mac_window_test.py
```

This starts an interactive command-line interface where you can:
- View all windows organized by display
- Control windows using simple commands
- Test mouse and keyboard automation
- Perform UI introspection

### Example Commands

#### Window Control
```bash
# Refresh window list
r

# Maximize window (using last 8 digits of window ID)
1a2b3c4d M

# Minimize window
1a2b3c4d m

# Close window
1a2b3c4d c

# Bring window to foreground
1a2b3c4d f

# Get window info
1a2b3c4d s
1a2b3c4d l

# Resize window
1a2b3c4d resize 800 600

# Move window
1a2b3c4d move 100 100

# Move to display 2
1a2b3c4d display 2
```

#### Mouse Control
```bash
# Get cursor position
cursor

# Move cursor
cursor 500 300

# Click at position
click 500 300
click right 500 300

# Double click
doubleclick 500 300

# Long click (hold for 2 seconds)
longclick left 2.0 500 300

# Scroll
scroll up 5 500 300
scroll down 3

# Drag
drag 100 100 200 200 left 0.5
```

#### Keyboard Control
```bash
# Send key combinations (Mac-style)
send cmd+c
send cmd+v
send option+tab
send cmd+shift+4

# Type text
type "Hello, World!"

# Show available keys
keys
```

#### Introspection
```bash
# Analyze element under cursor
hover

# Deep window inspection
1a2b3c4d i

# Analyze current cursor position
detect
```

#### Command Chaining
```bash
# Chain multiple commands with ' : '
cursor 500 300 : click : send cmd+c : send cmd+v

# Focus window, click, and type
1a2b3c4d f : click 100 100 : type "Hello Mac!"

# Complex automation sequence
cursor 200 200 : click : send cmd+a : send cmd+c : cursor 400 400 : click : send cmd+v
```

## API Reference

### MacWindowManager Class

#### Window Management
- `get_structured_windows()` - Get all windows organized by display/app
- `find_window_by_app(app_name)` - Find windows by application name
- `is_window_valid(window_number)` - Check if window still exists
- `get_window_state(window_number)` - Get window state (normal/minimized/maximized)

#### Window Control
- `maximize_window(window_number)` - Maximize window to display size
- `minimize_window(window_number)` - Minimize window to dock
- `close_window(window_number)` - Close window
- `bring_to_foreground(window_number)` - Bring window to front
- `resize_window(window_number, width, height)` - Resize window
- `move_window(window_number, x, y)` - Move window to position
- `move_window_to_display(window_number, display_id)` - Move to display

#### Mouse Control
- `get_cursor_position()` - Get current cursor position
- `set_cursor_position(x, y)` - Move cursor to position
- `send_mouse_click(button, x, y)` - Click at position
- `send_mouse_double_click(button, x, y)` - Double-click
- `send_mouse_long_click(button, duration, x, y)` - Long-click
- `send_mouse_scroll(direction, amount, x, y)` - Scroll
- `send_mouse_drag(x1, y1, x2, y2, button, duration)` - Drag

#### Keyboard Control
- `send_key_combination(keys)` - Send key combination
- `send_text(text)` - Type text
- `get_virtual_key_codes()` - Show available key codes

#### Introspection
- `get_element_under_cursor()` - Analyze element under cursor
- `introspect_window(window_number)` - Deep window analysis

#### System Info
- `get_computer_name()` - Get Mac computer name
- `get_user_name()` - Get current user
- `show_message_box(title, message)` - Show alert dialog

## Mac-Specific Notes

### Key Differences from Windows
- Use `cmd` instead of `ctrl` for most shortcuts
- Window "maximization" on Mac means resizing to screen size (no true maximize)
- Some applications may not support all window operations
- Accessibility permissions are required for most functionality

### macOS Virtual Key Codes
The system uses macOS-specific virtual key codes:
- **Cmd/Command**: `cmd`, `command`
- **Option/Alt**: `alt`, `option`
- **Control**: `ctrl`, `control`
- **Shift**: `shift`
- **Function**: `fn`

### Common Key Combinations
- Copy: `cmd+c`
- Paste: `cmd+v`
- Cut: `cmd+x`
- Undo: `cmd+z`
- Select All: `cmd+a`
- Application Switcher: `cmd+tab`
- Screenshot: `cmd+shift+4`
- Spotlight: `cmd+space`

### Troubleshooting

#### "Accessibility permissions not granted"
1. Open System Preferences → Security & Privacy → Privacy → Accessibility
2. Add your terminal application to the list
3. Restart the terminal application

#### "macOS APIs not available"
```bash
pip install pyobjc pyobjc-core pyobjc-framework-Cocoa pyobjc-framework-Quartz
```

#### "Could not access application"
- Some applications have additional security restrictions
- Try running with administrator privileges
- Some sandboxed apps may not be controllable

#### "Window operations not working"
- Ensure the target application supports AppleScript/Accessibility
- Some apps like System Preferences have restricted automation
- Check that the window is not in full-screen mode

## Examples

### Automated Screenshot Workflow
```python
# Focus Finder, open screenshot utility, take screenshot
wm.find_window_by_app("Finder")[0]  # Get Finder window
wm.bring_to_foreground(window_number)
wm.send_key_combination("cmd+shift+4")
```

### Multi-Display Window Organization
```python
# Move all Chrome windows to display 2
chrome_windows = wm.find_window_by_app("Chrome")
for window in chrome_windows:
    wm.move_window_to_display(window['window_number'], 2)
```

### UI Testing Automation
```python
# Click, type, and submit a form
wm.send_mouse_click("left", 300, 200)
wm.send_text("test@example.com")
wm.send_key_combination("tab")
wm.send_text("password123")
wm.send_key_combination("enter")
```

## License

This project is designed to be equivalent to the Windows window manager system, providing the same comprehensive automation capabilities on macOS using native Apple APIs.

## Contributing

When contributing:
1. Test on multiple macOS versions
2. Ensure accessibility permissions are documented
3. Use native macOS APIs where possible
4. Maintain compatibility with the Windows version's API design 