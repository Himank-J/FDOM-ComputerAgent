import win32gui
import win32process
import win32api
import win32con
import psutil
from typing import List, Dict, Optional, Tuple
import ctypes
from ctypes import wintypes, byref
import json
import time
import hashlib
import os
import getpass
import shutil

# Make UI Automation imports conditional
try:
    import comtypes
    from comtypes.client import CreateObject
    UI_AUTOMATION_AVAILABLE = True
except ImportError:
    UI_AUTOMATION_AVAILABLE = False
    comtypes = None

def _initialize_ui_automation():
    """Initialize UI Automation and generate the required interfaces"""
    global UI_AUTOMATION_AVAILABLE
    if not UI_AUTOMATION_AVAILABLE:
        return None, None
    
    try:
        # Create the UI Automation object first - this generates the interfaces
        uia = CreateObject("CUIAutomation")
        
        # Now import the generated interfaces
        import comtypes.gen.UIAutomationClient as UIA
        return uia, UIA
    except Exception as e:
        print(f"Warning: UI Automation not available: {e}")
        UI_AUTOMATION_AVAILABLE = False
        return None, None

class WindowManager:
    def __init__(self):
        # Get all monitors
        self.monitors = self._get_monitors()
        self._previous_windows = {}  # Track windows for change detection
    
    def _get_monitors(self) -> List[Dict]:
        """Get information about all monitors using proper Windows API"""
        monitors = []
        
        def monitor_enum_proc(hmonitor, hdc, rect, data):
            try:
                monitor_info = win32api.GetMonitorInfo(hmonitor)
                monitor_rect = monitor_info['Monitor']
                work_area = monitor_info['Work']
                is_primary = monitor_info['Flags'] == win32con.MONITORINFOF_PRIMARY
                device_name = monitor_info['Device']
                
                # Calculate actual monitor dimensions
                width = monitor_rect[2] - monitor_rect[0]
                height = monitor_rect[3] - monitor_rect[1]
                
                monitors.append({
                    'handle': hmonitor,
                    'rect': list(monitor_rect),  # [left, top, right, bottom]
                    'work_area': list(work_area),
                    'width': width,
                    'height': height,
                    'primary': is_primary,
                    'device': device_name,
                    'position': {
                        'left': monitor_rect[0],
                        'top': monitor_rect[1],
                        'right': monitor_rect[2],
                        'bottom': monitor_rect[3]
                    }
                })
                print(f"Monitor detected: {device_name} - {width}x{height} at ({monitor_rect[0]}, {monitor_rect[1]}) Primary: {is_primary}")
            except Exception as e:
                print(f"Error getting monitor info: {e}")
                # Fallback
                rect_list = [rect.left, rect.top, rect.right, rect.bottom] if hasattr(rect, 'left') else list(rect)
                width = rect_list[2] - rect_list[0]
                height = rect_list[3] - rect_list[1]
                monitors.append({
                    'handle': hmonitor,
                    'rect': rect_list,
                    'work_area': rect_list,
                    'width': width,
                    'height': height,
                    'primary': len(monitors) == 0,
                    'device': f'Monitor_{len(monitors) + 1}',
                    'position': {
                        'left': rect_list[0],
                        'top': rect_list[1],
                        'right': rect_list[2],
                        'bottom': rect_list[3]
                    }
                })
            return True
        
        try:
            # Use ctypes to properly call EnumDisplayMonitors
            user32 = ctypes.windll.user32
            
            # Define the callback function type
            MonitorEnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool,
                                                 wintypes.HMONITOR,
                                                 wintypes.HDC,
                                                 ctypes.POINTER(wintypes.RECT),
                                                 wintypes.LPARAM)
            
            def enum_proc(hmonitor, hdc, rect_ptr, data):
                rect = rect_ptr.contents
                return monitor_enum_proc(hmonitor, hdc, rect, data)
            
            callback = MonitorEnumProc(enum_proc)
            user32.EnumDisplayMonitors(None, None, callback, 0)
            
            # Sort monitors: primary first, then by left position
            monitors.sort(key=lambda m: (not m['primary'], m['position']['left']))
            
        except Exception as e:
            print(f"Monitor enumeration failed: {e}")
            # Fallback to single monitor
            try:
                width = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
                height = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)
                monitors.append({
                    'handle': 0,
                    'rect': [0, 0, width, height],
                    'work_area': [0, 0, width, height],
                    'width': width,
                    'height': height,
                    'primary': True,
                    'device': 'Primary Monitor',
                    'position': {'left': 0, 'top': 0, 'right': width, 'bottom': height}
                })
            except:
                # Ultimate fallback
                monitors.append({
                    'handle': 0,
                    'rect': [0, 0, 1920, 1080],
                    'work_area': [0, 0, 1920, 1080],
                    'width': 1920,
                    'height': 1080,
                    'primary': True,
                    'device': 'Default Monitor',
                    'position': {'left': 0, 'top': 0, 'right': 1920, 'bottom': 1080}
                })
        
        print(f"Total monitors detected: {len(monitors)}")
        for i, monitor in enumerate(monitors):
            print(f"  Monitor {i+1}: {monitor['width']}x{monitor['height']} at ({monitor['position']['left']}, {monitor['position']['top']}) - {monitor['device']} {'(Primary)' if monitor['primary'] else ''}")
        
        return monitors
    
    def _get_window_monitor(self, rect: Tuple[int, int, int, int]) -> int:
        """Determine which monitor a window is primarily on"""
        x1, y1, x2, y2 = rect
        window_center_x = (x1 + x2) // 2
        window_center_y = (y1 + y2) // 2
        
        for i, monitor in enumerate(self.monitors):
            pos = monitor['position']
            if pos['left'] <= window_center_x <= pos['right'] and pos['top'] <= window_center_y <= pos['bottom']:
                return i + 1  # 1-based indexing
        
        return 1  # Default to primary monitor
    
    def _is_window_minimized(self, hwnd: int) -> bool:
        """Check if a window is minimized"""
        return win32gui.IsIconic(hwnd)
    
    def _get_process_name(self, pid: int) -> str:
        """Get process name from PID"""
        try:
            process = psutil.Process(pid)
            return process.name()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return "Unknown"
    
    def _generate_window_id(self, hwnd: int, pid: int, title: str) -> str:
        """Generate a unique window identifier"""
        # Combine HWND, PID, and title hash for a more stable ID
        title_hash = hashlib.md5(title.encode('utf-8', errors='ignore')).hexdigest()[:8]
        return f"{hwnd}_{pid}_{title_hash}"
    
    def _is_valid_window(self, hwnd: int) -> bool:
        """Check if window is valid for our purposes"""
        try:
            if not win32gui.IsWindow(hwnd):
                return False
            if not win32gui.IsWindowVisible(hwnd):
                return False
            
            # Allow windows with empty titles (some valid windows have no title)
            title = win32gui.GetWindowText(hwnd)
            
            # Skip windows with no size
            rect = win32gui.GetWindowRect(hwnd)
            if rect[2] - rect[0] <= 0 or rect[3] - rect[1] <= 0:
                return False
                
            return True
        except Exception:
            return False

    # =============== WINDOW CONTROL METHODS ===============
    
    def get_window_state(self, hwnd: int) -> str:
        """Get current window state - FIXED to use proper Windows API"""
        try:
            # Don't validate visibility here, just check if window exists
            if not win32gui.IsWindow(hwnd):
                return "invalid"
            
            if win32gui.IsIconic(hwnd):
                return "minimized"
            
            # Use GetWindowPlacement to check if maximized
            try:
                # Get window placement structure
                placement = win32gui.GetWindowPlacement(hwnd)
                # placement[1] is the show state
                if placement[1] == win32con.SW_SHOWMAXIMIZED:
                    return "maximized"
                elif placement[1] == win32con.SW_SHOWMINIMIZED:
                    return "minimized"
                else:
                    return "normal"
            except:
                # Fallback: check if window covers entire screen
                try:
                    rect = win32gui.GetWindowRect(hwnd)
                    window_width = rect[2] - rect[0]
                    window_height = rect[3] - rect[1]
                    
                    # Find which monitor this window is on
                    monitor_id = self._get_window_monitor(rect)
                    if monitor_id <= len(self.monitors):
                        monitor = self.monitors[monitor_id - 1]
                        # If window size matches monitor size (or close), consider it maximized
                        if (abs(window_width - monitor['width']) <= 20 and 
                            abs(window_height - monitor['height']) <= 50):  # Allow for title bars
                            return "maximized"
                    
                    return "normal"
                except:
                    return "normal"
                    
        except Exception as e:
            return "error"
    
    def maximize_window(self, hwnd: int) -> Tuple[bool, str]:
        """Maximize a window"""
        try:
            # Add timing delay before action
            time.sleep(0.1)
            
            if not self.is_valid_window(hwnd):
                return False, "Window is no longer valid"
            
            current_state = self.get_window_state(hwnd)
            if current_state == "maximized":
                return True, "Window is already maximized"
            
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
            return True, "Window maximized"
        except Exception as e:
            return False, f"Failed to maximize: {e}"
    
    def minimize_window(self, hwnd: int) -> Tuple[bool, str]:
        """Minimize a window"""
        try:
            # Add timing delay before action
            time.sleep(0.1)
            
            if not self.is_valid_window(hwnd):
                return False, "Window is no longer valid"
            
            current_state = self.get_window_state(hwnd)
            if current_state == "minimized":
                return True, "Window is already minimized"
            
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
            return True, "Window minimized"
        except Exception as e:
            return False, f"Failed to minimize: {e}"
    
    def close_window(self, hwnd: int) -> Tuple[bool, str]:
        """Close a window"""
        try:
            # Add timing delay before action
            time.sleep(0.1)
            
            if not self.is_valid_window(hwnd):
                return False, "Window is no longer valid"
            
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            return True, "Window close signal sent"
        except Exception as e:
            return False, f"Failed to close: {e}"
    
    def smart_foreground(self, hwnd: int) -> Tuple[bool, str]:
        """Bring window to foreground using smart minimize/maximize technique with intermediate sizing"""
        try:
            # Add timing delay before action
            time.sleep(0.1)
            
            if not self.is_valid_window(hwnd):
                return False, "Window is no longer valid"
            
            # Store original state and position
            current_state = self.get_window_state(hwnd)
            rect = win32gui.GetWindowRect(hwnd)
            original_x, original_y = rect[0], rect[1]
            original_width = rect[2] - rect[0]
            original_height = rect[3] - rect[1]
            
            # Check if window is currently in foreground
            try:
                foreground_hwnd = win32gui.GetForegroundWindow()
                is_foreground = (foreground_hwnd == hwnd)
            except:
                is_foreground = False
            
            messages = []
            
            # If window is not in foreground, minimize it first
            if not is_foreground and current_state != "minimized":
                win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
                messages.append("minimized")
                time.sleep(1.5)  # Brief pause
            
            # Step 1: Restore and set to intermediate size (80% of screen)
            # Get monitor info for intermediate sizing
            monitor_info = win32api.GetMonitorInfo(win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST))
            work_area = monitor_info['Work']
            screen_width = work_area[2] - work_area[0]
            screen_height = work_area[3] - work_area[1]
            
            # Calculate intermediate size (80% of screen, centered)
            intermediate_width = int(screen_width * 0.8)
            intermediate_height = int(screen_height * 0.8)
            intermediate_x = work_area[0] + (screen_width - intermediate_width) // 2
            intermediate_y = work_area[1] + (screen_height - intermediate_height) // 2
            
            # Restore to normal first
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            time.sleep(0.3)
            
            # Set intermediate size
            win32gui.SetWindowPos(
                hwnd,
                0,
                intermediate_x, intermediate_y, intermediate_width, intermediate_height,
                win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE
            )
            messages.append(f"resized to intermediate ({intermediate_width}x{intermediate_height})")
            time.sleep(1.0)  # Pause for intermediate state to settle
            
            # Step 2: FORCE RESTORE first, then maximize (this is key!)
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            time.sleep(0.5)  # Let restore complete
            
            # Now maximize - this should work better after explicit restore
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
            messages.append("maximized to full screen")
            time.sleep(1.0)  # Pause for maximize animation
            
            # Step 3: Double-check maximize worked, force it if needed
            current_state_after = self.get_window_state(hwnd)
            if current_state_after != "maximized":
                # Try alternative maximize approach
                win32gui.ShowWindow(hwnd, win32con.SW_SHOWMAXIMIZED)
                time.sleep(0.5)
                messages.append("force maximized (fallback)")
                
                # Final check
                final_state = self.get_window_state(hwnd)
                if final_state != "maximized":
                    messages.append(f"maximize attempted (final state: {final_state})")
            
            # Finally, bring to foreground
            try:
                win32gui.SetForegroundWindow(hwnd)
                messages.append("brought to foreground")
            except:
                # Use fallback method
                try:
                    current_thread = win32process.GetCurrentThreadId()
                    window_thread, _ = win32process.GetWindowThreadProcessId(hwnd)
                    
                    if current_thread != window_thread:
                        win32process.AttachThreadInput(current_thread, window_thread, True)
                        try:
                            win32gui.SetForegroundWindow(hwnd)
                            messages.append("brought to foreground (method 2)")
                        finally:
                            win32process.AttachThreadInput(current_thread, window_thread, False)
                except:
                    messages.append("attempted foreground (may be restricted)")
            
            return True, f"Enhanced smart foreground: {' → '.join(messages)}"
                        
        except Exception as e:
            return False, f"Failed enhanced smart foreground: {e}"
    
    def resize_window(self, hwnd: int, width: int, height: int) -> Tuple[bool, str]:
        """Resize a window to specific dimensions"""
        try:
            # Add timing delay before action
            time.sleep(0.1)
            
            if not self.is_valid_window(hwnd):
                return False, "Window is no longer valid"
            
            # Get current position
            rect = win32gui.GetWindowRect(hwnd)
            current_x, current_y = rect[0], rect[1]
            
            # Restore window if minimized/maximized first
            if win32gui.IsIconic(hwnd) or self.get_window_state(hwnd) == "maximized":
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            
            # Resize window keeping current position
            win32gui.SetWindowPos(
                hwnd, 
                0,  # Insert after (ignored with SWP_NOZORDER)
                current_x, current_y, width, height,
                win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE
            )
            
            # Verify the resize worked by checking new dimensions
            time.sleep(0.1)  # Small delay to let Windows process the change
            new_rect = win32gui.GetWindowRect(hwnd)
            new_width = new_rect[2] - new_rect[0]
            new_height = new_rect[3] - new_rect[1]
            
            # Consider it successful if we're close to target size (within 20 pixels)
            if abs(new_width - width) <= 20 and abs(new_height - height) <= 20:
                return True, f"Window resized to {new_width}x{new_height}"
            else:
                return True, f"Window resize attempted (target: {width}x{height}, actual: {new_width}x{new_height})"
                
        except Exception as e:
            return False, f"Failed to resize: {e}"
    
    def move_window(self, hwnd: int, x: int, y: int) -> Tuple[bool, str]:
        """Move window to specific absolute coordinates"""
        try:
            # Add timing delay before action
            time.sleep(0.1)
            
            if not self.is_valid_window(hwnd):
                return False, "Window is no longer valid"
            
            # Get current size
            rect = win32gui.GetWindowRect(hwnd)
            current_width = rect[2] - rect[0]
            current_height = rect[3] - rect[1]
            
            # Restore window if minimized/maximized first
            if win32gui.IsIconic(hwnd) or self.get_window_state(hwnd) == "maximized":
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            
            # Move window keeping current size
            win32gui.SetWindowPos(
                hwnd,
                0,  # Insert after (ignored with SWP_NOZORDER)
                x, y, current_width, current_height,
                win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE
            )
            
            # Verify the move worked by checking new position
            time.sleep(2)  # Small delay to let Windows process the change
            new_rect = win32gui.GetWindowRect(hwnd)
            new_x, new_y = new_rect[0], new_rect[1]
            
            # Consider it successful if we're close to target position (within 10 pixels)
            if abs(new_x - x) <= 10 and abs(new_y - y) <= 10:
                return True, f"Window moved to ({new_x}, {new_y})"
            else:
                return True, f"Window move attempted (target: ({x}, {y}), actual: ({new_x}, {new_y}))"
                
        except Exception as e:
            return False, f"Failed to move: {e}"
    
    def move_window_to_monitor(self, hwnd: int, target_monitor: int) -> Tuple[bool, str]:
        """Move a window to a specific monitor (centered)"""
        try:
            if not self.is_valid_window(hwnd):
                return False, "Window is no longer valid"
            
            if target_monitor < 1 or target_monitor > len(self.monitors):
                return False, f"Invalid monitor ID. Available monitors: 1-{len(self.monitors)}"
            
            target_monitor_data = self.monitors[target_monitor - 1]
            
            # Get current window size
            current_rect = win32gui.GetWindowRect(hwnd)
            window_width = current_rect[2] - current_rect[0]
            window_height = current_rect[3] - current_rect[1]
            
            # Calculate position to center window on target monitor
            monitor_pos = target_monitor_data['position']
            target_x = monitor_pos['left'] + (target_monitor_data['width'] - window_width) // 2
            target_y = monitor_pos['top'] + (target_monitor_data['height'] - window_height) // 2
            
            # Ensure window doesn't go off-screen
            target_x = max(monitor_pos['left'], min(target_x, monitor_pos['right'] - window_width))
            target_y = max(monitor_pos['top'], min(target_y, monitor_pos['bottom'] - window_height))
            
            success, message = self.move_window(hwnd, target_x, target_y)
            if success:
                return True, f"Window moved to monitor {target_monitor} at ({target_x}, {target_y})"
            else:
                return False, message
                
        except Exception as e:
            return False, f"Failed to move to monitor: {e}"
    
    def move_window_to_screen_position(self, hwnd: int, screen_id: int, x: int, y: int) -> Tuple[bool, str]:
        """Move window to specific coordinates on a specific screen"""
        try:
            if not self.is_valid_window(hwnd):
                return False, "Window is no longer valid"
            
            if screen_id < 1 or screen_id > len(self.monitors):
                return False, f"Invalid screen ID. Available screens: 1-{len(self.monitors)}"
            
            screen_data = self.monitors[screen_id - 1]
            screen_pos = screen_data['position']
            
            # Convert relative screen coordinates to absolute coordinates
            absolute_x = screen_pos['left'] + x
            absolute_y = screen_pos['top'] + y
            
            # Validate coordinates are within screen bounds
            if x < 0 or y < 0:
                return False, f"Coordinates must be positive. Got ({x}, {y})"
            
            if x >= screen_data['width'] or y >= screen_data['height']:
                return False, f"Coordinates ({x}, {y}) are outside screen {screen_id} bounds ({screen_data['width']}x{screen_data['height']})"
            
            success, message = self.move_window(hwnd, absolute_x, absolute_y)
            if success:
                return True, f"Window moved to screen {screen_id} position ({x}, {y}) [absolute: ({absolute_x}, {absolute_y})]"
            else:
                return False, message
                
        except Exception as e:
            return False, f"Failed to move to screen position: {e}"

    # =============== EXISTING METHODS ===============
    
    def get_structured_windows(self) -> Dict:
        """Get all windows organized by monitor and application"""
        result = {
            "timestamp": time.time(),
            "monitors": {},
            "summary": {
                "total_monitors": len(self.monitors),
                "total_windows": 0,
                "total_apps": 0
            }
        }
        
        # Initialize monitor structure with correct dimensions
        for i, monitor in enumerate(self.monitors):
            monitor_id = i + 1
            result["monitors"][f"monitor_{monitor_id}"] = {
                "id": monitor_id,
                "rect": monitor['rect'],
                "work_area": monitor['work_area'],
                "width": monitor['width'],
                "height": monitor['height'],
                "primary": monitor['primary'],
                "device": monitor['device'],
                "applications": {},
                "window_count": 0
            }
        
        # Get all windows
        def enum_windows_proc(hwnd, data):
            if self._is_valid_window(hwnd):
                try:
                    # Get window info
                    title = win32gui.GetWindowText(hwnd)
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    proc_name = self._get_process_name(pid)
                    rect = win32gui.GetWindowRect(hwnd)
                    screen = self._get_window_monitor(rect)
                    minimized = self._is_window_minimized(hwnd)
                    window_id = self._generate_window_id(hwnd, pid, title)
                    
                    # Calculate window dimensions
                    width = rect[2] - rect[0]
                    height = rect[3] - rect[1]
                    
                    monitor_key = f"monitor_{screen}"
                    if monitor_key not in result["monitors"]:
                        return True  # Skip if monitor not found
                    
                    # Initialize app entry if not exists
                    if proc_name not in result["monitors"][monitor_key]["applications"]:
                        result["monitors"][monitor_key]["applications"][proc_name] = {
                            "process_name": proc_name,
                            "windows": {},
                            "window_count": 0,
                            "minimized_count": 0,
                            "visible_count": 0
                        }
                    
                    app_data = result["monitors"][monitor_key]["applications"][proc_name]
                    
                    # Add window details
                    window_data = {
                        "window_id": window_id,
                        "hwnd": hwnd,
                        "pid": pid,
                        "title": title,
                        "position": {
                            "x": rect[0],
                            "y": rect[1]
                        },
                        "size": {
                            "width": width,
                            "height": height
                        },
                        "rect": list(rect),
                        "minimized": minimized,
                        "visible": not minimized,
                        "monitor": screen
                    }
                    
                    app_data["windows"][window_id] = window_data
                    app_data["window_count"] += 1
                    
                    if minimized:
                        app_data["minimized_count"] += 1
                    else:
                        app_data["visible_count"] += 1
                    
                    result["monitors"][monitor_key]["window_count"] += 1
                    result["summary"]["total_windows"] += 1
                    
                except Exception as e:
                    # Skip windows that cause errors
                    pass
            return True
        
        win32gui.EnumWindows(enum_windows_proc, None)
        
        # Count unique applications
        all_apps = set()
        for monitor_data in result["monitors"].values():
            all_apps.update(monitor_data["applications"].keys())
        result["summary"]["total_apps"] = len(all_apps)
        
        return result
    
    def find_window_by_app(self, app_name: str) -> List[Dict]:
        """Find windows by application name - returns list format for backwards compatibility"""
        structured = self.get_structured_windows()
        matching_windows = []
        
        app_name_lower = app_name.lower()
        if not app_name_lower.endswith('.exe'):
            app_name_lower += '.exe'
        
        for monitor_data in structured["monitors"].values():
            for proc_name, app_data in monitor_data["applications"].items():
                if proc_name.lower() == app_name_lower:
                    for window_data in app_data["windows"].values():
                        # Convert back to old format for compatibility
                        matching_windows.append({
                            "hwnd": window_data["hwnd"],
                            "title": window_data["title"],
                            "pid": window_data["pid"],
                            "proc": proc_name,
                            "rect": window_data["rect"],
                            "screen": window_data["monitor"],
                            "minimized": window_data["minimized"]
                        })
        
        return matching_windows

    def print_structured_output(self, show_minimized: bool = True):
        """Print a clean, structured view of all windows"""
        data = self.get_structured_windows()
        
        print("=" * 80)
        print(f"WINDOW MANAGER - {data['summary']['total_windows']} windows across {data['summary']['total_monitors']} monitors")
        print("=" * 80)
        
        for monitor_key, monitor_data in data["monitors"].items():
            print(f"\n📺 MONITOR {monitor_data['id']} {'(PRIMARY)' if monitor_data['primary'] else ''}")
            print(f"   Resolution: {monitor_data['width']}x{monitor_data['height']}")
            print(f"   Position: {monitor_data['rect']}")
            print(f"   Windows: {monitor_data['window_count']}")
            print("-" * 60)
            
            if not monitor_data["applications"]:
                print("   No applications on this monitor")
                continue
            
            for app_name, app_data in monitor_data["applications"].items():
                visible_windows = [w for w in app_data["windows"].values() if not w["minimized"]]
                minimized_windows = [w for w in app_data["windows"].values() if w["minimized"]]
                
                print(f"\n   🖥️  {app_name}")
                print(f"      Total: {app_data['window_count']} | Visible: {len(visible_windows)} | Minimized: {len(minimized_windows)}")
                
                # Show visible windows
                for window in visible_windows:
                    title = window["title"][:50] + "..." if len(window["title"]) > 50 else window["title"]
                    print(f"      ├─ 👁️  {title}")
                    print(f"      │   ID: {window['window_id']}")
                    print(f"      │   Position: ({window['position']['x']}, {window['position']['y']})")
                    print(f"      │   Size: {window['size']['width']}x{window['size']['height']}")
                
                # Show minimized windows if requested
                if show_minimized and minimized_windows:
                    print(f"      │")
                    for window in minimized_windows:
                        title = window["title"][:50] + "..." if len(window["title"]) > 50 else window["title"]
                        print(f"      ├─ 📦 {title} (minimized)")
                        print(f"      │   ID: {window['window_id']}")
        
        print("\n" + "=" * 80)

    # =============== NEW SYSTEM UTILITIES ===============
    
    def get_cursor_position(self) -> Tuple[bool, str, Optional[Tuple[int, int]]]:
        """Get current cursor position"""
        try:
            cursor_pos = win32gui.GetCursorPos()
            monitor_id = self._get_cursor_monitor(cursor_pos)
            return True, f"Cursor at ({cursor_pos[0]}, {cursor_pos[1]}) on Monitor {monitor_id}", cursor_pos
        except Exception as e:
            return False, f"Failed to get cursor position: {e}", None
    
    def set_cursor_position(self, x: int, y: int) -> Tuple[bool, str]:
        """Set cursor position to absolute coordinates"""
        try:
            # Add timing delay before action (shorter for cursor movements)
            time.sleep(0.05)
            
            win32api.SetCursorPos((x, y))
            
            # Verify the position was set correctly
            actual_pos = win32gui.GetCursorPos()
            if actual_pos == (x, y):
                monitor_id = self._get_cursor_monitor((x, y))
                return True, f"Cursor moved to ({x}, {y}) on Monitor {monitor_id}"
            else:
                monitor_id = self._get_cursor_monitor(actual_pos)
                return True, f"Cursor moved to ({actual_pos[0]}, {actual_pos[1]}) on Monitor {monitor_id} (close to target)"
        except Exception as e:
            return False, f"Failed to set cursor position: {e}"
    
    def _get_cursor_monitor(self, cursor_pos: Tuple[int, int]) -> int:
        """Determine which monitor the cursor is on"""
        x, y = cursor_pos
        for i, monitor in enumerate(self.monitors):
            pos = monitor['position']
            if pos['left'] <= x <= pos['right'] and pos['top'] <= y <= pos['bottom']:
                return i + 1
        return 1
    
    def show_message_box(self, title: str, message: str, x: int = None, y: int = None, 
                        width: int = 300, height: int = 150) -> Tuple[bool, str]:
        """Display a message box at specified location"""
        try:
            # If no position specified, use cursor position
            if x is None or y is None:
                cursor_pos = win32gui.GetCursorPos()
                x = cursor_pos[0] if x is None else x
                y = cursor_pos[1] if y is None else y
            
            # Create a simple message box using Windows API
            # Note: Standard MessageBox doesn't support custom positioning directly
            # We'll use a workaround by creating it normally then moving it
            
            # Use threading to show message box and return immediately
            import threading
            
            def show_box():
                try:
                    # Show message box (this will be at default position initially)
                    result = win32api.MessageBox(0, message, title, win32con.MB_OK | win32con.MB_TOPMOST)
                except:
                    pass
            
            # Start in background
            thread = threading.Thread(target=show_box)
            thread.daemon = True
            thread.start()
            
            # Brief delay to let it appear
            time.sleep(0.1)
            
            # Try to find and move the message box window
            try:
                def find_message_box(hwnd, param):
                    if win32gui.GetWindowText(hwnd) == title:
                        # Found our message box, move it
                        win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 
                                            x, y, width, height, 
                                            win32con.SWP_SHOWWINDOW)
                        return False  # Stop enumeration
                    return True
                
                win32gui.EnumWindows(find_message_box, None)
            except:
                pass  # If we can't move it, that's okay
            
            return True, f"Message box '{title}' shown at ({x}, {y})"
            
        except Exception as e:
            return False, f"Failed to show message box: {e}"
    
    def get_computer_name(self) -> Tuple[bool, str]:
        """Get computer name"""
        try:
            computer_name = os.environ.get('COMPUTERNAME', 'Unknown')
            return True, f"Computer name: {computer_name}"
        except Exception as e:
            return False, f"Failed to get computer name: {e}"
    
    def get_user_name(self) -> Tuple[bool, str]:
        """Get current user name"""
        try:
            user_name = getpass.getuser()
            domain = os.environ.get('USERDOMAIN', '')
            if domain:
                full_name = f"{domain}\\{user_name}"
            else:
                full_name = user_name
            return True, f"User: {full_name}"
        except Exception as e:
            return False, f"Failed to get user name: {e}"
    
    # =============== VIRTUAL KEYBOARD OPERATIONS ===============
    
    def get_virtual_key_codes(self) -> Tuple[bool, str]:
        """Get all available virtual key codes - COMPREHENSIVE LIST"""
        try:
            key_categories = {
                "Modifier Keys": {
                    'CTRL': 0x11, 'LCTRL': 0xA2, 'RCTRL': 0xA3,
                    'ALT': 0x12, 'LALT': 0xA4, 'RALT': 0xA5,
                    'SHIFT': 0x10, 'LSHIFT': 0xA0, 'RSHIFT': 0xA1,
                    'WIN': 0x5B, 'LWIN': 0x5B, 'RWIN': 0x5C,
                },
                "Basic Keys": {
                    'ESC': 0x1B, 'TAB': 0x09, 'ENTER': 0x0D, 'SPACE': 0x20,
                    'BACKSPACE': 0x08, 'DELETE': 0x2E, 'INSERT': 0x2D,
                },
                "Navigation": {
                    'HOME': 0x24, 'END': 0x23, 'PAGEUP': 0x21, 'PAGEDOWN': 0x22,
                    'UP': 0x26, 'DOWN': 0x28, 'LEFT': 0x25, 'RIGHT': 0x27,
                },
                "Function Keys": {
                    'F1': 0x70, 'F2': 0x71, 'F3': 0x72, 'F4': 0x73, 'F5': 0x74, 'F6': 0x75,
                    'F7': 0x76, 'F8': 0x77, 'F9': 0x78, 'F10': 0x79, 'F11': 0x7A, 'F12': 0x7B,
                    'F13': 0x7C, 'F14': 0x7D, 'F15': 0x7E, 'F16': 0x7F, 'F17': 0x80, 'F18': 0x81,
                    'F19': 0x82, 'F20': 0x83, 'F21': 0x84, 'F22': 0x85, 'F23': 0x86, 'F24': 0x87,
                },
                "Numpad": {
                    'NUMPAD0': 0x60, 'NUMPAD1': 0x61, 'NUMPAD2': 0x62, 'NUMPAD3': 0x63,
                    'NUMPAD4': 0x64, 'NUMPAD5': 0x65, 'NUMPAD6': 0x66, 'NUMPAD7': 0x67,
                    'NUMPAD8': 0x68, 'NUMPAD9': 0x69, 'NUMPADADD': 0x6B, 'NUMPADSUBTRACT': 0x6D,
                    'NUMPADMULTIPLY': 0x6A, 'NUMPADDIVIDE': 0x6F, 'NUMPADDECIMAL': 0x6E,
                },
                "Special Characters": {
                    'SEMICOLON': 0xBA, 'EQUALS': 0xBB, 'COMMA': 0xBC, 'MINUS': 0xBD,
                    'PERIOD': 0xBE, 'SLASH': 0xBF, 'GRAVE': 0xC0, 'LBRACKET': 0xDB,
                    'BACKSLASH': 0xDC, 'RBRACKET': 0xDD, 'QUOTE': 0xDE,
                },
                "Lock Keys": {
                    'CAPSLOCK': 0x14, 'NUMLOCK': 0x90, 'SCROLLLOCK': 0x91,
                },
                "Media Keys": {
                    'VOLUME_MUTE': 0xAD, 'VOLUME_DOWN': 0xAE, 'VOLUME_UP': 0xAF,
                    'MEDIA_NEXT_TRACK': 0xB0, 'MEDIA_PREV_TRACK': 0xB1,
                    'MEDIA_STOP': 0xB2, 'MEDIA_PLAY_PAUSE': 0xB3,
                },
            }
            
            # Add letters and numbers
            key_categories["Letters"] = {}
            for i in range(26):
                key_categories["Letters"][chr(ord('A') + i)] = 0x41 + i
            
            key_categories["Numbers"] = {}
            for i in range(10):
                key_categories["Numbers"][str(i)] = 0x30 + i
            
            result = []
            for category, keys in key_categories.items():
                result.append(f"\n📁 {category}:")
                for key, code in sorted(keys.items()):
                    result.append(f"   {key:<20} = {hex(code)}")
            
            return True, "\n".join(result)
            
        except Exception as e:
            return False, f"Failed to get virtual key codes: {e}"
    
    def send_key_combination(self, keys: str) -> Tuple[bool, str]:
        """Send virtual keyboard combination (e.g., 'ctrl+c', 'alt+tab') - COMPREHENSIVE"""
        try:
            # Add timing delay before action
            time.sleep(0.1)
            
            # Parse key combination
            key_parts = [k.strip().upper() for k in keys.split('+')]
            
            # COMPREHENSIVE Map key names to virtual key codes
            key_map = {
                # Modifier keys
                'CTRL': 0x11, 'CONTROL': 0x11, 'LCTRL': 0xA2, 'RCTRL': 0xA3,
                'ALT': 0x12, 'LALT': 0xA4, 'RALT': 0xA5,
                'SHIFT': 0x10, 'LSHIFT': 0xA0, 'RSHIFT': 0xA1,
                'WIN': 0x5B, 'WINDOWS': 0x5B, 'LWIN': 0x5B, 'RWIN': 0x5C,
                
                # Basic keys
                'ESC': 0x1B, 'ESCAPE': 0x1B,
                'TAB': 0x09, 'ENTER': 0x0D, 'RETURN': 0x0D, 'SPACE': 0x20,
                'BACKSPACE': 0x08, 'DELETE': 0x2E, 'INSERT': 0x2D,
                
                # Home cluster
                'HOME': 0x24, 'END': 0x23, 'PAGEUP': 0x21, 'PAGEDOWN': 0x22,
                'PGUP': 0x21, 'PGDN': 0x22,
                
                # Arrow keys
                'UP': 0x26, 'DOWN': 0x28, 'LEFT': 0x25, 'RIGHT': 0x27,
                'UPARROW': 0x26, 'DOWNARROW': 0x28, 'LEFTARROW': 0x25, 'RIGHTARROW': 0x27,
                
                # Function keys (F1-F24)
                'F1': 0x70, 'F2': 0x71, 'F3': 0x72, 'F4': 0x73, 'F5': 0x74, 'F6': 0x75,
                'F7': 0x76, 'F8': 0x77, 'F9': 0x78, 'F10': 0x79, 'F11': 0x7A, 'F12': 0x7B,
                'F13': 0x7C, 'F14': 0x7D, 'F15': 0x7E, 'F16': 0x7F, 'F17': 0x80, 'F18': 0x81,
                'F19': 0x82, 'F20': 0x83, 'F21': 0x84, 'F22': 0x85, 'F23': 0x86, 'F24': 0x87,
                
                # Numpad digits
                'NUMPAD0': 0x60, 'NUMPAD1': 0x61, 'NUMPAD2': 0x62, 'NUMPAD3': 0x63,
                'NUMPAD4': 0x64, 'NUMPAD5': 0x65, 'NUMPAD6': 0x66, 'NUMPAD7': 0x67,
                'NUMPAD8': 0x68, 'NUMPAD9': 0x69,
                
                # Numpad operators
                'NUMPADADD': 0x6B, 'NUMPADSUBTRACT': 0x6D, 'NUMPADMULTIPLY': 0x6A,
                'NUMPADDIVIDE': 0x6F, 'NUMPADDECIMAL': 0x6E, 'NUMPADENTER': 0x0D,
                'NUMPADPLUS': 0x6B, 'NUMPADMINUS': 0x6D, 'NUMPADSTAR': 0x6A,
                'NUMPADSLASH': 0x6F, 'NUMPADDOT': 0x6E,
                
                # Lock keys
                'CAPSLOCK': 0x14, 'CAPS': 0x14, 'NUMLOCK': 0x90, 'SCROLLLOCK': 0x91,
                'SCROLL': 0x91,
                
                # Special characters (main keyboard)
                'SEMICOLON': 0xBA, ';': 0xBA,           # ; :
                'EQUALS': 0xBB, '=': 0xBB,             # = +
                'COMMA': 0xBC, ',': 0xBC,              # , <
                'MINUS': 0xBD, '-': 0xBD,              # - _
                'PERIOD': 0xBE, '.': 0xBE,             # . >
                'SLASH': 0xBF, '/': 0xBF,              # / ?
                'GRAVE': 0xC0, '`': 0xC0,              # ` ~
                'LBRACKET': 0xDB, '[': 0xDB,           # [ {
                'BACKSLASH': 0xDC, '\\': 0xDC,         # \ |
                'RBRACKET': 0xDD, ']': 0xDD,           # ] }
                'QUOTE': 0xDE, "'": 0xDE,              # ' "
                
                # Media keys
                'VOLUME_MUTE': 0xAD, 'MUTE': 0xAD,
                'VOLUME_DOWN': 0xAE, 'VOLDOWN': 0xAE,
                'VOLUME_UP': 0xAF, 'VOLUP': 0xAF,
                'MEDIA_NEXT_TRACK': 0xB0, 'NEXTTRACK': 0xB0,
                'MEDIA_PREV_TRACK': 0xB1, 'PREVTRACK': 0xB1,
                'MEDIA_STOP': 0xB2, 'MEDIASTOP': 0xB2,
                'MEDIA_PLAY_PAUSE': 0xB3, 'PLAYPAUSE': 0xB3,
                
                # Browser keys
                'BROWSER_BACK': 0xA6, 'BROWSERBACK': 0xA6,
                'BROWSER_FORWARD': 0xA7, 'BROWSERFORWARD': 0xA7,
                'BROWSER_REFRESH': 0xA8, 'BROWSERREFRESH': 0xA8,
                'BROWSER_STOP': 0xA9, 'BROWSERSTOP': 0xA9,
                'BROWSER_SEARCH': 0xAA, 'BROWSERSEARCH': 0xAA,
                'BROWSER_FAVORITES': 0xAB, 'BROWSERFAVORITES': 0xAB,
                'BROWSER_HOME': 0xAC, 'BROWSERHOME': 0xAC,
                
                # Application keys
                'APPS': 0x5D, 'MENU': 0x5D,           # Context menu key
                'SLEEP': 0x5F,
                'PRINT': 0x2A, 'PRINTSCREEN': 0x2C,
                'PAUSE': 0x13, 'BREAK': 0x03,
                
                # Additional special keys
                'SELECT': 0x29, 'EXECUTE': 0x2B, 'HELP': 0x2F,
                'CLEAR': 0x0C, 'SEPARATOR': 0x6C,
            }
            
            # Add letter keys (A-Z)
            for i in range(26):
                key_map[chr(ord('A') + i)] = 0x41 + i
            
            # Add number keys (0-9) - main keyboard
            for i in range(10):
                key_map[str(i)] = 0x30 + i
            
            # Convert key names to codes
            key_codes = []
            for key in key_parts:
                if key in key_map:
                    key_codes.append(key_map[key])
                else:
                    return False, f"Unknown key: {key}. Use 'keys' command to see all available keys."
            
            if not key_codes:
                return False, "No valid keys specified"
            
            # Try multiple methods for better compatibility
            # Method 1: Try SendInput API
            try:
                success = self._send_keys_via_sendinput(key_codes)
                if success:
                    return True, f"Sent key combination: {keys} (SendInput)"
            except Exception as e:
                print(f"SendInput failed: {e}")
            
            # Method 2: Try keybd_event API (fallback)
            try:
                success = self._send_keys_via_keybd_event(key_codes)
                if success:
                    return True, f"Sent key combination: {keys} (keybd_event)"
            except Exception as e:
                print(f"keybd_event failed: {e}")
            
            # Method 3: Try PostMessage to foreground window
            try:
                success = self._send_keys_via_postmessage(key_codes)
                if success:
                    return True, f"Sent key combination: {keys} (PostMessage)"
            except Exception as e:
                print(f"PostMessage failed: {e}")
            
            return False, f"All keyboard input methods failed for: {keys}"
                
        except Exception as e:
            return False, f"Failed to send key combination: {e}"
    
    def _send_keys_via_sendinput(self, key_codes: List[int]) -> bool:
        """Send keys using SendInput API"""
        import ctypes
        from ctypes import wintypes
        
        # Define input structures
        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))
            ]
        
        class INPUT(ctypes.Structure):
            class _INPUT(ctypes.Union):
                _fields_ = [("ki", KEYBDINPUT)]
            _anonymous_ = ("_input",)
            _fields_ = [
                ("type", wintypes.DWORD),
                ("_input", _INPUT)
            ]
        
        # Create input events
        inputs = []
        
        # Press all keys down
        for vk_code in key_codes:
            inp = INPUT()
            inp.type = 1  # INPUT_KEYBOARD
            inp.ki.wVk = vk_code
            inp.ki.wScan = 0
            inp.ki.dwFlags = 0  # KEYEVENTF_KEYDOWN
            inp.ki.time = 0
            inp.ki.dwExtraInfo = None
            inputs.append(inp)
        
        # Small delay between press and release
        time.sleep(0.05)
        
        # Release all keys (in reverse order)
        for vk_code in reversed(key_codes):
            inp = INPUT()
            inp.type = 1  # INPUT_KEYBOARD
            inp.ki.wVk = vk_code
            inp.ki.wScan = 0
            inp.ki.dwFlags = 2  # KEYEVENTF_KEYUP
            inp.ki.time = 0
            inp.ki.dwExtraInfo = None
            inputs.append(inp)
        
        # Send the inputs
        user32 = ctypes.windll.user32
        num_sent = user32.SendInput(len(inputs), (INPUT * len(inputs))(*inputs), ctypes.sizeof(INPUT))
        
        return num_sent == len(inputs)
    
    def _send_keys_via_keybd_event(self, key_codes: List[int]) -> bool:
        """Send keys using keybd_event API (older method)"""
        import ctypes
        
        user32 = ctypes.windll.user32
        
        try:
            # Press all keys down
            for vk_code in key_codes:
                user32.keybd_event(vk_code, 0, 0, 0)  # Key down
                time.sleep(0.01)
            
            time.sleep(0.05)  # Hold
            
            # Release all keys (in reverse order)
            for vk_code in reversed(key_codes):
                user32.keybd_event(vk_code, 0, 2, 0)  # Key up (KEYEVENTF_KEYUP = 2)
                time.sleep(0.01)
            
            return True
        except:
            return False
    
    def _send_keys_via_postmessage(self, key_codes: List[int]) -> bool:
        """Send keys using PostMessage to foreground window"""
        try:
            # Get foreground window
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return False
            
            # For simple combinations like Ctrl+V, we can send WM_KEYDOWN/WM_KEYUP
            WM_KEYDOWN = 0x0100
            WM_KEYUP = 0x0101
            
            # Press keys down
            for vk_code in key_codes:
                win32gui.PostMessage(hwnd, WM_KEYDOWN, vk_code, 0)
                time.sleep(0.01)
            
            time.sleep(0.05)
            
            # Release keys
            for vk_code in reversed(key_codes):
                win32gui.PostMessage(hwnd, WM_KEYUP, vk_code, 0)
                time.sleep(0.01)
            
            return True
        except:
            return False
    
    def send_text(self, text: str) -> Tuple[bool, str]:
        """Send text as if typed on keyboard"""
        try:
            import ctypes
            from ctypes import wintypes
            
            # Define input structures (same as above)
            class KEYBDINPUT(ctypes.Structure):
                _fields_ = [
                    ("wVk", wintypes.WORD),
                    ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))
                ]
            
            class INPUT(ctypes.Structure):
                class _INPUT(ctypes.Union):
                    _fields_ = [("ki", KEYBDINPUT)]
                _anonymous_ = ("_input",)
                _fields_ = [
                    ("type", wintypes.DWORD),
                    ("_input", _INPUT)
                ]
            
            inputs = []
            for char in text:
                # Key down
                inp = INPUT()
                inp.type = 1  # INPUT_KEYBOARD
                inp.ki.wVk = 0
                inp.ki.wScan = ord(char)
                inp.ki.dwFlags = 4  # KEYEVENTF_UNICODE
                inp.ki.time = 0
                inp.ki.dwExtraInfo = None
                inputs.append(inp)
                
                # Key up
                inp = INPUT()
                inp.type = 1  # INPUT_KEYBOARD
                inp.ki.wVk = 0
                inp.ki.wScan = ord(char)
                inp.ki.dwFlags = 4 | 2  # KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
                inp.ki.time = 0
                inp.ki.dwExtraInfo = None
                inputs.append(inp)
            
            # Send the inputs
            user32 = ctypes.windll.user32
            num_sent = user32.SendInput(len(inputs), (INPUT * len(inputs))(*inputs), ctypes.sizeof(INPUT))
            
            if num_sent == len(inputs):
                return True, f"Sent text: '{text}' ({len(text)} characters)"
            else:
                return False, f"Only sent {num_sent}/{len(inputs)} key events"
                
        except Exception as e:
            return False, f"Failed to send text: {e}"

    # =============== MOUSE OPERATIONS ===============
    
    def send_mouse_click(self, button: str = "left", x: int = None, y: int = None) -> Tuple[bool, str]:
        """Send mouse click at specified position or current cursor position"""
        try:
            import ctypes
            from ctypes import wintypes
            
            # Add timing delay before action
            time.sleep(0.1)
            
            # Define mouse input structure
            class MOUSEINPUT(ctypes.Structure):
                _fields_ = [
                    ("dx", ctypes.c_long),
                    ("dy", ctypes.c_long),
                    ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))
                ]
            
            class INPUT(ctypes.Structure):
                class _INPUT(ctypes.Union):
                    _fields_ = [("mi", MOUSEINPUT)]
                _anonymous_ = ("_input",)
                _fields_ = [
                    ("type", wintypes.DWORD),
                    ("_input", _INPUT)
                ]
            
            # ALWAYS move cursor to position if specified (this is the key change)
            if x is not None and y is not None:
                success, msg = self.set_cursor_position(x, y)
                if not success:
                    return False, f"Failed to move cursor: {msg}"
                # Add small delay after cursor movement
                time.sleep(0.05)
            else:
                # Get current cursor position
                cursor_pos = win32gui.GetCursorPos()
                x, y = cursor_pos
            
            # Map button to flags
            button_map = {
                "left": (0x0002, 0x0004),    # MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP
                "right": (0x0008, 0x0010),   # MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
                "middle": (0x0020, 0x0040)   # MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP
            }
            
            if button.lower() not in button_map:
                return False, f"Invalid button: {button}. Use left, right, or middle"
            
            down_flag, up_flag = button_map[button.lower()]
            
            # Create input events
            inputs = []
            
            # Mouse down
            inp = INPUT()
            inp.type = 0  # INPUT_MOUSE
            inp.mi.dx = 0
            inp.mi.dy = 0
            inp.mi.mouseData = 0
            inp.mi.dwFlags = down_flag
            inp.mi.time = 0
            inp.mi.dwExtraInfo = None
            inputs.append(inp)
            
            # Mouse up
            inp = INPUT()
            inp.type = 0  # INPUT_MOUSE
            inp.mi.dx = 0
            inp.mi.dy = 0
            inp.mi.mouseData = 0
            inp.mi.dwFlags = up_flag
            inp.mi.time = 0
            inp.mi.dwExtraInfo = None
            inputs.append(inp)
            
            # Send the inputs
            user32 = ctypes.windll.user32
            num_sent = user32.SendInput(len(inputs), (INPUT * len(inputs))(*inputs), ctypes.sizeof(INPUT))
            
            if num_sent == len(inputs):
                monitor_id = self._get_cursor_monitor((x, y))
                return True, f"{button.capitalize()} click at ({x}, {y}) on Monitor {monitor_id}"
            else:
                return False, f"Only sent {num_sent}/{len(inputs)} mouse events"
                
        except Exception as e:
            return False, f"Failed to send mouse click: {e}"
    
    def send_mouse_double_click(self, button: str = "left", x: int = None, y: int = None) -> Tuple[bool, str]:
        """Send mouse double click"""
        try:
            # Add timing delay before action
            time.sleep(0.1)
            
            # ALWAYS move cursor to position first if specified
            if x is not None and y is not None:
                success, msg = self.set_cursor_position(x, y)
                if not success:
                    return False, f"Failed to move cursor: {msg}"
                # Add small delay after cursor movement
                time.sleep(0.05)
            
            # Send first click (don't move cursor again since we already moved it)
            success1, msg1 = self.send_mouse_click(button, None, None)  # Use current position
            if not success1:
                return False, f"First click failed: {msg1}"
            
            # Brief delay between clicks
            time.sleep(0.05)
            
            # Send second click
            success2, msg2 = self.send_mouse_click(button, None, None)  # Use current position
            if not success2:
                return False, f"Second click failed: {msg2}"
            
            if x is None or y is None:
                cursor_pos = win32gui.GetCursorPos()
                x, y = cursor_pos
            
            monitor_id = self._get_cursor_monitor((x, y))
            return True, f"{button.capitalize()} double-click at ({x}, {y}) on Monitor {monitor_id}"
            
        except Exception as e:
            return False, f"Failed to send double click: {e}"
    
    def send_mouse_long_click(self, button: str = "left", duration: float = 1.0, 
                             x: int = None, y: int = None) -> Tuple[bool, str]:
        """Send mouse long click (press and hold)"""
        try:
            import ctypes
            from ctypes import wintypes
            
            # Add timing delay before action
            time.sleep(0.1)
            
            # ALWAYS move cursor to position if specified
            if x is not None and y is not None:
                success, msg = self.set_cursor_position(x, y)
                if not success:
                    return False, f"Failed to move cursor: {msg}"
            else:
                cursor_pos = win32gui.GetCursorPos()
                x, y = cursor_pos
            
            # Map button to flags
            button_map = {
                "left": (0x0002, 0x0004),
                "right": (0x0008, 0x0010),
                "middle": (0x0020, 0x0040)
            }
            
            if button.lower() not in button_map:
                return False, f"Invalid button: {button}. Use left, right, or middle"
            
            down_flag, up_flag = button_map[button.lower()]
            
            # Mouse down
            inp = INPUT()
            inp.type = 0  # INPUT_MOUSE
            inp.mi.dx = 0
            inp.mi.dy = 0
            inp.mi.mouseData = 0
            inp.mi.dwFlags = down_flag
            inp.mi.time = 0
            inp.mi.dwExtraInfo = None
            
            user32 = ctypes.windll.user32
            user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
            
            # Hold for specified duration
            time.sleep(duration)
            
            # Mouse up
            inp.mi.dwFlags = up_flag
            user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
            
            monitor_id = self._get_cursor_monitor((x, y))
            return True, f"{button.capitalize()} long-click ({duration}s) at ({x}, {y}) on Monitor {monitor_id}"
            
        except Exception as e:
            return False, f"Failed to send long click: {e}"
    
    def send_mouse_scroll(self, direction: str, amount: int = 3, x: int = None, y: int = None) -> Tuple[bool, str]:
        """Send mouse scroll (up, down, left, right)"""
        try:
            import ctypes
            from ctypes import wintypes
            
            # Define mouse input structure
            class MOUSEINPUT(ctypes.Structure):
                _fields_ = [
                    ("dx", ctypes.c_long),
                    ("dy", ctypes.c_long),
                    ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))
                ]
            
            class INPUT(ctypes.Structure):
                class _INPUT(ctypes.Union):
                    _fields_ = [("mi", MOUSEINPUT)]
                _anonymous_ = ("_input",)
                _fields_ = [
                    ("type", wintypes.DWORD),
                    ("_input", _INPUT)
                ]
            
            # Move cursor to position if specified
            if x is not None and y is not None:
                success, msg = self.set_cursor_position(x, y)
                if not success:
                    return False, f"Failed to move cursor: {msg}"
            else:
                cursor_pos = win32gui.GetCursorPos()
                x, y = cursor_pos
            
            # Map direction to flags and data
            WHEEL_DELTA = 120  # Standard wheel delta
            
            direction_map = {
                "up": (0x0800, amount * WHEEL_DELTA),      # MOUSEEVENTF_WHEEL, positive
                "down": (0x0800, -amount * WHEEL_DELTA),   # MOUSEEVENTF_WHEEL, negative
                "left": (0x1000, -amount * WHEEL_DELTA),   # MOUSEEVENTF_HWHEEL, negative
                "right": (0x1000, amount * WHEEL_DELTA)    # MOUSEEVENTF_HWHEEL, positive
            }
            
            if direction.lower() not in direction_map:
                return False, f"Invalid direction: {direction}. Use up, down, left, or right"
            
            flag, wheel_data = direction_map[direction.lower()]
            
            # Create scroll input
            inp = INPUT()
            inp.type = 0  # INPUT_MOUSE
            inp.mi.dx = 0
            inp.mi.dy = 0
            inp.mi.mouseData = wheel_data
            inp.mi.dwFlags = flag
            inp.mi.time = 0
            inp.mi.dwExtraInfo = None
            
            # Send the input
            user32 = ctypes.windll.user32
            num_sent = user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
            
            if num_sent == 1:
                monitor_id = self._get_cursor_monitor((x, y))
                return True, f"Scroll {direction} (amount: {amount}) at ({x}, {y}) on Monitor {monitor_id}"
            else:
                return False, "Failed to send scroll event"
                
        except Exception as e:
            return False, f"Failed to send scroll: {e}"
    
    def send_mouse_drag(self, start_x: int, start_y: int, end_x: int, end_y: int, 
                       button: str = "left", duration: float = 0.5) -> Tuple[bool, str]:
        """Send mouse drag from start to end position"""
        try:
            import ctypes
            from ctypes import wintypes
            
            # Define mouse input structure
            class MOUSEINPUT(ctypes.Structure):
                _fields_ = [
                    ("dx", ctypes.c_long),
                    ("dy", ctypes.c_long),
                    ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))
                ]
            
            class INPUT(ctypes.Structure):
                class _INPUT(ctypes.Union):
                    _fields_ = [("mi", MOUSEINPUT)]
                _anonymous_ = ("_input",)
                _fields_ = [
                    ("type", wintypes.DWORD),
                    ("_input", _INPUT)
                ]
            
            # Map button to flags
            button_map = {
                "left": (0x0002, 0x0004),
                "right": (0x0008, 0x0010),
                "middle": (0x0020, 0x0040)
            }
            
            if button.lower() not in button_map:
                return False, f"Invalid button: {button}. Use left, right, or middle"
            
            down_flag, up_flag = button_map[button.lower()]
            
            # Move to start position
            self.set_cursor_position(start_x, start_y)
            time.sleep(0.1)
            
            # Mouse down at start
            inp = INPUT()
            inp.type = 0  # INPUT_MOUSE
            inp.mi.dx = 0
            inp.mi.dy = 0
            inp.mi.mouseData = 0
            inp.mi.dwFlags = down_flag
            inp.mi.time = 0
            inp.mi.dwExtraInfo = None
            
            user32 = ctypes.windll.user32
            user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
            
            # Calculate intermediate positions for smooth drag
            steps = max(10, int(duration * 20))  # 20 steps per second
            for i in range(steps + 1):
                progress = i / steps
                current_x = int(start_x + (end_x - start_x) * progress)
                current_y = int(start_y + (end_y - start_y) * progress)
                
                self.set_cursor_position(current_x, current_y)
                time.sleep(duration / steps)
            
            # Mouse up at end
            inp.mi.dwFlags = up_flag
            user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
            
            start_monitor = self._get_cursor_monitor((start_x, start_y))
            end_monitor = self._get_cursor_monitor((end_x, end_y))
            
            return True, f"{button.capitalize()} drag from ({start_x}, {start_y}) to ({end_x}, {end_y}) in {duration}s (Monitor {start_monitor}→{end_monitor})"
            
        except Exception as e:
            return False, f"Failed to send drag: {e}"

    def _execute_single_command(self, command_str: str) -> Tuple[bool, str]:
        """Execute a single command - used internally by command chain"""
        # This will be called from the test file's process_command method
        # We'll need to refactor the test file to support this
        pass

    def is_valid_window(self, hwnd: int) -> bool:
        """Check if window handle is still valid - SIMPLIFIED VERSION"""
        try:
            return win32gui.IsWindow(hwnd)
        except:
            return False
    


    def introspect_window(self, hwnd: int) -> Tuple[bool, str]:
        """Deep introspection of a window - like ShareX detection"""
        try:
            # Add timing delay
            time.sleep(0.1)
            
            if not self.is_valid_window(hwnd):
                return False, "Window is no longer valid"
            
            # Collect comprehensive window information
            introspection_data = {
                "basic_info": self._get_basic_window_info(hwnd),
                "hierarchy": self._get_window_hierarchy(hwnd),
                "ui_automation": self._get_ui_automation_info(hwnd),
                "regions": self._get_window_regions(hwnd),
                "class_info": self._get_window_class_info(hwnd),
                "process_info": self._get_window_process_info(hwnd)
            }
            
            # Format the output nicely
            output = self._format_introspection_output(introspection_data)
            return True, output
            
        except Exception as e:
            return False, f"Failed to introspect window: {e}"

    def _get_basic_window_info(self, hwnd: int) -> Dict:
        """Get basic window information"""
        try:
            rect = win32gui.GetWindowRect(hwnd)
            client_rect = win32gui.GetClientRect(hwnd)
            
            return {
                "hwnd": hwnd,
                "title": win32gui.GetWindowText(hwnd),
                "class_name": win32gui.GetClassName(hwnd),
                "window_rect": {"x": rect[0], "y": rect[1], "width": rect[2]-rect[0], "height": rect[3]-rect[1]},
                "client_rect": {"width": client_rect[2], "height": client_rect[3]},
                "visible": win32gui.IsWindowVisible(hwnd),
                "enabled": win32gui.IsWindowEnabled(hwnd),
                "state": self.get_window_state(hwnd),
                "z_order": self._get_window_z_order(hwnd),
                "has_menu": win32gui.GetMenu(hwnd) != 0,
                "is_unicode": win32gui.IsWindowUnicode(hwnd)
            }
        except Exception as e:
            return {"error": str(e)}

    def _get_window_hierarchy(self, hwnd: int) -> Dict:
        """Get window hierarchy information"""
        try:
            # Get parent window
            parent = win32gui.GetParent(hwnd)
            owner = win32gui.GetWindow(hwnd, win32con.GW_OWNER) if parent == 0 else None
            
            # Get child windows
            children = []
            def enum_child_proc(child_hwnd, lparam):
                try:
                    child_info = {
                        "hwnd": child_hwnd,
                        "title": win32gui.GetWindowText(child_hwnd),
                        "class_name": win32gui.GetClassName(child_hwnd),
                        "rect": win32gui.GetWindowRect(child_hwnd),
                        "visible": win32gui.IsWindowVisible(child_hwnd),
                        "control_id": win32gui.GetDlgCtrlID(child_hwnd)
                    }
                    children.append(child_info)
                except:
                    pass
                return True
            
            win32gui.EnumChildWindows(hwnd, enum_child_proc, 0)
            
            return {
                "parent": parent if parent != 0 else None,
                "owner": owner,
                "children_count": len(children),
                "children": children[:10],  # Limit to first 10 for readability
                "has_more_children": len(children) > 10
            }
        except Exception as e:
            return {"error": str(e)}

    def _get_ui_automation_info(self, hwnd: int) -> Dict:
        """Get UI Automation information (like ShareX detection)"""
        try:
            # Initialize UI Automation safely
            uia_obj, UIA = _initialize_ui_automation()
            if not uia_obj or not UIA:
                return {"error": "UI Automation not available"}
            
            element = uia_obj.ElementFromHandle(hwnd)
            
            if not element:
                return {"error": "Could not get UI Automation element"}
            
            # Get element properties
            automation_info = {
                "name": element.CurrentName or "",
                "automation_id": element.CurrentAutomationId or "",
                "control_type": self._get_control_type_name(element.CurrentControlType),
                "class_name": element.CurrentClassName or "",
                "framework_id": element.CurrentFrameworkId or "",
                "is_enabled": element.CurrentIsEnabled,
                "is_keyboard_focusable": element.CurrentIsKeyboardFocusable,
                "is_content_element": element.CurrentIsContentElement,
                "is_control_element": element.CurrentIsControlElement,
                "bounding_rectangle": self._get_automation_rect(element.CurrentBoundingRectangle),
                "help_text": element.CurrentHelpText or "",
                "accelerator_key": element.CurrentAcceleratorKey or "",
                "access_key": element.CurrentAccessKey or ""
            }
            
            # Get child elements for structure analysis
            child_elements = []
            try:
                children = element.FindAll(UIA.TreeScope_Children, uia_obj.CreateTrueCondition())
                for i in range(min(children.Length, 10)):  # Limit to 10 children
                    child = children.GetElement(i)
                    child_info = {
                        "name": child.CurrentName or "",
                        "control_type": self._get_control_type_name(child.CurrentControlType),
                        "class_name": child.CurrentClassName or "",
                        "rect": self._get_automation_rect(child.CurrentBoundingRectangle)
                    }
                    child_elements.append(child_info)
            except:
                pass
            
            automation_info["ui_children"] = child_elements
            automation_info["ui_children_count"] = len(child_elements)
            
            return automation_info
            
        except Exception as e:
            return {"error": f"UI Automation failed: {e}"}

    def _get_window_regions(self, hwnd: int) -> Dict:
        """Detect different regions within the window"""
        try:
            window_rect = win32gui.GetWindowRect(hwnd)
            client_rect = win32gui.GetClientRect(hwnd)
            
            # Calculate border sizes
            border_x = (window_rect[2] - window_rect[0] - client_rect[2]) // 2
            border_y = (window_rect[3] - window_rect[1] - client_rect[3]) - border_x
            
            regions = {
                "title_bar": {
                    "x": window_rect[0],
                    "y": window_rect[1], 
                    "width": window_rect[2] - window_rect[0],
                    "height": border_y
                },
                "client_area": {
                    "x": window_rect[0] + border_x,
                    "y": window_rect[1] + border_y,
                    "width": client_rect[2],
                    "height": client_rect[3]
                },
                "borders": {
                    "left": border_x,
                    "right": border_x, 
                    "top": border_y,
                    "bottom": border_x
                }
            }
            
            # Try to detect specific regions using point testing
            test_points = self._get_region_test_points(window_rect, client_rect)
            region_detection = {}
            
            for region_name, point in test_points.items():
                try:
                    child_hwnd = win32gui.ChildWindowFromPoint(hwnd, (point[0] - window_rect[0], point[1] - window_rect[1]))
                    if child_hwnd and child_hwnd != hwnd:
                        region_detection[region_name] = {
                            "detected": True,
                            "child_hwnd": child_hwnd,
                            "class_name": win32gui.GetClassName(child_hwnd),
                            "title": win32gui.GetWindowText(child_hwnd)
                        }
                    else:
                        region_detection[region_name] = {"detected": False}
                except:
                    region_detection[region_name] = {"detected": False, "error": "Detection failed"}
            
            return {
                "calculated_regions": regions,
                "detected_controls": region_detection
            }
            
        except Exception as e:
            return {"error": str(e)}

    def _get_window_class_info(self, hwnd: int) -> Dict:
        """Get detailed window class information"""
        try:
            class_name = win32gui.GetClassName(hwnd)
            
            # Get window style and extended style
            style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            
            # Decode common window styles
            style_flags = self._decode_window_styles(style)
            ex_style_flags = self._decode_extended_styles(ex_style)
            
            return {
                "class_name": class_name,
                "window_style": hex(style),
                "extended_style": hex(ex_style),
                "style_flags": style_flags,
                "extended_style_flags": ex_style_flags,
                "class_type": self._classify_window_type(class_name, style)
            }
        except Exception as e:
            return {"error": str(e)}

    def _get_window_process_info(self, hwnd: int) -> Dict:
        """Get detailed process information"""
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            
            try:
                process = psutil.Process(pid)
                return {
                    "pid": pid,
                    "name": process.name(),
                    "exe": process.exe(),
                    "cmdline": " ".join(process.cmdline()),
                    "memory_usage": process.memory_info().rss,
                    "cpu_percent": process.cpu_percent(),
                    "create_time": process.create_time(),
                    "num_threads": process.num_threads()
                }
            except psutil.NoSuchProcess:
                return {"pid": pid, "error": "Process no longer exists"}
        except Exception as e:
            return {"error": str(e)}

    def _get_control_type_name(self, control_type: int) -> str:
        """Convert UI Automation control type to readable name"""
        control_types = {
            50000: "Button", 50001: "Calendar", 50002: "CheckBox", 50003: "ComboBox",
            50004: "Edit", 50005: "Hyperlink", 50006: "Image", 50007: "ListItem",
            50008: "List", 50009: "Menu", 50010: "MenuBar", 50011: "MenuItem",
            50012: "ProgressBar", 50013: "RadioButton", 50014: "ScrollBar",
            50015: "Slider", 50016: "Spinner", 50017: "StatusBar", 50018: "Tab",
            50019: "TabItem", 50020: "Text", 50021: "ToolBar", 50022: "ToolTip",
            50023: "Tree", 50024: "TreeItem", 50025: "Custom", 50026: "Group",
            50027: "Thumb", 50028: "DataGrid", 50029: "DataItem", 50030: "Document",
            50031: "SplitButton", 50032: "Window", 50033: "Pane", 50034: "Header",
            50035: "HeaderItem", 50036: "Table", 50037: "TitleBar", 50038: "Separator"
        }
        return control_types.get(control_type, f"Unknown({control_type})")

    def _get_automation_rect(self, rect) -> Dict:
        """Convert UI Automation rectangle to dict"""
        try:
            return {
                "x": int(rect.left),
                "y": int(rect.top), 
                "width": int(rect.right - rect.left),
                "height": int(rect.bottom - rect.top)
            }
        except:
            return {"x": 0, "y": 0, "width": 0, "height": 0}

    def _get_window_z_order(self, hwnd: int) -> int:
        """Get window Z-order position"""
        try:
            z_order = 0
            current = win32gui.GetWindow(hwnd, win32con.GW_HWNDFIRST)
            while current:
                if current == hwnd:
                    return z_order
                z_order += 1
                current = win32gui.GetWindow(current, win32con.GW_HWNDNEXT)
            return -1
        except:
            return -1

    def _get_region_test_points(self, window_rect: tuple, client_rect: tuple) -> Dict:
        """Generate test points for different window regions"""
        wx, wy, wr, wb = window_rect
        cw, ch = client_rect[2], client_rect[3]
        
        return {
            "title_bar_center": (wx + (wr-wx)//2, wy + 10),
            "client_top_left": (wx + 10, wy + 30),
            "client_center": (wx + (wr-wx)//2, wy + (wb-wy)//2),
            "client_bottom_right": (wr - 10, wb - 10)
        }

    def _decode_window_styles(self, style: int) -> List[str]:
        """Decode window style flags"""
        styles = []
        style_map = {
            0x10000000: "WS_VISIBLE",
            0x00C00000: "WS_CAPTION", 
            0x00080000: "WS_SYSMENU",
            0x00040000: "WS_THICKFRAME",
            0x00020000: "WS_MINIMIZEBOX",
            0x00010000: "WS_MAXIMIZEBOX",
            0x20000000: "WS_MINIMIZE",
            0x01000000: "WS_MAXIMIZE"
        }
        
        for flag, name in style_map.items():
            if style & flag:
                styles.append(name)
        return styles

    def _decode_extended_styles(self, ex_style: int) -> List[str]:
        """Decode extended window style flags"""
        styles = []
        ex_style_map = {
            0x00000080: "WS_EX_TOOLWINDOW",
            0x00000008: "WS_EX_TOPMOST", 
            0x00000200: "WS_EX_ACCEPTFILES",
            0x00080000: "WS_EX_LAYERED",
            0x08000000: "WS_EX_NOACTIVATE"
        }
        
        for flag, name in ex_style_map.items():
            if ex_style & flag:
                styles.append(name)
        return styles

    def _classify_window_type(self, class_name: str, style: int) -> str:
        """Classify window type based on class name and style"""
        if "Chrome" in class_name:
            return "Browser"
        elif class_name in ["Notepad", "Edit", "WordPadClass"]:
            return "Text Editor"
        elif class_name == "CabinetWClass":
            return "File Explorer"
        elif style & 0x00C00000:  # WS_CAPTION
            return "Application Window"
        elif style & 0x00000080:  # WS_EX_TOOLWINDOW
            return "Tool Window"
        else:
            return "Unknown"

    def _format_introspection_output(self, data: Dict) -> str:
        """Format introspection data for readable output"""
        output = []
        
        # Basic Info
        basic = data.get("basic_info", {})
        output.append("🔍 WINDOW INTROSPECTION")
        output.append("=" * 50)
        output.append(f"📱 Title: {basic.get('title', 'N/A')}")
        output.append(f"🆔 HWND: {basic.get('hwnd', 'N/A')}")
        output.append(f"📏 Size: {basic.get('window_rect', {}).get('width', 0)}x{basic.get('window_rect', {}).get('height', 0)}")
        output.append(f"📍 Position: ({basic.get('window_rect', {}).get('x', 0)}, {basic.get('window_rect', {}).get('y', 0)})")
        output.append(f"🎯 State: {basic.get('state', 'unknown')}")
        output.append(f"👁️  Visible: {basic.get('visible', False)}")
        output.append(f"📊 Z-Order: {basic.get('z_order', -1)}")
        
        # Class Info
        class_info = data.get("class_info", {})
        output.append(f"\n🏷️  CLASS INFORMATION")
        output.append(f"📋 Class Name: {class_info.get('class_name', 'N/A')}")
        output.append(f"🎨 Window Type: {class_info.get('class_type', 'Unknown')}")
        output.append(f"⚙️  Style Flags: {', '.join(class_info.get('style_flags', []))}")
        
        # Process Info
        process = data.get("process_info", {})
        if "error" not in process:
            output.append(f"\n⚡ PROCESS INFORMATION")
            output.append(f"🔢 PID: {process.get('pid', 'N/A')}")
            output.append(f"📂 Process: {process.get('name', 'N/A')}")
            output.append(f"💾 Memory: {process.get('memory_usage', 0) // (1024*1024)} MB")
        
        # UI Automation
        ui_auto = data.get("ui_automation", {})
        if "error" not in ui_auto:
            output.append(f"\n🤖 UI AUTOMATION ANALYSIS")
            output.append(f"🏷️  Control Type: {ui_auto.get('control_type', 'N/A')}")
            output.append(f"🆔 Automation ID: {ui_auto.get('automation_id', 'N/A')}")
            output.append(f"🖼️  Framework: {ui_auto.get('framework_id', 'N/A')}")
        
        return "\n".join(output)

    # Add this method to the WindowManager class (around line 1800):

    def get_element_under_cursor(self) -> Tuple[bool, str]:
        """Get detailed info about UI element under mouse cursor (like ShareX)"""
        try:
            cursor_pos = win32gui.GetCursorPos()
            x, y = cursor_pos
            
            # Get window under cursor
            hwnd = win32gui.WindowFromPoint(cursor_pos)
            if not hwnd:
                return False, "No window found under cursor"
            
            # Get window hierarchy
            root_hwnd = hwnd
            while True:
                parent = win32gui.GetParent(root_hwnd)
                if parent == 0:
                    break
                root_hwnd = parent
            
            # Get basic info
            window_title = win32gui.GetWindowText(hwnd)
            window_class = win32gui.GetClassName(hwnd)
            window_rect = win32gui.GetWindowRect(hwnd)
            
            # ENHANCED: Classify the UI region type
            region_type = self._classify_ui_region(window_class, window_rect, root_hwnd)
            
            output = []
            output.append(f"🎯 ELEMENT UNDER CURSOR ({x}, {y})")
            output.append("=" * 50)
            output.append(f"🎨 UI Region Type: {region_type}")
            output.append(f"🪟 Window: {window_title or 'Untitled'}")
            output.append(f"🏷️  Class: {window_class}")
            output.append(f"🆔 HWND: {hwnd}")
            output.append(f"📏 Size: {window_rect[2]-window_rect[0]}×{window_rect[3]-window_rect[1]}")
            output.append(f"📍 Position: ({window_rect[0]}, {window_rect[1]})")
            
            # Show relative position within parent
            if root_hwnd != hwnd:
                root_title = win32gui.GetWindowText(root_hwnd)
                root_class = win32gui.GetClassName(root_hwnd)
                root_rect = win32gui.GetWindowRect(root_hwnd)
                
                rel_x = window_rect[0] - root_rect[0]
                rel_y = window_rect[1] - root_rect[1]
                
                output.append(f"\n🏠 Parent Application: {root_title or 'Untitled'}")
                output.append(f"🏷️  Parent Class: {root_class}")
                output.append(f"📍 Relative Position: ({rel_x}, {rel_y}) within parent")
                
                # Detect what area of the application this is
                app_region = self._detect_application_region(window_rect, root_rect, window_class)
                output.append(f"🎯 Application Region: {app_region}")
            
            # Get child windows/controls in this area
            children = self._get_nearby_controls(hwnd, cursor_pos)
            if children:
                output.append(f"\n🔍 Nearby Controls:")
                for child in children[:3]:  # Show first 3
                    output.append(f"   • {child['class']} - {child['title'][:30]}")
            
            return True, "\n".join(output)
            
        except Exception as e:
            return False, f"Failed to get element under cursor: {e}"

    def _classify_ui_region(self, class_name: str, rect: tuple, root_hwnd: int) -> str:
        """Classify what type of UI region this is"""
        width = rect[2] - rect[0]
        height = rect[3] - rect[1]
        
        # Office applications
        if "NetUIHWND" in class_name:
            return "🎀 RIBBON/TOOLBAR"
        elif "_WwG" in class_name or "OpusApp" in class_name:
            return "📄 DOCUMENT/CONTENT AREA"
        elif "StatusBar" in class_name:
            return "📊 STATUS BAR"
        
        # Browser
        elif "Chrome" in class_name:
            if height < 100:
                return "🌐 BROWSER TOOLBAR"
            else:
                return "🌐 WEB CONTENT"
        
        # Common patterns
        elif height < 50:
            return "🔧 TOOLBAR/MENU"
        elif width > height * 3:
            return "📏 HORIZONTAL PANEL"
        elif height > width * 2:
            return "📐 VERTICAL PANEL"
        else:
            return "🖼️ CONTENT AREA"

    def _detect_application_region(self, window_rect: tuple, parent_rect: tuple, class_name: str) -> str:
        """Detect which part of the application window this control is in"""
        wx, wy = window_rect[0], window_rect[1]
        px, py, pr, pb = parent_rect
        
        # Relative position within parent
        rel_x = (wx - px) / (pr - px) if pr != px else 0
        rel_y = (wy - py) / (pb - py) if pb != py else 0
        
        if rel_y < 0.2:
            return "🔝 TOP (Likely ribbon/menu area)"
        elif rel_y > 0.9:
            return "🔽 BOTTOM (Likely status bar)"
        elif rel_x < 0.1:
            return "◀️ LEFT SIDE (Likely sidebar/navigation)"
        elif rel_x > 0.9:
            return "▶️ RIGHT SIDE (Likely properties/tools)"
        else:
            return "🎯 CENTER (Likely main content)"

    def _get_nearby_controls(self, hwnd: int, cursor_pos: tuple) -> List[Dict]:
        """Get controls near the cursor position"""
        controls = []
        x, y = cursor_pos
        
        # Check for sibling windows (same parent)
        try:
            parent = win32gui.GetParent(hwnd)
            if parent:
                def enum_siblings(sibling_hwnd, lparam):
                    if sibling_hwnd != hwnd and win32gui.IsWindowVisible(sibling_hwnd):
                        rect = win32gui.GetWindowRect(sibling_hwnd)
                        # Check if it's near our cursor (within 200 pixels)
                        if (abs(rect[0] - x) < 200 or abs(rect[2] - x) < 200) and \
                           (abs(rect[1] - y) < 200 or abs(rect[3] - y) < 200):
                            controls.append({
                                'hwnd': sibling_hwnd,
                                'title': win32gui.GetWindowText(sibling_hwnd),
                                'class': win32gui.GetClassName(sibling_hwnd),
                                'rect': rect
                            })
                    return True
                
                win32gui.EnumChildWindows(parent, enum_siblings, 0)
        except:
            pass
        
        return controls

    def get_window_hierarchy_tree(self, hwnd: int) -> Tuple[bool, str]:
        """Get complete hierarchical tree of all UI regions in a window"""
        try:
            time.sleep(0.1)
            
            if not self.is_valid_window(hwnd):
                return False, "Window is no longer valid"
            
            # Build the complete tree structure
            tree = self._build_window_tree(hwnd, 0)
            
            # Format as readable tree
            output = self._format_hierarchy_tree(tree)
            
            return True, output
            
        except Exception as e:
            return False, f"Failed to get window hierarchy: {e}"

    def _build_window_tree(self, hwnd: int, depth: int) -> Dict:
        """Recursively build window hierarchy tree"""
        try:
            # Get basic window info
            rect = win32gui.GetWindowRect(hwnd)
            title = win32gui.GetWindowText(hwnd)
            class_name = win32gui.GetClassName(hwnd)
            visible = win32gui.IsWindowVisible(hwnd)
            
            node = {
                'hwnd': hwnd,
                'title': title,
                'class': class_name,
                'rect': rect,
                'size': (rect[2] - rect[0], rect[3] - rect[1]),
                'visible': visible,
                'depth': depth,
                'children': []
            }
            
            # Get all child windows
            def enum_child_proc(child_hwnd, lparam):
                try:
                    # Only include visible children with reasonable size
                    if win32gui.IsWindowVisible(child_hwnd):
                        child_rect = win32gui.GetWindowRect(child_hwnd)
                        width = child_rect[2] - child_rect[0]
                        height = child_rect[3] - child_rect[1]
                        
                        # Skip tiny elements (< 5px) - usually artifacts
                        if width >= 5 and height >= 5:
                            child_tree = self._build_window_tree(child_hwnd, depth + 1)
                            node['children'].append(child_tree)
                except:
                    pass
                return True
            
            win32gui.EnumChildWindows(hwnd, enum_child_proc, 0)
            
            # Sort children by position (top-to-bottom, left-to-right)
            node['children'].sort(key=lambda x: (x['rect'][1], x['rect'][0]))
            
            return node
            
        except Exception as e:
            return {'hwnd': hwnd, 'error': str(e), 'children': []}

    def _format_hierarchy_tree(self, tree: Dict) -> str:
        """Format tree as readable hierarchical structure"""
        output = []
        
        def format_node(node, prefix=""):
            try:
                hwnd = node['hwnd']
                title = node.get('title', '')
                class_name = node.get('class', '')
                size = node.get('size', (0, 0))
                rect = node.get('rect', (0, 0, 0, 0))
                
                # Format the line
                title_display = title[:40] + "..." if len(title) > 40 else title
                title_display = title_display or "Untitled"
                
                line = f"{prefix}├─ {title_display}"
                line += f" [{class_name}]"
                line += f" {size[0]}×{size[1]}"
                line += f" @({rect[0]},{rect[1]})"
                line += f" HWND:{hwnd}"
                
                output.append(line)
                
                # Process children
                children = node.get('children', [])
                for i, child in enumerate(children):
                    is_last = (i == len(children) - 1)
                    child_prefix = prefix + ("    " if is_last else "│   ")
                    format_node(child, child_prefix)
                    
            except Exception as e:
                output.append(f"{prefix}├─ ERROR: {e}")
        
        # Header
        root_title = tree.get('title', 'Unknown Window')
        root_class = tree.get('class', 'Unknown')
        root_size = tree.get('size', (0, 0))
        
        output.append(f"🌳 WINDOW HIERARCHY TREE")
        output.append(f"═" * 60)
        output.append(f"🏠 Root: {root_title} [{root_class}] {root_size[0]}×{root_size[1]}")
        output.append("")
        
        # Root children
        children = tree.get('children', [])
        for i, child in enumerate(children):
            is_last = (i == len(children) - 1)
            child_prefix = "    " if is_last else "│   "
            format_node(child, child_prefix)
        
        if not children:
            output.append("└─ (No child windows detected)")
        
        output.append("")
        output.append(f"📊 Total regions found: {self._count_nodes(tree)}")
        
        return "\n".join(output)

    def _count_nodes(self, tree: Dict) -> int:
        """Count total nodes in tree"""
        count = 1  # Count this node
        for child in tree.get('children', []):
            count += self._count_nodes(child)
        return count

    def launch_application(self, app_name: str, screen_id: int, fullscreen: bool = True) -> Tuple[bool, str]:
        """
        Launch an application on a specific screen in fullscreen mode
        
        Args:
            app_name: Name/path of the application to launch
            screen_id: Screen ID (1-based) to launch the app on
            fullscreen: Whether to make the app fullscreen (default: True)
            
        Returns:
            Tuple[bool, str]: (success, message)
        """
        try:
            time.sleep(0.1)
            
            # Validate screen ID
            if screen_id < 1 or screen_id > len(self.monitors):
                return False, f"Invalid screen ID {screen_id}. Available screens: 1-{len(self.monitors)}"
            
            target_monitor = self.monitors[screen_id - 1]
            
            # Check if app is already running
            existing_windows = self.find_window_by_app(app_name)
            if existing_windows:
                # App already running - warn user
                running_instances = len(existing_windows)
                window_details = []
                for window in existing_windows[:3]:  # Show first 3 instances
                    screen = window.get('screen', 'Unknown')
                    title = window.get('title', 'Untitled')[:30]
                    window_details.append(f"'{title}' on Screen {screen}")
                
                details_str = ", ".join(window_details)
                if running_instances > 3:
                    details_str += f" and {running_instances - 3} more"
                
                return False, f"⚠️  Application '{app_name}' is already running ({running_instances} instance{'s' if running_instances > 1 else ''}): {details_str}. Some applications don't support multiple instances."
            
            # Try to launch the application
            import subprocess
            
            # Get the full path if it's just an app name
            app_path = self._resolve_application_path(app_name)
            if not app_path:
                return False, f"Could not find application: {app_name}"
            
            print(f"Launching: {app_path}")
            
            # Launch the application
            try:
                process = subprocess.Popen(app_path, shell=True)
                launched_pid = process.pid
            except Exception as e:
                return False, f"Failed to launch application: {e}"
            
            # Wait for the window to appear (with timeout)
            new_window_hwnd = None
            max_wait_time = 20  # 10 seconds timeout
            wait_interval = 0.5
            elapsed_time = 0
            
            print(f"Waiting for window to appear (PID: {launched_pid})...")
            
            while elapsed_time < max_wait_time and not new_window_hwnd:
                time.sleep(wait_interval)
                elapsed_time += wait_interval
                
                # Look for new windows using the correct method
                current_windows = self.get_all_windows()
                for window in current_windows:
                    # Try to match by process name or PID
                    window_proc = window.get('proc', '').lower()
                    app_name_lower = app_name.lower()
                    
                    if (app_name_lower in window_proc or 
                        window_proc.replace('.exe', '') in app_name_lower or
                        window.get('pid') == launched_pid):
                        new_window_hwnd = window['hwnd']
                        print(f"Found new window: {window.get('title', 'Untitled')} (HWND: {new_window_hwnd})")
                        break
            
            if not new_window_hwnd:
                return False, f"Application launched but window not detected within {max_wait_time} seconds. It may still be starting up."
            
            # Move window to target screen and make fullscreen
            success_move = self.move_window_to_monitor(new_window_hwnd, screen_id)
            if not success_move[0]:
                return False, f"Application launched but failed to move to screen {screen_id}: {success_move[1]}"
            
            time.sleep(0.5)  # Let the move complete
            
            if fullscreen:
                # Maximize the window to make it fullscreen
                success_max = self.maximize_window(new_window_hwnd)
                if not success_max[0]:
                    return False, f"Application launched and moved to screen {screen_id} but failed to maximize: {success_max[1]}"
                
                return True, f"✅ Successfully launched '{app_name}' on Screen {screen_id} in fullscreen mode"
            else:
                return True, f"✅ Successfully launched '{app_name}' on Screen {screen_id}"
                
        except Exception as e:
            return False, f"Failed to launch application: {e}"

    def _resolve_application_path(self, app_name: str) -> Optional[str]:
        """
        Resolve application name to full path using JSON configuration
        """
        # If it's already a full path, return as-is
        if os.path.isfile(app_name):
            return app_name
        
        # Load application mappings from JSON
        app_mappings = self._load_application_mappings()
        
        app_key = app_name.lower().replace('.exe', '')
        if app_key in app_mappings:
            mapped_paths = app_mappings[app_key]
            if isinstance(mapped_paths, list):
                # Try multiple paths for Office apps
                for path in mapped_paths:
                    resolved_path = self._resolve_path_variables(path)
                    if os.path.isfile(resolved_path):
                        return resolved_path
            else:
                # Single path
                resolved_path = self._resolve_path_variables(mapped_paths)
                if os.path.isfile(resolved_path):
                    return resolved_path
        
        # Try Windows PATH
        try:
            app_name_exe = app_name if app_name.endswith('.exe') else app_name + '.exe'
            path = shutil.which(app_name_exe)
            if path:
                return path
        except:
            pass
        
        # Last resort
        return app_name

    def _load_application_mappings(self) -> Dict:
        """Load application mappings from JSON file"""
        try:
            json_path = os.path.join(os.path.dirname(__file__), 'safe_applications.json')
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('applications', {})
        except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
            print(f"Warning: Could not load application mappings: {e}")
            # Fallback to basic mappings
            return {
                'notepad': 'notepad.exe',
                'calc': 'calc.exe',
                'paint': 'mspaint.exe'
            }

    def _resolve_path_variables(self, path: str) -> str:
        """Resolve path variables like {USER}"""
        if '{USER}' in path:
            path = path.replace('{USER}', getpass.getuser())
        return path

    def get_all_windows(self) -> List[Dict]:
        """Get all visible windows across all monitors"""
        data = self.get_structured_windows()
        all_windows = []
        
        for monitor_data in data["monitors"].values():
            for app_data in monitor_data["applications"].values():
                for window_data in app_data["windows"].values():
                    # Convert to the expected format
                    window_dict = {
                        "hwnd": window_data['hwnd'],
                        "title": window_data['title'],
                        "pid": window_data['pid'],
                        "proc": app_data['process_name'],
                        "rect": [
                            window_data['position']['x'],
                            window_data['position']['y'],
                            window_data['position']['x'] + window_data['size']['width'],
                            window_data['position']['y'] + window_data['size']['height']
                        ],
                        "screen": window_data['monitor'],
                        "minimized": window_data['minimized']
                    }
                    all_windows.append(window_dict)
        
        return all_windows

    def send_esc_enhanced(self) -> Tuple[bool, str]:
        """Enhanced ESC with multiple methods for better dialog compatibility"""
        methods_tried = []
        
        # Method 1: SendInput (prioritize this for dialogs)
        try:
            success = self._send_esc_via_sendinput_direct()
            if success:
                return True, "ESC sent via SendInput (enhanced)"
            methods_tried.append("SendInput failed")
        except Exception as e:
            methods_tried.append(f"SendInput error: {e}")
        
        # Method 2: PostMessage to foreground window (better for modal dialogs)
        try:
            success = self._send_esc_via_postmessage_direct()
            if success:
                return True, "ESC sent via PostMessage (enhanced)"
            methods_tried.append("PostMessage failed")
        except Exception as e:
            methods_tried.append(f"PostMessage error: {e}")
        
        # Method 3: Fall back to existing logic
        try:
            return self.send_key_combination("ESC")
        except Exception as e:
            methods_tried.append(f"Standard method error: {e}")
        
        return False, f"All ESC methods failed: {'; '.join(methods_tried)}"

    def _send_esc_via_sendinput_direct(self) -> bool:
        """Direct SendInput for ESC key only"""
        import ctypes
        from ctypes import wintypes
        
        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), 
                       ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                       ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))]
        
        class INPUT(ctypes.Structure):
            class _INPUT(ctypes.Union):
                _fields_ = [("ki", KEYBDINPUT)]
            _anonymous_ = ("_input",)
            _fields_ = [("type", wintypes.DWORD), ("_input", _INPUT)]
        
        VK_ESCAPE = 0x1B
        inputs = []
        
        # Key down
        inp = INPUT()
        inp.type = 1  # INPUT_KEYBOARD
        inp.ki.wVk = VK_ESCAPE
        inp.ki.dwFlags = 0
        inputs.append(inp)
        
        # Key up  
        inp = INPUT()
        inp.type = 1
        inp.ki.wVk = VK_ESCAPE
        inp.ki.dwFlags = 2  # KEYEVENTF_KEYUP
        inputs.append(inp)
        
        user32 = ctypes.windll.user32
        num_sent = user32.SendInput(len(inputs), (INPUT * len(inputs))(*inputs), ctypes.sizeof(INPUT))
        return num_sent == len(inputs)

    def _send_esc_via_postmessage_direct(self) -> bool:
        """Direct PostMessage for ESC key"""
        import win32gui
        
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return False
        
        WM_KEYDOWN, WM_KEYUP, VK_ESCAPE = 0x0100, 0x0101, 0x1B
        
        result1 = win32gui.PostMessage(hwnd, WM_KEYDOWN, VK_ESCAPE, 0)
        time.sleep(0.05)
        result2 = win32gui.PostMessage(hwnd, WM_KEYUP, VK_ESCAPE, 0)
        
        return result1 != 0 and result2 != 0


# Example usage and testing
if __name__ == "__main__":
    wm = WindowManager()
    
    # Print structured output
    wm.print_structured_output(show_minimized=True)
    
    print("\n" + "="*40 + " JSON OUTPUT " + "="*40)
    # Show JSON format
    data = wm.get_structured_windows()
    print(json.dumps(data, indent=2, default=str))
