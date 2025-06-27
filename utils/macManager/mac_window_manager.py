#!/usr/bin/env python3
"""
Mac Window Manager - Comprehensive window and system automation for macOS
Equivalent to the Windows window_manager.py but using macOS APIs
"""

import time
import json
import hashlib
import os
import getpass
import ctypes
from typing import List, Dict, Optional, Tuple, Any
import subprocess
import sys

# macOS-specific imports
try:
    import Quartz
    from Quartz import (
        CGDisplayCopyAllDisplayModes, CGMainDisplayID, CGDisplayBounds,
        CGDisplayCreateImage, CGWindowListCopyWindowInfo, kCGWindowListOptionOnScreenOnly,
        kCGNullWindowID, kCGWindowListExcludeDesktopElements, CGEventCreateMouseEvent,
        CGEventPost, kCGHIDEventTap, CGEventCreateKeyboardEvent, CGEventSetFlags,
        kCGEventMouseMoved, kCGEventLeftMouseDown, kCGEventLeftMouseUp,
        kCGEventRightMouseDown, kCGEventRightMouseUp, kCGEventOtherMouseDown,
        kCGEventOtherMouseUp, kCGEventKeyDown, kCGEventKeyUp, kCGEventScrollWheel,
        CGEventSourceCreate, kCGEventSourceStateHIDSystemState, CGDisplayMoveCursorToPoint,
        CGEventGetLocation, CGEventCreate, kCGEventMouseMoved, CGDisplayPixelsHigh,
        CGDisplayPixelsWide, CGRectMake, CGDisplayIDToOpenGLDisplayMask,
        kCGEventLeftMouseDragged
    )
    
    # Try to import additional functions, with fallbacks if not available
    try:
        from Quartz import CGEventKeyboardSetUnicodeString
    except ImportError:
        CGEventKeyboardSetUnicodeString = None
    
    try:
        from Quartz import CGEventCreateScrollWheelEvent, kCGScrollEventUnitPixel
    except ImportError:
        CGEventCreateScrollWheelEvent = None
        kCGScrollEventUnitPixel = None
    
    try:
        from Quartz import CGEventSetLocation
    except ImportError:
        CGEventSetLocation = None
    
    from AppKit import (
        NSWorkspace, NSApplication, NSScreen, NSWindow, NSApp,
        NSApplicationActivateIgnoringOtherApps, NSRunningApplication,
        NSWorkspaceDidActivateApplicationNotification, NSNotificationCenter,
        NSAlert, NSInformationalAlertStyle, NSModalResponseOK, NSCursor,
        NSEvent, NSWorkspaceLaunchConfigurationArguments,  # Add this
        NSWorkspaceLaunchConfigurationEnvironment,  # And this
        NSWorkspaceLaunchDefault  # And this
    )
    
    from Foundation import (
        NSString, NSArray, NSDictionary, NSNumber, NSDate, NSBundle,
        NSProcessInfo, NSHost, NSFileManager, NSHomeDirectory, NSURL,
        NSUserDefaults, NSTimer, NSRunLoop, NSDefaultRunLoopMode, NSValue
    )
    
    import objc
    from CoreFoundation import (
        CFArrayGetCount, CFArrayGetValueAtIndex, CFStringRef,
        CFNumberRef, CFDictionaryRef, CFArrayRef
    )
    
    MACOS_APIS_AVAILABLE = True
    
except ImportError as e:
    print(f"Warning: macOS APIs not available: {e}")
    print("Please install PyObjC: pip install pyobjc")
    MACOS_APIS_AVAILABLE = False
    # Create dummy objects to prevent import errors
    class DummyClass:
        pass
    Quartz = AppKit = Foundation = objc = DummyClass()

# Accessibility API imports
try:
    from ApplicationServices import (
        AXUIElementCreateApplication, AXUIElementCopyAttributeNames,
        AXUIElementCopyAttributeValue, AXUIElementGetPid, AXUIElementCreateSystemWide,
        AXUIElementCopyElementAtPosition, kAXTitleAttribute, kAXRoleAttribute,
        kAXPositionAttribute, kAXSizeAttribute, kAXWindowsAttribute, kAXFocusedWindowAttribute,
        kAXMinimizedAttribute, kAXMainAttribute, kAXChildrenAttribute, kAXParentAttribute,
        AXUIElementSetAttributeValue, kAXRaisedAttribute, AXUIElementPerformAction,
        kAXRaiseAction, kAXPressAction, AXIsProcessTrusted, AXUIElementCopyParameterizedAttributeNames
    )
    ACCESSIBILITY_AVAILABLE = True
except ImportError:
    print("Warning: Accessibility APIs not available")
    ACCESSIBILITY_AVAILABLE = False

class MacWindowManager:
    def __init__(self):
        """Initialize the Mac Window Manager"""
        if not MACOS_APIS_AVAILABLE:
            raise ImportError("macOS APIs not available. Please install PyObjC: pip install pyobjc")
        
        # Check accessibility permissions
        if ACCESSIBILITY_AVAILABLE and not AXIsProcessTrusted():
            print("⚠️  WARNING: Accessibility permissions not granted!")
            print("Please go to System Preferences > Security & Privacy > Privacy > Accessibility")
            print("and add your terminal application (Terminal, iTerm2, etc.) to the allowed list.")
            print("Some features may not work without accessibility permissions.")
            
        # Initialize display information
        self.displays = self._get_displays()
        self._previous_windows = {}  # Track windows for change detection
        self.workspace = NSWorkspace.sharedWorkspace()
        
    def _get_displays(self) -> List[Dict]:
        """Get information about all connected displays"""
        displays = []
        
        try:
            # Get all active displays
            max_displays = 32
            active_displays = (Quartz.CGDirectDisplayID * max_displays)()
            display_count = Quartz.CGGetActiveDisplayList(max_displays, active_displays, None)
            
            for i in range(display_count):
                display_id = active_displays[i]
                
                # Get display bounds
                bounds = Quartz.CGDisplayBounds(display_id)
                width = int(bounds.size.width)
                height = int(bounds.size.height)
                x = int(bounds.origin.x)
                y = int(bounds.origin.y)
                
                # Check if this is the main display
                is_main = (display_id == Quartz.CGMainDisplayID())
                
                display_info = {
                    'id': int(display_id),
                    'bounds': {
                        'x': x, 'y': y, 'width': width, 'height': height
                    },
                    'size': {'width': width, 'height': height},
                    'origin': {'x': x, 'y': y},
                    'is_main': is_main,
                    'index': i + 1,  # 1-based indexing for user interface
                }
                
                displays.append(display_info)
                
            # Sort displays: main first, then by position
            displays.sort(key=lambda d: (not d['is_main'], d['origin']['x'], d['origin']['y']))
            
            print(f"Detected {len(displays)} display(s):")
            for i, display in enumerate(displays):
                main_indicator = " (Main)" if display['is_main'] else ""
                print(f"  Display {i+1}: {display['size']['width']}x{display['size']['height']} "
                      f"at ({display['origin']['x']}, {display['origin']['y']}){main_indicator}")
                      
        except Exception as e:
            print(f"Error detecting displays: {e}")
            # Fallback to main display
            main_id = Quartz.CGMainDisplayID()
            bounds = Quartz.CGDisplayBounds(main_id)
            displays = [{
                'id': int(main_id),
                'bounds': {'x': 0, 'y': 0, 'width': int(bounds.size.width), 'height': int(bounds.size.height)},
                'size': {'width': int(bounds.size.width), 'height': int(bounds.size.height)},
                'origin': {'x': 0, 'y': 0},
                'is_main': True,
                'index': 1
            }]
            
        return displays

    def _get_window_display(self, window_bounds: Dict) -> int:
        """Determine which display a window is primarily on"""
        window_center_x = window_bounds['x'] + window_bounds['width'] // 2
        window_center_y = window_bounds['y'] + window_bounds['height'] // 2
        
        for display in self.displays:
            bounds = display['bounds']
            if (bounds['x'] <= window_center_x <= bounds['x'] + bounds['width'] and
                bounds['y'] <= window_center_y <= bounds['y'] + bounds['height']):
                return display['index']
        
        return 1  # Default to main display

    def _generate_window_id(self, window_number: int, pid: int, title: str) -> str:
        """Generate a unique window identifier"""
        title_hash = hashlib.md5(title.encode('utf-8', errors='ignore')).hexdigest()[:8]
        return f"{window_number}_{pid}_{title_hash}" 

    # =============== WINDOW DETECTION METHODS ===============
    
    def get_structured_windows(self) -> Dict:
        """Get all windows organized by display and application"""
        result = {
            "timestamp": time.time(),
            "displays": {},
            "summary": {
                "total_displays": len(self.displays),
                "total_windows": 0,
                "total_apps": 0
            }
        }
        
        # Initialize display structure
        for display in self.displays:
            display_id = display['index']
            result["displays"][f"display_{display_id}"] = {
                "id": display_id,
                "bounds": display['bounds'],
                "size": display['size'],
                "origin": display['origin'],
                "is_main": display['is_main'],
                "applications": {},
                "window_count": 0
            }
        
        try:
            # Get all on-screen windows
            window_list = Quartz.CGWindowListCopyWindowInfo(
                kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements,
                kCGNullWindowID
            )
            
            if not window_list:
                return result
                
            # Process each window
            for window_info in window_list:
                try:
                    # Extract window information
                    window_number = window_info.get('kCGWindowNumber', 0)
                    window_layer = window_info.get('kCGWindowLayer', 0)
                    owner_pid = window_info.get('kCGWindowOwnerPID', 0)
                    owner_name = window_info.get('kCGWindowOwnerName', 'Unknown')
                    window_name = window_info.get('kCGWindowName', '')
                    
                    # Skip windows without proper info or system windows
                    if not owner_name or window_layer < 0 or not window_number:
                        continue
                        
                    # Get window bounds
                    bounds_info = window_info.get('kCGWindowBounds', {})
                    window_bounds = {
                        'x': int(bounds_info.get('X', 0)),
                        'y': int(bounds_info.get('Y', 0)),
                        'width': int(bounds_info.get('Width', 0)),
                        'height': int(bounds_info.get('Height', 0))
                    }
                    
                    # Skip windows with no size
                    if window_bounds['width'] <= 0 or window_bounds['height'] <= 0:
                        continue
                    
                    # Determine which display this window is on
                    display_index = self._get_window_display(window_bounds)
                    display_key = f"display_{display_index}"
                    
                    if display_key not in result["displays"]:
                        continue  # Skip if display not found
                    
                    # Get additional window state using Accessibility API
                    window_state = self._get_window_state_ax(window_number, owner_pid)
                    
                    # Generate window ID
                    window_id = self._generate_window_id(window_number, owner_pid, window_name)
                    
                    # Initialize app entry if not exists
                    if owner_name not in result["displays"][display_key]["applications"]:
                        result["displays"][display_key]["applications"][owner_name] = {
                            "process_name": owner_name,
                            "pid": owner_pid,
                            "windows": {},
                            "window_count": 0,
                            "minimized_count": 0,
                            "visible_count": 0
                        }
                    
                    app_data = result["displays"][display_key]["applications"][owner_name]
                    
                    # Create window data structure
                    window_data = {
                        "window_id": window_id,
                        "window_number": window_number,
                        "pid": owner_pid,
                        "title": window_name,
                        "app_name": owner_name,
                        "position": {
                            "x": window_bounds['x'],
                            "y": window_bounds['y']
                        },
                        "size": {
                            "width": window_bounds['width'],
                            "height": window_bounds['height']
                        },
                        "bounds": window_bounds,
                        "minimized": window_state.get('minimized', False),
                        "visible": not window_state.get('minimized', False),
                        "display": display_index,
                        "layer": window_layer,
                        "is_main": window_state.get('is_main', False)
                    }
                    
                    # Add to app data
                    app_data["windows"][window_id] = window_data
                    app_data["window_count"] += 1
                    
                    if window_data["minimized"]:
                        app_data["minimized_count"] += 1
                    else:
                        app_data["visible_count"] += 1
                    
                    result["displays"][display_key]["window_count"] += 1
                    result["summary"]["total_windows"] += 1
                    
                except Exception as e:
                    # Skip problematic windows
                    continue
            
            # Count unique applications
            all_apps = set()
            for display_data in result["displays"].values():
                all_apps.update(display_data["applications"].keys())
            result["summary"]["total_apps"] = len(all_apps)
            
        except Exception as e:
            print(f"Error getting windows: {e}")
            
        return result

    def _get_window_state_ax(self, window_number: int, pid: int) -> Dict:
        """Get window state using Accessibility API"""
        state = {'minimized': False, 'is_main': False, 'focused': False}
        
        if not ACCESSIBILITY_AVAILABLE:
            return state
            
        try:
            # Create accessibility element for the application
            app_element = AXUIElementCreateApplication(pid)
            if not app_element:
                return state
                
            # Get all windows for this app
            windows_ref = AXUIElementCopyAttributeValue(app_element, kAXWindowsAttribute, None)
            if not windows_ref[0] or not windows_ref[1]:
                return state
                
            windows = windows_ref[1]
            for i in range(CFArrayGetCount(windows)):
                window_element = CFArrayGetValueAtIndex(windows, i)
                
                # Check if minimized
                minimized_ref = AXUIElementCopyAttributeValue(window_element, kAXMinimizedAttribute, None)
                if minimized_ref[0] == 0 and minimized_ref[1]:
                    state['minimized'] = bool(minimized_ref[1])
                
                # Check if main window
                main_ref = AXUIElementCopyAttributeValue(window_element, kAXMainAttribute, None)
                if main_ref[0] == 0 and main_ref[1]:
                    state['is_main'] = bool(main_ref[1])
                    break  # Found the main window
                    
        except Exception:
            pass  # Ignore accessibility errors
            
        return state

    # =============== WINDOW CONTROL METHODS ===============
    
    def is_window_valid(self, window_number: int) -> bool:
        """Check if window is still valid"""
        try:
            window_list = Quartz.CGWindowListCopyWindowInfo(
                kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements,
                kCGNullWindowID
            )
            
            if not window_list:
                return False
                
            for window_info in window_list:
                if window_info.get('kCGWindowNumber') == window_number:
                    return True
                    
            return False
        except Exception:
            return False

    def get_window_state(self, window_number: int) -> str:
        """Get current window state"""
        try:
            # Find the window in current window list
            window_list = Quartz.CGWindowListCopyWindowInfo(
                kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements,
                kCGNullWindowID
            )
            
            if not window_list:
                return "invalid"
                
            window_info = None
            for info in window_list:
                if info.get('kCGWindowNumber') == window_number:
                    window_info = info
                    break
                    
            if not window_info:
                return "invalid"
                
            # Get PID and use Accessibility API for detailed state
            pid = window_info.get('kCGWindowOwnerPID', 0)
            if pid and ACCESSIBILITY_AVAILABLE:
                state = self._get_window_state_ax(window_number, pid)
                if state['minimized']:
                    return "minimized"
                    
            # Check if window covers most of the screen (likely maximized)
            bounds = window_info.get('kCGWindowBounds', {})
            width = bounds.get('Width', 0)
            height = bounds.get('Height', 0)
            
            # Get the display this window is on
            display_index = self._get_window_display({
                'x': int(bounds.get('X', 0)),
                'y': int(bounds.get('Y', 0)),
                'width': int(width),
                'height': int(height)
            })
            
            if display_index <= len(self.displays):
                display = self.displays[display_index - 1]
                display_width = display['size']['width']
                display_height = display['size']['height']
                
                # Consider maximized if window covers most of the screen
                if (abs(width - display_width) <= 50 and abs(height - display_height) <= 100):
                    return "maximized"
                    
            return "normal"
            
        except Exception:
            return "error"

    def maximize_window(self, window_number: int) -> Tuple[bool, str]:
        """Maximize a window (macOS doesn't have true maximize, so we'll resize to screen)"""
        try:
            time.sleep(0.1)
            
            if not self.is_window_valid(window_number):
                return False, "Window is no longer valid"
            
            current_state = self.get_window_state(window_number)
            if current_state == "maximized":
                return True, "Window is already maximized"
            
            # Get window info
            window_info = self._get_window_info(window_number)
            if not window_info:
                return False, "Could not get window information"
            
            pid = window_info.get('kCGWindowOwnerPID', 0)
            if not pid or not ACCESSIBILITY_AVAILABLE:
                return False, "Accessibility API not available or no PID"
            
            # Get the display this window is on
            bounds = window_info.get('kCGWindowBounds', {})
            display_index = self._get_window_display({
                'x': int(bounds.get('X', 0)),
                'y': int(bounds.get('Y', 0)),
                'width': int(bounds.get('Width', 0)),
                'height': int(bounds.get('Height', 0))
            })
            
            if display_index > len(self.displays):
                return False, "Could not determine display"
            
            display = self.displays[display_index - 1]
            
            # Use Accessibility API to resize window
            app_element = AXUIElementCreateApplication(pid)
            if not app_element:
                return False, "Could not access application"
            
            # Find the window element
            window_element = self._find_window_element(app_element, window_number)
            if not window_element:
                return False, "Could not find window element"
            
            # Set window size to display size (minus some margin for dock/menu bar)
            new_size = Foundation.NSSize()
            new_size.width = display['size']['width']
            new_size.height = display['size']['height'] - 50  # Account for menu bar
            
            new_position = Foundation.NSPoint()
            new_position.x = display['origin']['x']
            new_position.y = display['origin']['y'] + 25  # Account for menu bar
            
            # Set position and size
            pos_result = AXUIElementSetAttributeValue(window_element, kAXPositionAttribute, 
                                                     Foundation.NSValue.valueWithPoint_(new_position))
            size_result = AXUIElementSetAttributeValue(window_element, kAXSizeAttribute,
                                                      Foundation.NSValue.valueWithSize_(new_size))
            
            if pos_result == 0 and size_result == 0:
                return True, "Window maximized"
            else:
                return False, "Failed to resize window"
                
        except Exception as e:
            return False, f"Failed to maximize: {e}"

    def minimize_window(self, window_number: int) -> Tuple[bool, str]:
        """Minimize a window"""
        try:
            time.sleep(0.1)
            
            if not self.is_window_valid(window_number):
                return False, "Window is no longer valid"
            
            current_state = self.get_window_state(window_number)
            if current_state == "minimized":
                return True, "Window is already minimized"
            
            # Get window info
            window_info = self._get_window_info(window_number)
            if not window_info:
                return False, "Could not get window information"
            
            pid = window_info.get('kCGWindowOwnerPID', 0)
            if not pid or not ACCESSIBILITY_AVAILABLE:
                return False, "Accessibility API not available or no PID"
            
            # Use Accessibility API
            app_element = AXUIElementCreateApplication(pid)
            if not app_element:
                return False, "Could not access application"
            
            window_element = self._find_window_element(app_element, window_number)
            if not window_element:
                return False, "Could not find window element"
            
            # Set minimized attribute
            result = AXUIElementSetAttributeValue(window_element, kAXMinimizedAttribute, 
                                                Foundation.NSNumber.numberWithBool_(True))
            
            if result == 0:
                return True, "Window minimized"
            else:
                return False, "Failed to minimize window"
                
        except Exception as e:
            return False, f"Failed to minimize: {e}"

    def close_window(self, window_number: int) -> Tuple[bool, str]:
        """Close a window"""
        try:
            time.sleep(0.1)
            
            if not self.is_window_valid(window_number):
                return False, "Window is no longer valid"
            
            # Get window info
            window_info = self._get_window_info(window_number)
            if not window_info:
                return False, "Could not get window information"
            
            pid = window_info.get('kCGWindowOwnerPID', 0)
            if not pid or not ACCESSIBILITY_AVAILABLE:
                # Fallback: try to close via application
                app_name = window_info.get('kCGWindowOwnerName', '')
                if app_name:
                    try:
                        # Use AppleScript as fallback
                        script = f'''
                        tell application "{app_name}"
                            close window 1
                        end tell
                        '''
                        subprocess.run(['osascript', '-e', script], check=True, capture_output=True)
                        return True, "Window close signal sent (AppleScript)"
                    except:
                        return False, "Could not close window"
                else:
                    return False, "Accessibility API not available and no app name"
            
            # Use Accessibility API
            app_element = AXUIElementCreateApplication(pid)
            if not app_element:
                return False, "Could not access application"
            
            window_element = self._find_window_element(app_element, window_number)
            if not window_element:
                return False, "Could not find window element"
            
            # Try to find and click the close button
            close_button = self._find_close_button(window_element)
            if close_button:
                result = AXUIElementPerformAction(close_button, kAXPressAction)
                if result == 0:
                    return True, "Window closed"
            
            return False, "Could not find close button"
                
        except Exception as e:
            return False, f"Failed to close: {e}"

    def bring_to_foreground(self, window_number: int) -> Tuple[bool, str]:
        """Bring window to foreground"""
        try:
            time.sleep(0.1)
            
            if not self.is_window_valid(window_number):
                return False, "Window is no longer valid"
            
            # Get window info
            window_info = self._get_window_info(window_number)
            if not window_info:
                return False, "Could not get window information"
            
            pid = window_info.get('kCGWindowOwnerPID', 0)
            app_name = window_info.get('kCGWindowOwnerName', '')
            
            if not pid:
                return False, "No PID found"
            
            # First, activate the application
            running_apps = NSWorkspace.sharedWorkspace().runningApplications()
            target_app = None
            
            for app in running_apps:
                if app.processIdentifier() == pid:
                    target_app = app
                    break
            
            if target_app:
                target_app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
                time.sleep(0.2)
            
            # Then try to bring specific window to front using Accessibility API
            if ACCESSIBILITY_AVAILABLE:
                app_element = AXUIElementCreateApplication(pid)
                if app_element:
                    window_element = self._find_window_element(app_element, window_number)
                    if window_element:
                        # Raise the window
                        AXUIElementPerformAction(window_element, kAXRaiseAction)
                        # Set as main window
                        AXUIElementSetAttributeValue(window_element, kAXMainAttribute,
                                                   Foundation.NSNumber.numberWithBool_(True))
            
            return True, f"Window brought to foreground"
                
        except Exception as e:
            return False, f"Failed to bring to foreground: {e}"

    def resize_window(self, window_number: int, width: int, height: int) -> Tuple[bool, str]:
        """Resize window to specific dimensions"""
        try:
            time.sleep(0.1)
            
            if not self.is_window_valid(window_number):
                return False, "Window is no longer valid"
            
            # Get window info
            window_info = self._get_window_info(window_number)
            if not window_info:
                return False, "Could not get window information"
            
            pid = window_info.get('kCGWindowOwnerPID', 0)
            if not pid or not ACCESSIBILITY_AVAILABLE:
                return False, "Accessibility API not available or no PID"
            
            # Use Accessibility API
            app_element = AXUIElementCreateApplication(pid)
            if not app_element:
                return False, "Could not access application"
            
            window_element = self._find_window_element(app_element, window_number)
            if not window_element:
                return False, "Could not find window element"
            
            # Set new size
            new_size = Foundation.NSSize()
            new_size.width = width
            new_size.height = height
            
            result = AXUIElementSetAttributeValue(window_element, kAXSizeAttribute,
                                                Foundation.NSValue.valueWithSize_(new_size))
            
            if result == 0:
                # Verify the resize
                time.sleep(0.1)
                size_ref = AXUIElementCopyAttributeValue(window_element, kAXSizeAttribute, None)
                if size_ref[0] == 0 and size_ref[1]:
                    actual_size = Foundation.NSValue(size_ref[1]).sizeValue()
                    return True, f"Window resized to {int(actual_size.width)}x{int(actual_size.height)}"
                else:
                    return True, f"Window resize attempted (target: {width}x{height})"
            else:
                return False, "Failed to resize window"
                
        except Exception as e:
            return False, f"Failed to resize: {e}"

    def move_window(self, window_number: int, x: int, y: int) -> Tuple[bool, str]:
        """Move window to specific coordinates"""
        try:
            time.sleep(0.1)
            
            if not self.is_window_valid(window_number):
                return False, "Window is no longer valid"
            
            # Get window info
            window_info = self._get_window_info(window_number)
            if not window_info:
                return False, "Could not get window information"
            
            pid = window_info.get('kCGWindowOwnerPID', 0)
            if not pid or not ACCESSIBILITY_AVAILABLE:
                return False, "Accessibility API not available or no PID"
            
            # Use Accessibility API
            app_element = AXUIElementCreateApplication(pid)
            if not app_element:
                return False, "Could not access application"
            
            window_element = self._find_window_element(app_element, window_number)
            if not window_element:
                return False, "Could not find window element"
            
            # Set new position
            new_position = Foundation.NSPoint()
            new_position.x = x
            new_position.y = y
            
            result = AXUIElementSetAttributeValue(window_element, kAXPositionAttribute,
                                                Foundation.NSValue.valueWithPoint_(new_position))
            
            if result == 0:
                # Verify the move
                time.sleep(0.1)
                pos_ref = AXUIElementCopyAttributeValue(window_element, kAXPositionAttribute, None)
                if pos_ref[0] == 0 and pos_ref[1]:
                    actual_pos = Foundation.NSValue(pos_ref[1]).pointValue()
                    return True, f"Window moved to ({int(actual_pos.x)}, {int(actual_pos.y)})"
                else:
                    return True, f"Window move attempted (target: ({x}, {y}))"
            else:
                return False, "Failed to move window"
                
        except Exception as e:
            return False, f"Failed to move: {e}"

    def move_window_to_display(self, window_number: int, target_display: int) -> Tuple[bool, str]:
        """Move window to specific display (centered)"""
        try:
            if not self.is_window_valid(window_number):
                return False, "Window is no longer valid"
            
            if target_display < 1 or target_display > len(self.displays):
                return False, f"Invalid display ID. Available displays: 1-{len(self.displays)}"
            
            target_display_data = self.displays[target_display - 1]
            
            # Get current window size
            window_info = self._get_window_info(window_number)
            if not window_info:
                return False, "Could not get window information"
            
            bounds = window_info.get('kCGWindowBounds', {})
            window_width = int(bounds.get('Width', 400))
            window_height = int(bounds.get('Height', 300))
            
            # Calculate position to center window on target display
            target_x = target_display_data['origin']['x'] + (target_display_data['size']['width'] - window_width) // 2
            target_y = target_display_data['origin']['y'] + (target_display_data['size']['height'] - window_height) // 2
            
            # Ensure window doesn't go off-screen
            max_x = target_display_data['origin']['x'] + target_display_data['size']['width'] - window_width
            max_y = target_display_data['origin']['y'] + target_display_data['size']['height'] - window_height
            target_x = max(target_display_data['origin']['x'], min(target_x, max_x))
            target_y = max(target_display_data['origin']['y'], min(target_y, max_y))
            
            success, message = self.move_window(window_number, target_x, target_y)
            if success:
                return True, f"Window moved to display {target_display} at ({target_x}, {target_y})"
            else:
                return False, message
                
        except Exception as e:
            return False, f"Failed to move to display: {e}"

    # =============== MOUSE AND CURSOR CONTROL ===============
    
    def get_cursor_position(self) -> Tuple[bool, str, Optional[Tuple[int, int]]]:
        """Get current cursor position"""
        try:
            # Get cursor position using Core Graphics (most accurate)
            mouse_pos = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
            
            # Core Graphics uses bottom-left origin, convert to top-left origin (screen coordinates)
            main_screen = NSScreen.mainScreen()
            screen_height = main_screen.frame().size.height
            x = int(mouse_pos.x)
            y = int(screen_height - mouse_pos.y)
            
            display_id = self._get_cursor_display((x, y))
            return True, f"Cursor at ({x}, {y}) on Display {display_id}", (x, y)
        except Exception as e:
            # Fallback method using NSEvent
            try:
                cursor_pos = NSEvent.mouseLocation()
                main_screen = NSScreen.mainScreen()
                screen_height = main_screen.frame().size.height
                x = int(cursor_pos.x)
                y = int(screen_height - cursor_pos.y)
                display_id = self._get_cursor_display((x, y))
                return True, f"Cursor at ({x}, {y}) on Display {display_id}", (x, y)
            except Exception as e2:
                return False, f"Failed to get cursor position: {e}, fallback: {e2}", None

    def set_cursor_position(self, x: int, y: int) -> Tuple[bool, str]:
        """Set cursor position to absolute coordinates"""
        try:
            time.sleep(0.05)
            
            # Convert to Core Graphics coordinates (Y is inverted)
            main_screen = NSScreen.mainScreen()
            screen_height = main_screen.frame().size.height
            cg_y = screen_height - y
            
            # Use Core Graphics to move cursor
            success = Quartz.CGDisplayMoveCursorToPoint(Quartz.CGMainDisplayID(), 
                                                       Quartz.CGPoint(x, cg_y))
            
            if success == 0:  # Success in Core Graphics is 0
                display_id = self._get_cursor_display((x, y))
                return True, f"Cursor moved to ({x}, {y}) on Display {display_id}"
            else:
                return False, "Failed to move cursor"
                
        except Exception as e:
            return False, f"Failed to set cursor position: {e}"

    def _get_cursor_display(self, cursor_pos: Tuple[int, int]) -> int:
        """Determine which display the cursor is on"""
        x, y = cursor_pos
        for display in self.displays:
            bounds = display['bounds']
            if (bounds['x'] <= x <= bounds['x'] + bounds['width'] and
                bounds['y'] <= y <= bounds['y'] + bounds['height']):
                return display['index']
        return 1

    def send_mouse_click(self, button: str = "left", x: int = None, y: int = None) -> Tuple[bool, str]:
        """Send mouse click at specified position or current cursor position"""
        try:
            time.sleep(0.1)
            
            # Move cursor to position if specified
            if x is not None and y is not None:
                success, msg = self.set_cursor_position(x, y)
                if not success:
                    return False, f"Failed to move cursor: {msg}"
                time.sleep(0.1)  # Give cursor time to move
                
                # Verify cursor position after move
                _, _, actual_pos = self.get_cursor_position()
                if actual_pos:
                    actual_x, actual_y = actual_pos
                    # Allow small tolerance for cursor position
                    if abs(actual_x - x) > 5 or abs(actual_y - y) > 5:
                        print(f"Warning: Cursor moved to ({actual_x}, {actual_y}) instead of ({x}, {y})")
            else:
                # Get current cursor position
                _, _, pos = self.get_cursor_position()
                if pos:
                    x, y = pos
                else:
                    return False, "Could not get cursor position"
            
            # Convert screen coordinates to Core Graphics coordinates for click event
            main_screen = NSScreen.mainScreen()
            screen_height = main_screen.frame().size.height
            cg_point = Quartz.CGPoint(x, screen_height - y)
            
            # Map button to event types
            button_map = {
                "left": (kCGEventLeftMouseDown, kCGEventLeftMouseUp, Quartz.kCGMouseButtonLeft),
                "right": (kCGEventRightMouseDown, kCGEventRightMouseUp, Quartz.kCGMouseButtonRight),
                "middle": (kCGEventOtherMouseDown, kCGEventOtherMouseUp, Quartz.kCGMouseButtonCenter)
            }
            
            if button.lower() not in button_map:
                return False, f"Invalid button: {button}. Use left, right, or middle"
            
            down_event, up_event, mouse_button = button_map[button.lower()]
            
            # Create event source
            event_source = CGEventSourceCreate(kCGEventSourceStateHIDSystemState)
            
            # Create mouse down event
            mouse_down = CGEventCreateMouseEvent(event_source, down_event, cg_point, mouse_button)
            # Create mouse up event
            mouse_up = CGEventCreateMouseEvent(event_source, up_event, cg_point, mouse_button)
            
            # Post events
            CGEventPost(kCGHIDEventTap, mouse_down)
            time.sleep(0.02)  # Small delay between down and up
            CGEventPost(kCGHIDEventTap, mouse_up)
            
            display_id = self._get_cursor_display((x, y))
            return True, f"{button.capitalize()} click at ({x}, {y}) on Display {display_id}"
            
        except Exception as e:
            return False, f"Failed to send mouse click: {e}"

    def send_mouse_double_click(self, button: str = "left", x: int = None, y: int = None) -> Tuple[bool, str]:
        """Send mouse double click"""
        try:
            time.sleep(0.1)
            
            # Move cursor to position if specified
            if x is not None and y is not None:
                success, msg = self.set_cursor_position(x, y)
                if not success:
                    return False, f"Failed to move cursor: {msg}"
                time.sleep(0.05)
            
            # Send first click
            success1, msg1 = self.send_mouse_click(button, None, None)
            if not success1:
                return False, f"First click failed: {msg1}"
            
            # Brief delay between clicks
            time.sleep(0.05)
            
            # Send second click
            success2, msg2 = self.send_mouse_click(button, None, None)
            if not success2:
                return False, f"Second click failed: {msg2}"
            
            if x is None or y is None:
                _, _, pos = self.get_cursor_position()
                if pos:
                    x, y = pos
                else:
                    x, y = 0, 0
            
            display_id = self._get_cursor_display((x, y))
            return True, f"{button.capitalize()} double-click at ({x}, {y}) on Display {display_id}"
            
        except Exception as e:
            return False, f"Failed to send double click: {e}"

    def send_mouse_long_click(self, button: str = "left", duration: float = 1.0, 
                             x: int = None, y: int = None) -> Tuple[bool, str]:
        """Send mouse long click (press and hold)"""
        try:
            time.sleep(0.1)
            
            # Move cursor to position if specified
            if x is not None and y is not None:
                success, msg = self.set_cursor_position(x, y)
                if not success:
                    return False, f"Failed to move cursor: {msg}"
            else:
                _, _, pos = self.get_cursor_position()
                if pos:
                    x, y = pos
                else:
                    return False, "Could not get cursor position"
            
            # Convert to Core Graphics coordinates
            main_screen = NSScreen.mainScreen()
            screen_height = main_screen.frame().size.height
            cg_point = Quartz.CGPoint(x, screen_height - y)
            
            # Map button to event types
            button_map = {
                "left": (kCGEventLeftMouseDown, kCGEventLeftMouseUp, Quartz.kCGMouseButtonLeft),
                "right": (kCGEventRightMouseDown, kCGEventRightMouseUp, Quartz.kCGMouseButtonRight),
                "middle": (kCGEventOtherMouseDown, kCGEventOtherMouseUp, Quartz.kCGMouseButtonCenter)
            }
            
            if button.lower() not in button_map:
                return False, f"Invalid button: {button}. Use left, right, or middle"
            
            down_event, up_event, mouse_button = button_map[button.lower()]
            
            # Create event source
            event_source = CGEventSourceCreate(kCGEventSourceStateHIDSystemState)
            
            # Mouse down
            mouse_down = CGEventCreateMouseEvent(event_source, down_event, cg_point, mouse_button)
            CGEventPost(kCGHIDEventTap, mouse_down)
            
            # Hold for specified duration
            time.sleep(duration)
            
            # Mouse up
            mouse_up = CGEventCreateMouseEvent(event_source, up_event, cg_point, mouse_button)
            CGEventPost(kCGHIDEventTap, mouse_up)
            
            display_id = self._get_cursor_display((x, y))
            return True, f"{button.capitalize()} long-click ({duration}s) at ({x}, {y}) on Display {display_id}"
            
        except Exception as e:
            return False, f"Failed to send long click: {e}"

    def send_mouse_scroll(self, direction: str, amount: int = 3, x: int = None, y: int = None) -> Tuple[bool, str]:
        """Send mouse scroll (up, down, left, right)"""
        try:
            # Move cursor to position if specified
            if x is not None and y is not None:
                success, msg = self.set_cursor_position(x, y)
                if not success:
                    return False, f"Failed to move cursor: {msg}"
            else:
                _, _, pos = self.get_cursor_position()
                if pos:
                    x, y = pos
                else:
                    return False, "Could not get cursor position"
            
            # Convert to Core Graphics coordinates
            main_screen = NSScreen.mainScreen()
            screen_height = main_screen.frame().size.height
            cg_point = Quartz.CGPoint(x, screen_height - y)
            
            # Map direction to scroll values
            direction_map = {
                "up": (amount, 0),      # Positive Y scroll
                "down": (-amount, 0),   # Negative Y scroll
                "left": (0, -amount),   # Negative X scroll  
                "right": (0, amount)    # Positive X scroll
            }
            
            if direction.lower() not in direction_map:
                return False, f"Invalid direction: {direction}. Use up, down, left, or right"
            
            scroll_y, scroll_x = direction_map[direction.lower()]
            
            # Create event source
            event_source = CGEventSourceCreate(kCGEventSourceStateHIDSystemState)
            
            # Create scroll event using the correct function name
            try:
                scroll_event = Quartz.CGEventCreateScrollWheelEvent(
                    event_source, 
                    Quartz.kCGScrollEventUnitPixel,
                    2,  # Number of scroll axes
                    scroll_y, scroll_x
                )
            except AttributeError:
                # Fallback if the function name is different
                try:
                    scroll_event = Quartz.CGEventCreateScrollWheelEvent2(
                        event_source,
                        Quartz.kCGScrollEventUnitPixel,
                        2,
                        scroll_y, scroll_x
                    )
                except AttributeError:
                    # Use alternative method
                    scroll_event = CGEventCreateMouseEvent(
                        event_source, 
                        kCGEventScrollWheel, 
                        cg_point, 
                        0
                    )
                    # Set scroll wheel delta manually
                    Quartz.CGEventSetIntegerValueField(scroll_event, Quartz.kCGScrollWheelEventDeltaAxis1, scroll_y)
                    Quartz.CGEventSetIntegerValueField(scroll_event, Quartz.kCGScrollWheelEventDeltaAxis2, scroll_x)
            
            # Set the event location
            if scroll_event:
                try:
                    Quartz.CGEventSetLocation(scroll_event, cg_point)
                except:
                    pass  # Some versions may not support this
                
                # Post the event
                CGEventPost(kCGHIDEventTap, scroll_event)
                
                display_id = self._get_cursor_display((x, y))
                return True, f"Scroll {direction} (amount: {amount}) at ({x}, {y}) on Display {display_id}"
            else:
                return False, "Failed to create scroll event"
            
        except Exception as e:
            return False, f"Failed to send scroll: {e}"

    def send_mouse_drag(self, start_x: int, start_y: int, end_x: int, end_y: int,
                       button: str = "left", duration: float = 0.5) -> Tuple[bool, str]:
        """Send mouse drag from start to end position"""
        try:
            # Map button to event types
            button_map = {
                "left": (kCGEventLeftMouseDown, kCGEventLeftMouseUp, Quartz.kCGMouseButtonLeft),
                "right": (kCGEventRightMouseDown, kCGEventRightMouseUp, Quartz.kCGMouseButtonRight),
                "middle": (kCGEventOtherMouseDown, kCGEventOtherMouseUp, Quartz.kCGMouseButtonCenter)
            }
            
            if button.lower() not in button_map:
                return False, f"Invalid button: {button}. Use left, right, or middle"
            
            down_event, up_event, mouse_button = button_map[button.lower()]
            
            # Move to start position
            self.set_cursor_position(start_x, start_y)
            time.sleep(0.1)
            
            # Convert coordinates to Core Graphics
            main_screen = NSScreen.mainScreen()
            screen_height = main_screen.frame().size.height
            
            start_cg = Quartz.CGPoint(start_x, screen_height - start_y)
            end_cg = Quartz.CGPoint(end_x, screen_height - end_y)
            
            # Create event source
            event_source = CGEventSourceCreate(kCGEventSourceStateHIDSystemState)
            
            # Mouse down at start
            mouse_down = CGEventCreateMouseEvent(event_source, down_event, start_cg, mouse_button)
            CGEventPost(kCGHIDEventTap, mouse_down)
            
            # Calculate intermediate positions for smooth drag
            steps = max(10, int(duration * 20))  # 20 steps per second
            for i in range(1, steps + 1):
                progress = i / steps
                current_x = int(start_x + (end_x - start_x) * progress)
                current_y = int(start_y + (end_y - start_y) * progress)
                
                # Convert to CG coordinates
                current_cg = Quartz.CGPoint(current_x, screen_height - current_y)
                
                # Create drag event
                drag_event = CGEventCreateMouseEvent(event_source, kCGEventLeftMouseDragged, 
                                                   current_cg, mouse_button)
                CGEventPost(kCGHIDEventTap, drag_event)
                
                time.sleep(duration / steps)
            
            # Mouse up at end
            mouse_up = CGEventCreateMouseEvent(event_source, up_event, end_cg, mouse_button)
            CGEventPost(kCGHIDEventTap, mouse_up)
            
            start_display = self._get_cursor_display((start_x, start_y))
            end_display = self._get_cursor_display((end_x, end_y))
            
            return True, f"{button.capitalize()} drag from ({start_x}, {start_y}) to ({end_x}, {end_y}) in {duration}s (Display {start_display}→{end_display})"
            
        except Exception as e:
            return False, f"Failed to send drag: {e}"

    # =============== KEYBOARD CONTROL ===============
    
    def get_virtual_key_codes(self) -> Tuple[bool, str]:
        """Get all available virtual key codes for macOS"""
        try:
            key_categories = {
                "Modifier Keys": {
                    'CMD': 0x37, 'COMMAND': 0x37, 'LCMD': 0x37, 'RCMD': 0x36,
                    'SHIFT': 0x38, 'LSHIFT': 0x38, 'RSHIFT': 0x3C,
                    'ALT': 0x3A, 'OPTION': 0x3A, 'LALT': 0x3A, 'RALT': 0x3D,
                    'CTRL': 0x3B, 'CONTROL': 0x3B, 'LCTRL': 0x3B, 'RCTRL': 0x3E,
                    'FN': 0x3F,
                },
                "Basic Keys": {
                    'ESC': 0x35, 'ESCAPE': 0x35,
                    'TAB': 0x30, 'ENTER': 0x24, 'RETURN': 0x24, 'SPACE': 0x31,
                    'BACKSPACE': 0x33, 'DELETE': 0x75, 'FORWARD_DELETE': 0x75,
                },
                "Navigation": {
                    'HOME': 0x73, 'END': 0x77, 'PAGEUP': 0x74, 'PAGEDOWN': 0x79,
                    'UP': 0x7E, 'DOWN': 0x7D, 'LEFT': 0x7B, 'RIGHT': 0x7C,
                },
                "Function Keys": {
                    'F1': 0x7A, 'F2': 0x78, 'F3': 0x63, 'F4': 0x76, 'F5': 0x60, 'F6': 0x61,
                    'F7': 0x62, 'F8': 0x64, 'F9': 0x65, 'F10': 0x6D, 'F11': 0x67, 'F12': 0x6F,
                    'F13': 0x69, 'F14': 0x6B, 'F15': 0x71, 'F16': 0x6A, 'F17': 0x40, 'F18': 0x4F,
                    'F19': 0x50, 'F20': 0x5A,
                },
                "Number Row": {
                    '1': 0x12, '2': 0x13, '3': 0x14, '4': 0x15, '5': 0x17,
                    '6': 0x16, '7': 0x1A, '8': 0x1C, '9': 0x19, '0': 0x1D,
                    'MINUS': 0x1B, 'EQUALS': 0x18,
                },
                "Letters": {
                    'A': 0x00, 'B': 0x0B, 'C': 0x08, 'D': 0x02, 'E': 0x0E, 'F': 0x03,
                    'G': 0x05, 'H': 0x04, 'I': 0x22, 'J': 0x26, 'K': 0x28, 'L': 0x25,
                    'M': 0x2E, 'N': 0x2D, 'O': 0x1F, 'P': 0x23, 'Q': 0x0C, 'R': 0x0F,
                    'S': 0x01, 'T': 0x11, 'U': 0x20, 'V': 0x09, 'W': 0x0D, 'X': 0x07,
                    'Y': 0x10, 'Z': 0x06,
                },
                "Special Characters": {
                    'SEMICOLON': 0x29, 'QUOTE': 0x27, 'COMMA': 0x2B, 'PERIOD': 0x2F,
                    'SLASH': 0x2C, 'BACKSLASH': 0x2A, 'GRAVE': 0x32, 'LBRACKET': 0x21,
                    'RBRACKET': 0x1E,
                },
                "Keypad": {
                    'KP_0': 0x52, 'KP_1': 0x53, 'KP_2': 0x54, 'KP_3': 0x55, 'KP_4': 0x56,
                    'KP_5': 0x57, 'KP_6': 0x58, 'KP_7': 0x59, 'KP_8': 0x5B, 'KP_9': 0x5C,
                    'KP_DECIMAL': 0x41, 'KP_ENTER': 0x4C, 'KP_PLUS': 0x45, 'KP_MINUS': 0x4E,
                    'KP_MULTIPLY': 0x43, 'KP_DIVIDE': 0x4B, 'KP_EQUALS': 0x51, 'KP_CLEAR': 0x47,
                },
                "Media/Volume": {
                    'VOLUME_UP': 0x48, 'VOLUME_DOWN': 0x49, 'MUTE': 0x4A,
                    'BRIGHTNESS_UP': 0x90, 'BRIGHTNESS_DOWN': 0x91,
                },
            }
            
            result = []
            for category, keys in key_categories.items():
                result.append(f"\n📁 {category}:")
                for key, code in sorted(keys.items()):
                    result.append(f"   {key:<20} = {hex(code)}")
            
            return True, "\n".join(result)
            
        except Exception as e:
            return False, f"Failed to get virtual key codes: {e}"

    def send_key_combination(self, keys: str) -> Tuple[bool, str]:
        """Send virtual keyboard combination (e.g., 'cmd+c', 'option+tab')"""
        try:
            time.sleep(0.1)
            
            # Parse key combination
            key_parts = [k.strip().upper() for k in keys.split('+')]
            
            # Map key names to virtual key codes (macOS specific)
            key_map = {
                # Modifier keys
                'CMD': 0x37, 'COMMAND': 0x37, 'LCMD': 0x37, 'RCMD': 0x36,
                'SHIFT': 0x38, 'LSHIFT': 0x38, 'RSHIFT': 0x3C,
                'ALT': 0x3A, 'OPTION': 0x3A, 'LALT': 0x3A, 'RALT': 0x3D,
                'CTRL': 0x3B, 'CONTROL': 0x3B, 'LCTRL': 0x3B, 'RCTRL': 0x3E,
                'FN': 0x3F,
                
                # Basic keys
                'ESC': 0x35, 'ESCAPE': 0x35, 'TAB': 0x30, 'ENTER': 0x24, 'RETURN': 0x24,
                'SPACE': 0x31, 'BACKSPACE': 0x33, 'DELETE': 0x75,
                
                # Navigation
                'HOME': 0x73, 'END': 0x77, 'PAGEUP': 0x74, 'PAGEDOWN': 0x79,
                'UP': 0x7E, 'DOWN': 0x7D, 'LEFT': 0x7B, 'RIGHT': 0x7C,
                
                # Function keys
                'F1': 0x7A, 'F2': 0x78, 'F3': 0x63, 'F4': 0x76, 'F5': 0x60, 'F6': 0x61,
                'F7': 0x62, 'F8': 0x64, 'F9': 0x65, 'F10': 0x6D, 'F11': 0x67, 'F12': 0x6F,
                
                # Letters
                'A': 0x00, 'B': 0x0B, 'C': 0x08, 'D': 0x02, 'E': 0x0E, 'F': 0x03,
                'G': 0x05, 'H': 0x04, 'I': 0x22, 'J': 0x26, 'K': 0x28, 'L': 0x25,
                'M': 0x2E, 'N': 0x2D, 'O': 0x1F, 'P': 0x23, 'Q': 0x0C, 'R': 0x0F,
                'S': 0x01, 'T': 0x11, 'U': 0x20, 'V': 0x09, 'W': 0x0D, 'X': 0x07,
                'Y': 0x10, 'Z': 0x06,
                
                # Numbers
                '1': 0x12, '2': 0x13, '3': 0x14, '4': 0x15, '5': 0x17,
                '6': 0x16, '7': 0x1A, '8': 0x1C, '9': 0x19, '0': 0x1D,
                
                # Special characters
                'MINUS': 0x1B, 'EQUALS': 0x18, 'SEMICOLON': 0x29, 'QUOTE': 0x27,
                'COMMA': 0x2B, 'PERIOD': 0x2F, 'SLASH': 0x2C, 'BACKSLASH': 0x2A,
                'GRAVE': 0x32, 'LBRACKET': 0x21, 'RBRACKET': 0x1E,
            }
            
            # Convert key names to codes
            key_codes = []
            modifier_flags = 0
            
            # Map modifiers to flags
            modifier_flag_map = {
                0x37: Quartz.kCGEventFlagMaskCommand,    # CMD
                0x36: Quartz.kCGEventFlagMaskCommand,    # RCMD
                0x38: Quartz.kCGEventFlagMaskShift,      # SHIFT
                0x3C: Quartz.kCGEventFlagMaskShift,      # RSHIFT
                0x3A: Quartz.kCGEventFlagMaskAlternate,  # ALT/OPTION
                0x3D: Quartz.kCGEventFlagMaskAlternate,  # RALT
                0x3B: Quartz.kCGEventFlagMaskControl,    # CTRL
                0x3E: Quartz.kCGEventFlagMaskControl,    # RCTRL
            }
            
            for key in key_parts:
                if key in key_map:
                    key_code = key_map[key]
                    key_codes.append(key_code)
                    
                    # Set modifier flags
                    if key_code in modifier_flag_map:
                        modifier_flags |= modifier_flag_map[key_code]
                else:
                    return False, f"Unknown key: {key}. Use 'keys' command to see all available keys."
            
            if not key_codes:
                return False, "No valid keys specified"
            
            # Create event source
            event_source = CGEventSourceCreate(kCGEventSourceStateHIDSystemState)
            
            # Find the main key (non-modifier)
            main_key = None
            for key_code in key_codes:
                if key_code not in modifier_flag_map:
                    main_key = key_code
                    break
            
            if main_key is None:
                # If only modifiers, use the first one as main key
                main_key = key_codes[0] if key_codes else 0x31  # Default to space
            
            # Create key down event with modifiers
            key_down = CGEventCreateKeyboardEvent(event_source, main_key, True)
            CGEventSetFlags(key_down, modifier_flags)
            
            # Create key up event
            key_up = CGEventCreateKeyboardEvent(event_source, main_key, False)
            
            # Post events
            CGEventPost(kCGHIDEventTap, key_down)
            time.sleep(0.05)  # Hold key briefly
            CGEventPost(kCGHIDEventTap, key_up)
            
            return True, f"Sent key combination: {keys}"
                
        except Exception as e:
            return False, f"Failed to send key combination: {e}"

    def send_text(self, text: str) -> Tuple[bool, str]:
        """Send text as if typed on keyboard"""
        try:
            # Try method 1: CGEventKeyboardSetUnicodeString if available
            if CGEventKeyboardSetUnicodeString is not None:
                try:
                    # Create event source
                    event_source = CGEventSourceCreate(kCGEventSourceStateHIDSystemState)
                    
                    for char in text:
                        # Convert character to Unicode
                        unicode_val = ord(char)
                        
                        # Create keyboard event for this character
                        key_down = CGEventCreateKeyboardEvent(event_source, 0, True)
                        key_up = CGEventCreateKeyboardEvent(event_source, 0, False)
                        
                        # Set the unicode string for the event
                        CGEventKeyboardSetUnicodeString(key_down, 1, ctypes.byref(ctypes.c_uint16(unicode_val)))
                        CGEventKeyboardSetUnicodeString(key_up, 1, ctypes.byref(ctypes.c_uint16(unicode_val)))
                        
                        # Post events
                        CGEventPost(kCGHIDEventTap, key_down)
                        time.sleep(0.01)  # Small delay between characters
                        CGEventPost(kCGHIDEventTap, key_up)
                        time.sleep(0.01)
                    
                    return True, f"Sent text: '{text}' ({len(text)} characters)"
                except Exception:
                    pass  # Fall through to AppleScript method
            
            # Fallback: use AppleScript for text input
            try:
                # Escape quotes in the text for AppleScript
                escaped_text = text.replace('"', '\\"').replace('\\', '\\\\')
                script = f'tell application "System Events" to keystroke "{escaped_text}"'
                subprocess.run(['osascript', '-e', script], check=True, capture_output=True)
                return True, f"Sent text via AppleScript: '{text}' ({len(text)} characters)"
            except Exception as e2:
                return False, f"Failed to send text via AppleScript: {e2}"
                
        except Exception as e:
            return False, f"Failed to send text: {e}"

    # =============== SYSTEM INFORMATION ===============
    
    def get_computer_name(self) -> Tuple[bool, str]:
        """Get computer name"""
        try:
            computer_name = NSHost.currentHost().localizedName()
            return True, f"Computer name: {computer_name}"
        except Exception as e:
            return False, f"Failed to get computer name: {e}"

    def get_user_name(self) -> Tuple[bool, str]:
        """Get current user name"""
        try:
            user_name = getpass.getuser()
            full_name = NSProcessInfo.processInfo().userName()
            return True, f"User: {full_name} ({user_name})"
        except Exception as e:
            return False, f"Failed to get user name: {e}"

    def show_message_box(self, title: str, message: str, x: int = None, y: int = None,
                        width: int = 300, height: int = 150) -> Tuple[bool, str]:
        """Display a message box at specified location"""
        try:
            # Create alert
            alert = NSAlert.alloc().init()
            alert.setMessageText_(title)
            alert.setInformativeText_(message)
            alert.setAlertStyle_(NSInformationalAlertStyle)
            alert.addButtonWithTitle_("OK")
            
            # Show alert (this is modal)
            response = alert.runModal()
            
            if response == NSModalResponseOK:
                return True, f"Message box '{title}' shown and acknowledged"
            else:
                return True, f"Message box '{title}' shown"
                
        except Exception as e:
            return False, f"Failed to show message box: {e}"

    # =============== ADDITIONAL UTILITY METHODS ===============
    
    def find_window_by_app(self, app_name: str) -> List[Dict]:
        """Find windows by application name - returns list format for backwards compatibility"""
        structured = self.get_structured_windows()
        matching_windows = []
        
        app_name_lower = app_name.lower()
        
        for display_data in structured["displays"].values():
            for proc_name, app_data in display_data["applications"].items():
                if app_name_lower in proc_name.lower():
                    for window_data in app_data["windows"].values():
                        # Convert to old format for compatibility
                        matching_windows.append({
                            "window_number": window_data["window_number"],
                            "title": window_data["title"],
                            "pid": window_data["pid"],
                            "app_name": proc_name,
                            "bounds": window_data["bounds"],
                            "display": window_data["display"],
                            "minimized": window_data["minimized"]
                        })
        
        return matching_windows

    def print_structured_output(self, show_minimized: bool = True):
        """Print a clean, structured view of all windows"""
        data = self.get_structured_windows()
        
        print("=" * 80)
        print(f"MAC WINDOW MANAGER - {data['summary']['total_windows']} windows across {data['summary']['total_displays']} displays")
        print("=" * 80)
        
        for display_key, display_data in data["displays"].items():
            main_indicator = " (MAIN)" if display_data['is_main'] else ""
            print(f"\n🖥️  DISPLAY {display_data['id']}{main_indicator}")
            print(f"   Resolution: {display_data['size']['width']}x{display_data['size']['height']}")
            print(f"   Origin: ({display_data['origin']['x']}, {display_data['origin']['y']})")
            print(f"   Windows: {display_data['window_count']}")
            print("-" * 60)
            
            if not display_data["applications"]:
                print("   No applications on this display")
                continue
            
            for app_name, app_data in display_data["applications"].items():
                visible_windows = [w for w in app_data["windows"].values() if not w["minimized"]]
                minimized_windows = [w for w in app_data["windows"].values() if w["minimized"]]
                
                print(f"\n   📱 {app_name}")
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

    # =============== HELPER METHODS ===============
    
    def _get_window_info(self, window_number: int) -> Optional[Dict]:
        """Get window info by window number"""
        try:
            window_list = Quartz.CGWindowListCopyWindowInfo(
                kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements,
                kCGNullWindowID
            )
            
            if not window_list:
                return None
                
            for window_info in window_list:
                if window_info.get('kCGWindowNumber') == window_number:
                    return window_info
                    
            return None
        except Exception:
            return None

    def _find_window_element(self, app_element, window_number: int):
        """Find accessibility element for specific window"""
        try:
            windows_ref = AXUIElementCopyAttributeValue(app_element, kAXWindowsAttribute, None)
            if not windows_ref[0] or not windows_ref[1]:
                return None
                
            windows = windows_ref[1]
            # For now, return the first window (main window)
            # In a full implementation, we'd match by window properties
            if CFArrayGetCount(windows) > 0:
                return CFArrayGetValueAtIndex(windows, 0)
                
            return None
        except Exception:
            return None

    def _find_close_button(self, window_element):
        """Find the close button in a window"""
        try:
            children_ref = AXUIElementCopyAttributeValue(window_element, kAXChildrenAttribute, None)
            if not children_ref[0] or not children_ref[1]:
                return None
                
            children = children_ref[1]
            for i in range(CFArrayGetCount(children)):
                child = CFArrayGetValueAtIndex(children, i)
                
                # Check if this is a close button
                role_ref = AXUIElementCopyAttributeValue(child, kAXRoleAttribute, None)
                if role_ref[0] == 0 and role_ref[1]:
                    role = str(role_ref[1])
                    if "Button" in role:
                        # Check if it's the close button (usually the first button)
                        return child
                        
            return None
        except Exception:
            return None

    # =============== INTROSPECTION METHODS ===============
    
    def get_element_under_cursor(self) -> Tuple[bool, str]:
        """Get detailed info about UI element under mouse cursor (macOS equivalent of ShareX detection)"""
        try:
            # Get cursor position
            success, msg, cursor_pos = self.get_cursor_position()
            if not success or not cursor_pos:
                return False, "Could not get cursor position"
            
            x, y = cursor_pos
            
            # Convert to Core Graphics coordinates for element detection
            main_screen = NSScreen.mainScreen()
            screen_height = main_screen.frame().size.height
            cg_point = Quartz.CGPoint(x, screen_height - y)
            
            output = []
            output.append(f"🎯 ELEMENT UNDER CURSOR ({x}, {y})")
            output.append("=" * 50)
            
            if ACCESSIBILITY_AVAILABLE:
                try:
                    # Get system-wide accessibility element
                    system_element = AXUIElementCreateSystemWide()
                    
                    # Get element at cursor position
                    element_ref = AXUIElementCopyElementAtPosition(system_element, x, y, None)
                    if element_ref[0] == 0 and element_ref[1]:
                        element = element_ref[1]
                        
                        # Get element properties
                        element_info = self._get_element_properties(element)
                        
                        output.append(f"🎨 Element Type: {element_info.get('role', 'Unknown')}")
                        output.append(f"🏷️  Title: {element_info.get('title', 'No title')}")
                        output.append(f"📄 Description: {element_info.get('description', 'No description')}")
                        output.append(f"🆔 Role Description: {element_info.get('role_description', 'Unknown')}")
                        output.append(f"📏 Size: {element_info.get('size', 'Unknown')}")
                        output.append(f"📍 Position: {element_info.get('position', 'Unknown')}")
                        output.append(f"✅ Enabled: {element_info.get('enabled', 'Unknown')}")
                        output.append(f"🎯 Focusable: {element_info.get('focusable', 'Unknown')}")
                        
                        # Get parent application info
                        pid_ref = AXUIElementGetPid(element, None)
                        if pid_ref[0] == 0:
                            pid = pid_ref[1]
                            running_apps = NSWorkspace.sharedWorkspace().runningApplications()
                            for app in running_apps:
                                if app.processIdentifier() == pid:
                                    output.append(f"\n🏠 Parent Application: {app.localizedName()}")
                                    output.append(f"📦 Bundle ID: {app.bundleIdentifier()}")
                                    break
                    else:
                        output.append("❌ No accessibility element found at cursor position")
                        
                except Exception as e:
                    output.append(f"❌ Accessibility detection failed: {e}")
            else:
                output.append("❌ Accessibility API not available")
            
            # Also try to get window information at cursor position
            try:
                # Find window under cursor using Core Graphics
                window_list = Quartz.CGWindowListCopyWindowInfo(
                    kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements,
                    kCGNullWindowID
                )
                
                if window_list:
                    for window_info in window_list:
                        bounds = window_info.get('kCGWindowBounds', {})
                        window_x = bounds.get('X', 0)
                        window_y = bounds.get('Y', 0)
                        window_width = bounds.get('Width', 0)
                        window_height = bounds.get('Height', 0)
                        
                        if (window_x <= x <= window_x + window_width and
                            window_y <= y <= window_y + window_height):
                            
                            output.append(f"\n🪟 Window Information:")
                            output.append(f"   App: {window_info.get('kCGWindowOwnerName', 'Unknown')}")
                            output.append(f"   Title: {window_info.get('kCGWindowName', 'Untitled')}")
                            output.append(f"   Window ID: {window_info.get('kCGWindowNumber', 'Unknown')}")
                            output.append(f"   Layer: {window_info.get('kCGWindowLayer', 'Unknown')}")
                            output.append(f"   Bounds: {window_x}, {window_y}, {window_width}x{window_height}")
                            break
                            
            except Exception as e:
                output.append(f"❌ Window detection failed: {e}")
            
            return True, "\n".join(output)
            
        except Exception as e:
            return False, f"Failed to get element under cursor: {e}"

    def introspect_window(self, window_number: int) -> Tuple[bool, str]:
        """Deep introspection of a window"""
        try:
            time.sleep(0.1)
            
            if not self.is_window_valid(window_number):
                return False, "Window is no longer valid"
            
            # Get window info
            window_info = self._get_window_info(window_number)
            if not window_info:
                return False, "Could not get window information"
            
            output = []
            output.append("🔍 WINDOW INTROSPECTION")
            output.append("=" * 50)
            
            # Basic window information
            app_name = window_info.get('kCGWindowOwnerName', 'Unknown')
            window_name = window_info.get('kCGWindowName', 'Untitled')
            pid = window_info.get('kCGWindowOwnerPID', 0)
            layer = window_info.get('kCGWindowLayer', 0)
            
            bounds = window_info.get('kCGWindowBounds', {})
            width = bounds.get('Width', 0)
            height = bounds.get('Height', 0)
            x = bounds.get('X', 0)
            y = bounds.get('Y', 0)
            
            output.append(f"📱 Application: {app_name}")
            output.append(f"🪟 Window: {window_name}")
            output.append(f"🆔 Window Number: {window_number}")
            output.append(f"🔢 Process ID: {pid}")
            output.append(f"📏 Size: {width}x{height}")
            output.append(f"📍 Position: ({x}, {y})")
            output.append(f"🎚️  Layer: {layer}")
            
            # Get application information
            if pid:
                running_apps = NSWorkspace.sharedWorkspace().runningApplications()
                for app in running_apps:
                    if app.processIdentifier() == pid:
                        output.append(f"\n📦 Bundle ID: {app.bundleIdentifier()}")
                        output.append(f"🚀 Launched: {app.launchDate()}")
                        output.append(f"⚡ Active: {app.isActive()}")
                        output.append(f"🔒 Hidden: {app.isHidden()}")
                        break
            
            # Accessibility introspection
            if ACCESSIBILITY_AVAILABLE and pid:
                try:
                    app_element = AXUIElementCreateApplication(pid)
                    if app_element:
                        # Get window elements
                        windows_ref = AXUIElementCopyAttributeValue(app_element, kAXWindowsAttribute, None)
                        if windows_ref[0] == 0 and windows_ref[1]:
                            windows = windows_ref[1]
                            window_count = CFArrayGetCount(windows)
                            
                            output.append(f"\n🪟 Accessibility Windows: {window_count}")
                            
                            # Analyze first window (main window)
                            if window_count > 0:
                                main_window = CFArrayGetValueAtIndex(windows, 0)
                                window_props = self._get_element_properties(main_window)
                                
                                output.append(f"   🎯 Main Window Role: {window_props.get('role', 'Unknown')}")
                                output.append(f"   🏷️  Title: {window_props.get('title', 'No title')}")
                                output.append(f"   ✅ Enabled: {window_props.get('enabled', 'Unknown')}")
                                output.append(f"   🎯 Focusable: {window_props.get('focusable', 'Unknown')}")
                                output.append(f"   📦 Minimized: {window_props.get('minimized', 'Unknown')}")
                                
                                # Get child elements
                                children_ref = AXUIElementCopyAttributeValue(main_window, kAXChildrenAttribute, None)
                                if children_ref[0] == 0 and children_ref[1]:
                                    children = children_ref[1]
                                    child_count = CFArrayGetCount(children)
                                    output.append(f"   👶 Child Elements: {child_count}")
                                    
                                    # Show first few children
                                    for i in range(min(child_count, 5)):
                                        child = CFArrayGetValueAtIndex(children, i)
                                        child_props = self._get_element_properties(child)
                                        role = child_props.get('role', 'Unknown')
                                        title = child_props.get('title', 'No title')[:30]
                                        output.append(f"      {i+1}. {role}: {title}")
                                    
                                    if child_count > 5:
                                        output.append(f"      ... and {child_count - 5} more")
                        
                except Exception as e:
                    output.append(f"❌ Accessibility introspection failed: {e}")
            
            return True, "\n".join(output)
            
        except Exception as e:
            return False, f"Failed to introspect window: {e}"

    def _get_element_properties(self, element) -> Dict:
        """Get properties of an accessibility element"""
        properties = {}
        
        if not ACCESSIBILITY_AVAILABLE or not element:
            return properties
        
        try:
            # Get role
            role_ref = AXUIElementCopyAttributeValue(element, kAXRoleAttribute, None)
            if role_ref[0] == 0 and role_ref[1]:
                properties['role'] = str(role_ref[1])
            
            # Get title
            title_ref = AXUIElementCopyAttributeValue(element, kAXTitleAttribute, None)
            if title_ref[0] == 0 and title_ref[1]:
                properties['title'] = str(title_ref[1])
            
            # Get description
            try:
                desc_ref = AXUIElementCopyAttributeValue(element, "AXDescription", None)
                if desc_ref[0] == 0 and desc_ref[1]:
                    properties['description'] = str(desc_ref[1])
            except:
                pass
            
            # Get role description
            try:
                role_desc_ref = AXUIElementCopyAttributeValue(element, "AXRoleDescription", None)
                if role_desc_ref[0] == 0 and role_desc_ref[1]:
                    properties['role_description'] = str(role_desc_ref[1])
            except:
                pass
            
            # Get position
            pos_ref = AXUIElementCopyAttributeValue(element, kAXPositionAttribute, None)
            if pos_ref[0] == 0 and pos_ref[1]:
                pos = Foundation.NSValue(pos_ref[1]).pointValue()
                properties['position'] = f"({int(pos.x)}, {int(pos.y)})"
            
            # Get size
            size_ref = AXUIElementCopyAttributeValue(element, kAXSizeAttribute, None)
            if size_ref[0] == 0 and size_ref[1]:
                size = Foundation.NSValue(size_ref[1]).sizeValue()
                properties['size'] = f"{int(size.width)}x{int(size.height)}"
            
            # Get enabled state
            try:
                enabled_ref = AXUIElementCopyAttributeValue(element, "AXEnabled", None)
                if enabled_ref[0] == 0 and enabled_ref[1]:
                    properties['enabled'] = bool(enabled_ref[1])
            except:
                pass
            
            # Get focusable state
            try:
                focus_ref = AXUIElementCopyAttributeValue(element, "AXFocusable", None)
                if focus_ref[0] == 0 and focus_ref[1]:
                    properties['focusable'] = bool(focus_ref[1])
            except:
                pass
            
            # Get minimized state
            try:
                min_ref = AXUIElementCopyAttributeValue(element, kAXMinimizedAttribute, None)
                if min_ref[0] == 0 and min_ref[1]:
                    properties['minimized'] = bool(min_ref[1])
            except:
                pass
                
        except Exception:
            pass
        
        return properties

    # Add these methods to the MacWindowManager class

    def launch_application(self, app_name: str, display_id: int, fullscreen: bool = True) -> Tuple[bool, str]:
        """Launch an application on a specific display"""
        try:
            workspace = NSWorkspace.sharedWorkspace()
            
            # Find the application
            app_url = workspace.URLForApplicationWithBundleIdentifier_(app_name)
            if not app_url:
                # Try finding by name if bundle ID fails
                app_url = workspace.fullPathForApplication_(app_name)
                if not app_url:
                    return False, f"Application '{app_name}' not found"
                app_url = NSURL.fileURLWithPath_(app_url)
            
            # Launch the application
            configuration = {
                NSWorkspaceLaunchConfigurationArguments: [],
                NSWorkspaceLaunchConfigurationEnvironment: {},
            }
            
            app, error = workspace.launchApplicationAtURL_options_configuration_error_(
                app_url,
                NSWorkspaceLaunchDefault,
                configuration,
                None
            )
            
            if not app:
                return False, f"Failed to launch application: {error}"
            
            # Wait for the application to launch
            time.sleep(1)
            
            # Get the application's windows
            windows = self.find_window_by_app(app_name)
            if not windows:
                return True, "Application launched, but no window found"
            
            # Move the main window to the target display and set fullscreen if requested
            main_window = windows[0]
            window_number = main_window['number']
            
            if display_id > 0:
                self.move_window_to_display(window_number, display_id)
            
            if fullscreen:
                self.maximize_window(window_number)
            
            return True, f"Application launched successfully on display {display_id}"
        
        except Exception as e:
            return False, f"Error launching application: {str(e)}"

    def get_window_hierarchy_tree(self, window_number: int) -> Tuple[bool, str]:
        """Get a formatted string representation of the window's UI element hierarchy"""
        try:
            # Get the window's process ID
            window_info = self._get_window_info(window_number)
            if not window_info:
                return False, "Window not found"
            
            pid = window_info.get('kCGWindowOwnerPID')
            if not pid:
                return False, "Window process ID not found"
            
            # Create the accessibility element for the application
            app_element = AXUIElementCreateApplication(pid)
            if not app_element:
                return False, "Failed to create accessibility element"
            
            # Find the specific window
            window_element = self._find_window_element(app_element, window_number)
            if not window_element:
                return False, "Failed to find window element"
            
            # Build the hierarchy tree
            tree = self._build_element_tree(window_element)
            
            # Format the tree as a string
            formatted_tree = self._format_element_tree(tree)
            
            return True, formatted_tree
        
        except Exception as e:
            return False, f"Error getting window hierarchy: {str(e)}"

    def _build_element_tree(self, element, depth=0, max_depth=10) -> Dict:
        """Recursively build a tree structure of UI elements"""
        if depth >= max_depth:
            return {"role": "max_depth_reached"}
        
        try:
            # Get element properties
            role = self._get_ax_attribute(element, kAXRoleAttribute, "unknown")
            title = self._get_ax_attribute(element, kAXTitleAttribute, "")
            
            # Create node
            node = {
                "role": role,
                "title": title,
                "children": []
            }
            
            # Get children
            children = self._get_ax_attribute(element, kAXChildrenAttribute, None)
            if children:
                for child in children:
                    child_tree = self._build_element_tree(child, depth + 1, max_depth)
                    if child_tree:
                        node["children"].append(child_tree)
            
            return node
        
        except Exception:
            return None

    def _format_element_tree(self, tree: Dict, prefix="", is_last=True) -> str:
        """Format a tree structure as a string with proper indentation"""
        if not tree:
            return ""
        
        result = []
        
        # Add current node
        marker = "└── " if is_last else "├── "
        title = f" ({tree['title']})" if tree['title'] else ""
        result.append(f"{prefix}{marker}{tree['role']}{title}")
        
        # Add children
        child_prefix = prefix + ("    " if is_last else "│   ")
        children = tree.get("children", [])
        
        for i, child in enumerate(children):
            is_last_child = i == len(children) - 1
            result.append(self._format_element_tree(child, child_prefix, is_last_child))
        
        return "\n".join(result)

    def move_window_to_screen_position(self, window_number: int, display_id: int, x: int, y: int) -> Tuple[bool, str]:
        """Move a window to a specific position relative to a display"""
        try:
            # Validate display ID
            if display_id < 1 or display_id > len(self.displays):
                return False, f"Invalid display ID: {display_id}"
            
            # Get display information
            display = self.displays[display_id - 1]
            display_origin = display['origin']
            
            # Calculate absolute coordinates
            abs_x = display_origin['x'] + x
            abs_y = display_origin['y'] + y
            
            # Move the window
            return self.move_window(window_number, abs_x, abs_y)
        
        except Exception as e:
            return False, f"Error moving window: {str(e)}"

# =============== CONVENIENCE FUNCTIONS ===============

def find_window_by_app(app_name: str) -> List[Dict]:
    """Quick function to find windows by application name"""
    wm = MacWindowManager()
    return wm.find_window_by_app(app_name)

def get_structured_windows() -> Dict:
    """Get structured window data organized by display and application"""
    wm = MacWindowManager()
    return wm.get_structured_windows()

def print_windows(show_minimized: bool = True):
    """Print a clean view of all windows"""
    wm = MacWindowManager()
    wm.print_structured_output(show_minimized)

# Example usage and testing
if __name__ == "__main__":
    try:
        wm = MacWindowManager()
        
        # Print structured output
        print("🚀 Mac Window Manager Test")
        wm.print_structured_output(show_minimized=True)
        
        print("\n" + "="*40 + " JSON OUTPUT " + "="*40)
        # Show JSON format
        data = wm.get_structured_windows()
        print(json.dumps(data, indent=2, default=str))
        
    except Exception as e:
        print(f"Error running Mac Window Manager: {e}")
        print("Make sure you have PyObjC installed: pip install pyobjc")
        print("And that you've granted accessibility permissions to your terminal.")

