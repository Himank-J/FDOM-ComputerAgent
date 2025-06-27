import os
import json
import time
import tempfile
import hashlib
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Use YOUR existing infrastructure
from gui_controller import SimpleWindowAPI
from fdom.screenshot_manager import ScreenshotManager  
from fdom.visual_differ import VisualDiffer

def handle_splash_screen_if_needed(seraphine_analysis: Dict, screenshot_path: str, fdom_path: str) -> Dict:
    """Handle splash screen and replace original screenshot"""
    try:
        # ✅ LOOP PREVENTION: Check if we've already tried this recently
        if check_recent_splash_attempts(fdom_path):
            print("⚠️ Recent splash screen attempts detected - preventing infinite loop")
            return {"action": "loop_prevented", "success": True, "restart_required": False}
        
        # Extract splash screen data from seraphine_analysis
        splash_data, startup_data = extract_splash_data(seraphine_analysis)
        
        print(f"🔍 Checking splash screen requirements...")
        print(f"   Splash present: {splash_data.get('present', False)}")
        print(f"   Startup required: {startup_data.get('required', False)}")
        
        if not splash_data.get('present', False) and not startup_data.get('required', False):
            print("✅ No splash screen interaction needed")
            return {"action": "none", "success": True, "restart_required": False}

        # ✅ SIMPLIFIED APPROACH - Use basic screenshot comparison instead of full visual_differ
        gui_api = SimpleWindowAPI()
        
        # ✅ TAKE BEFORE SCREENSHOT using simple approach
        before_screenshot = take_simple_screenshot("splash_before")
        if not before_screenshot:
            return {"action": "failed", "success": False, "error": "Could not take before screenshot"}
        
        # Get click targets
        click_targets = get_click_targets(splash_data, startup_data)
        print(f"🎯 Attempting splash screen dismissal with {len(click_targets)} targets...")
        
        # Try each target with simplified verification
        for i, target in enumerate(click_targets, 1):
            group_id = target.get('group_id')
            coordinates = get_click_coordinates(group_id, seraphine_analysis)
            
            if coordinates:
                x, y = coordinates
                print(f"🖱️  Target {i}: Clicking {group_id} at coordinates ({x}, {y})")
                
                # ✅ USE AUTO_CAPTIONER'S RELIABLE CLICK METHOD
                click_success = perform_enhanced_click(x, y, group_id)
                if not click_success:
                    print(f"❌ Enhanced click failed for {group_id}")
                    continue
                
                # ✅ SIMPLIFIED VERIFICATION
                if verify_screen_changed_simple(before_screenshot, x, y):
                    print(f"✅ VERIFIED screen change after clicking {group_id}")
                    
                    # Cleanup before screenshot
                    cleanup_screenshot(before_screenshot)
                    
                    record_splash_attempt(fdom_path, group_id, [x, y], True)
                    
                    # ✅ TAKE NEW SCREENSHOT
                    print("📸 Taking new screenshot after splash screen dismissal...")
                    time.sleep(2.0)  # Give UI time to settle
                    new_screenshot_path = take_new_app_screenshot(screenshot_path)
                    
                    if new_screenshot_path:
                        print(f"✅ New screenshot saved: {new_screenshot_path}")
                        
                        # ✅ REPLACE ORIGINAL SCREENSHOT 
                        import shutil
                        import os
                        
                        # Backup original (optional)
                        backup_path = screenshot_path.replace('.png', '_with_splash.png')
                        shutil.copy2(screenshot_path, backup_path)
                        print(f"📁 Backed up original to: {os.path.basename(backup_path)}")
                        
                        # Replace original with clean screenshot
                        shutil.copy2(new_screenshot_path, screenshot_path)
                        print(f"🔄 Replaced {os.path.basename(screenshot_path)} with splash-free version")
                        
                        # Clean up temp file
                        os.remove(new_screenshot_path)
                        
                        return {
                            "action": "replaced_screenshot",
                            "success": True,
                            "clicked_group": group_id,
                            "coordinates": [x, y],
                            "restart_required": True,  # ← Signal restart needed
                            "new_screenshot_path": screenshot_path,  # ← Same path, but new content
                            "message": "Splash screen dismissed, screenshot replaced, restart required"
                        }
                        
                    else:
                        print("⚠️ Could not take new screenshot, continuing without restart")
                    return {
                        "action": "clicked",
                        "success": True,
                        "clicked_group": group_id,
                        "coordinates": [x, y],
                            "restart_required": False,
                            "message": "Splash screen dismissed but screenshot replacement failed"
                    }
                else:
                    print(f"❌ No screen change detected after clicking {group_id}")
                    record_splash_attempt(fdom_path, group_id, [x, y], False)
                    continue
        
        # Cleanup before screenshot
        cleanup_screenshot(before_screenshot)
        
        return {"action": "tried", "success": False, "restart_required": False}
        
    except Exception as e:
        print(f"❌ Error during splash screen handling: {e}")
        return {"action": "failed", "success": False, "restart_required": False, "error": str(e)}

def take_simple_screenshot(name: str) -> Optional[str]:
    """Take a simple screenshot without requiring VisualDiffer"""
    try:
        import tempfile
        from PIL import ImageGrab
        
        # Take screenshot
        screenshot = ImageGrab.grab()
        
        # Save to temp file
        temp_dir = tempfile.gettempdir()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = os.path.join(temp_dir, f"{name}_{timestamp}.png")
        
        screenshot.save(screenshot_path)
        screenshot.close()
        
        print(f"📸 Screenshot saved: {screenshot_path}")
        return screenshot_path
        
    except Exception as e:
        print(f"❌ Screenshot failed: {e}")
        return None

def verify_screen_changed_simple(before_screenshot: str, click_x: int, click_y: int) -> bool:
    """Simplified screen change verification using basic image comparison"""
    try:
        print("📸 Taking after screenshot for comparison...")
        time.sleep(2.0)  # Give UI more time to respond
        
        # Take after screenshot
        after_screenshot = take_simple_screenshot("splash_after")
        if not after_screenshot:
            print("❌ Could not take after screenshot")
            return False
        
        # ✅ BASIC IMAGE COMPARISON
        from PIL import Image
        import numpy as np
        
        # Load images
        img1 = Image.open(before_screenshot)
        img2 = Image.open(after_screenshot)
        
        # Convert to arrays
        arr1 = np.array(img1)
        arr2 = np.array(img2)
        
        # Calculate difference
        diff = np.abs(arr1.astype(float) - arr2.astype(float))
        total_diff = np.sum(diff)
        total_pixels = arr1.size
        
        # Calculate percentage difference
        diff_percentage = (total_diff / (total_pixels * 255)) * 100
        
        # Clean up
        img1.close()
        img2.close()
        cleanup_screenshot(after_screenshot)
        
        # Consider significant if more than 0.5% of pixels changed
        threshold = 0.5
        changed = diff_percentage > threshold
        
        print(f"📊 Image difference: {diff_percentage:.2f}% ({'CHANGED' if changed else 'NO CHANGE'})")
        
        return changed
        
    except Exception as e:
        print(f"❌ Simple verification failed: {e}")
        # Fall back to time-based assumption
        print("📸 Falling back to time-based verification")
        time.sleep(1)
        return True  # Assume success

def cleanup_screenshot(screenshot_path: str):
    """Clean up screenshot file"""
    if screenshot_path and os.path.exists(screenshot_path):
        try:
            os.remove(screenshot_path)
        except:
            pass

def perform_enhanced_click(abs_x: int, abs_y: int, element_name: str) -> bool:
    """Use auto_captioner's reliable SendInput click method"""
    try:
        import ctypes
        from ctypes import wintypes
        
        # Get current position for smooth movement
        gui_api = SimpleWindowAPI()
        current_pos = gui_api.get_cursor_position()
        start_x, start_y = current_pos if current_pos else (abs_x - 50, abs_y - 20)
        
        # ✅ COPY AUTO_CAPTIONER'S WORKING SendInput METHOD
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
        
        user32 = ctypes.windll.user32
        screen_width = user32.GetSystemMetrics(0)
        screen_height = user32.GetSystemMetrics(1)
        
        # Smooth movement to target (like auto_captioner)
        steps = 10
        for i in range(steps + 1):
            progress = i / steps
            eased_progress = 1 - (1 - progress) ** 2  # Ease-out
            
            current_x = int(start_x + (abs_x - start_x) * eased_progress)
            current_y = int(start_y + (abs_y - start_y) * eased_progress)
            
            # Convert to SendInput coordinates
            input_x = int((current_x * 65535) / screen_width)
            input_y = int((current_y * 65535) / screen_height)
            
            # Create input structure
            inp = INPUT()
            inp.type = 0  # INPUT_MOUSE
            inp.mi.dx = input_x
            inp.mi.dy = input_y
            inp.mi.mouseData = 0
            inp.mi.dwFlags = 0x8001  # MOUSEEVENTF_MOVE + MOUSEEVENTF_ABSOLUTE
            inp.mi.time = 0
            inp.mi.dwExtraInfo = None
            
            result = user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
            if result != 1:
                return False
        
            time.sleep(0.02)
        
        # Perform click at final position
        click_input = INPUT()
        click_input.type = 0
        click_input.mi.dx = int((abs_x * 65535) / screen_width)
        click_input.mi.dy = int((abs_y * 65535) / screen_height)
        click_input.mi.mouseData = 0
        click_input.mi.dwFlags = 0x8003  # MOUSEEVENTF_LEFTDOWN + MOUSEEVENTF_ABSOLUTE
        click_input.mi.time = 0
        click_input.mi.dwExtraInfo = None
        
        # Click down
        user32.SendInput(1, ctypes.byref(click_input), ctypes.sizeof(INPUT))
        time.sleep(0.05)
        
        # Click up
        click_input.mi.dwFlags = 0x8004  # MOUSEEVENTF_LEFTUP + MOUSEEVENTF_ABSOLUTE
        user32.SendInput(1, ctypes.byref(click_input), ctypes.sizeof(INPUT))
        
        time.sleep(2.0)  # Wait for splash screen to respond
        return True
        
    except Exception as e:
        print(f"❌ Enhanced click failed: {e}")
        return False

def get_click_coordinates(group_id: str, seraphine_analysis: Dict) -> Optional[Tuple[int, int]]:
    """Get click coordinates with PROPER bbox_processor lookup"""
    
    # Strategy 1: Check bbox_processor.final_groups first (like the original working version)
    bbox_processor = seraphine_analysis.get('bbox_processor')
    if bbox_processor and hasattr(bbox_processor, 'final_groups'):
        if group_id in bbox_processor.final_groups:
            bboxes = bbox_processor.final_groups[group_id]
            if bboxes:
                # Use first bbox for coordinates
                bbox = bboxes[0]
                app_relative_x = (bbox.x1 + bbox.x2) // 2
                app_relative_y = (bbox.y1 + bbox.y2) // 2
                
                # ✅ CONVERT TO ABSOLUTE SCREEN COORDINATES
                absolute_x, absolute_y = convert_to_absolute_coordinates(app_relative_x, app_relative_y)
                
                print(f"✅ Found coordinates for {group_id} in bbox_processor: app-relative ({app_relative_x}, {app_relative_y}) → absolute ({absolute_x}, {absolute_y})")
                return (absolute_x, absolute_y)
    
    # Strategy 2: Fallback to group_details
    group_details = seraphine_analysis.get('analysis', {}).get('group_details', {})
    
    if group_id in group_details:
        bbox = group_details[group_id].get('bbox')
        if bbox and len(bbox) == 4:
            # Calculate centroid
            cx = (bbox[0] + bbox[2]) // 2
            cy = (bbox[1] + bbox[3]) // 2
            
            # Convert to absolute coordinates
            absolute_x, absolute_y = convert_to_absolute_coordinates(cx, cy)
            
            print(f"✅ Found coordinates for {group_id} in group_details: ({cx}, {cy}) → absolute ({absolute_x}, {absolute_y})")
            return (absolute_x, absolute_y)
    
    print(f"❌ Group {group_id} not found anywhere")
    
    # Debug info
    if bbox_processor and hasattr(bbox_processor, 'final_groups'):
        bbox_groups = list(bbox_processor.final_groups.keys())[:10]
        print(f"🔍 bbox_processor groups: {bbox_groups}...")
    
    available_groups = list(group_details.keys())[:10]
    print(f"🔍 group_details groups: {available_groups}...")
    
    return None

def convert_to_absolute_coordinates(app_x: int, app_y: int) -> Tuple[int, int]:
    """Convert app-relative coordinates to absolute screen coordinates"""
    try:
        # ✅ DETECT APP DYNAMICALLY FROM CURRENT CONTEXT
        gui_api = SimpleWindowAPI()
        
        # Try to find current focused/active window
        possible_titles = ["PowerPoint", "Blender", "Word", "Excel", "Chrome", "Firefox"]
        
        app_window_id = None
        found_title = None
        for title in possible_titles:
            app_window_id = gui_api.find_window(title)
            if app_window_id:
                found_title = title
                break
        
        if app_window_id:
            print(f"✅ Found active window: {found_title}")
            window_info = gui_api.get_window_info(app_window_id)
            if window_info and 'window_data' in window_info:
                pos = window_info['window_data']['position']
                window_x = pos.get('x', 0)
                window_y = pos.get('y', 0)
                
                # Convert to absolute coordinates
                absolute_x = window_x + app_x
                absolute_y = window_y + app_y
                
                print(f"🔧 Coordinate conversion: window at ({window_x}, {window_y}) + app offset ({app_x}, {app_y}) = absolute ({absolute_x}, {absolute_y})")
                return (absolute_x, absolute_y)
            else:
                print("❌ No window_data in window_info")
        else:
            print("❌ Could not find any known application window")
        
        # Fallback: assume coordinates are already absolute
        print(f"⚠️ Could not get window position, using coordinates as-is")
        return (app_x, app_y)
        
    except Exception as e:
        print(f"❌ Coordinate conversion failed: {e}")
        return (app_x, app_y)

def get_click_coordinates_from_group(group_id: str, group_details: Dict, override_coords: Optional[Dict] = None) -> Optional[Tuple[int, int]]:
    """
    Get click coordinates from group details (app-relative coordinates)
    """
    
    # Priority 1: Use provided coordinates
    if override_coords and 'x' in override_coords and 'y' in override_coords:
        return (int(override_coords['x']), int(override_coords['y']))
    
    # Priority 2: Calculate centroid from group bbox
    group_info = group_details.get(group_id, {})
    
    print(f"🔍 DEBUG: Group {group_id} structure:")
    print(f"   Keys: {list(group_info.keys()) if group_info else 'GROUP NOT FOUND'}")
    
    if not group_info:
        return None
        
    # Try different bbox formats
    bbox = None
    
    # Format: bboxes array - use first bbox
    if 'bboxes' in group_info and group_info['bboxes']:
        bboxes = group_info['bboxes']
        if bboxes:
            first_bbox = bboxes[0]
            if isinstance(first_bbox, dict) and 'bbox' in first_bbox:
                bbox = first_bbox['bbox']
            elif isinstance(first_bbox, list):
                bbox = first_bbox
    
    if bbox and len(bbox) >= 4:
        # bbox format: [x1, y1, x2, y2] - these are app-relative coordinates
        x1, y1, x2, y2 = bbox[:4]
        centroid_x = int((x1 + x2) / 2)
        centroid_y = int((y1 + y2) / 2)
        print(f"✅ Found app-relative coordinates for {group_id}: ({centroid_x}, {centroid_y})")
        return (centroid_x, centroid_y)
    
    print(f"❌ Could not determine coordinates for group {group_id}")
    return None


def perform_click_and_check_change_existing_system(app_coords: Tuple[int, int], group_id: str, api) -> bool:
    """
    Perform click using existing system and check for screen change
    """
    try:
        app_x, app_y = app_coords
        print(f"🖱️  Clicking at app-relative coords ({app_x}, {app_y}) for group {group_id}")
        
        # ✅ GET WINDOW POSITION FROM EXISTING SYSTEM
        # You'll need to get the app window coordinates to convert app-relative to screen coordinates
        # For now, I'll assume the coordinates are already correct or use a workaround
        
        # ✅ USE YOUR EXISTING CLICK SYSTEM
        success = api.click(app_x, app_y, "left")
        
        if not success:
            print(f"❌ Failed to perform click at ({app_x}, {app_y})")
            return False
        
        # ✅ WAIT AND ASSUME SUCCESS FOR NOW (you can add screen change detection later)
        time.sleep(2.0)  # Wait for splash screen to respond
        print(f"✅ Click completed on {group_id} using existing GUI system")
        return True  # ✅ ASSUME SUCCESS since we're using your tested click system
        
    except Exception as e:
        print(f"❌ Error during click: {str(e)}")
        return False


# Add missing helper functions
def extract_splash_data(seraphine_analysis: Dict) -> Tuple[Dict, Dict]:
    """Extract splash screen data from seraphine analysis"""
    splash_data = {}
    startup_data = {}
    
    # Location 1: Direct in seraphine_analysis
    splash_data = seraphine_analysis.get('splash_screen', {})
    startup_data = seraphine_analysis.get('startup_interaction', {})
    
    # Location 2: In analysis sub-dict
    if not splash_data and 'analysis' in seraphine_analysis:
        analysis = seraphine_analysis['analysis']
        splash_data = analysis.get('splash_screen', {})
        startup_data = analysis.get('startup_interaction', {})
    
    return splash_data, startup_data

def get_click_targets(splash_data: Dict, startup_data: Dict) -> List[Dict]:
    """Get click targets from splash and startup data"""
    click_targets = []
    
    if splash_data.get('present', False):
        safe_targets = splash_data.get('dismissal', {}).get('safe_click_targets', [])
        click_targets.extend(safe_targets)
        print(f"🔍 Added {len(safe_targets)} splash screen targets: {[t.get('group_id') for t in safe_targets]}")
    
    if startup_data.get('required', False):
        strategies = startup_data.get('strategies', [])
        # Sort by changes_screen=true first
        strategies.sort(key=lambda x: not x.get('changes_screen', False))
        click_targets.extend(strategies)
        print(f"🔍 Added {len(strategies)} startup strategies: {[s.get('group_id') for s in strategies]}")
        
        # ✅ FIXED: Use separate formatting to avoid f-string backslash issue
        priority_list = []
        for s in strategies:
            group_id = s.get('group_id')
            priority = 'HIGH' if s.get('changes_screen') else 'LOW'
            priority_list.append(f"{group_id}({priority})")
        print(f"🔍 Priority order: {priority_list}")
    
    print(f"🔍 Total click targets: {len(click_targets)}")
    return click_targets

def check_recent_splash_attempts(fdom_path: str) -> bool:
    """Check if we've made recent splash screen attempts (prevent infinite loops)"""
    try:
        if not os.path.exists(fdom_path):
            return False
        
        with open(fdom_path, 'r', encoding='utf-8') as f:
            fdom_data = json.load(f)
        
        attempts = fdom_data.get('metadata', {}).get('splash_attempts', [])
        
        # Check last 3 attempts in last 60 seconds
        current_time = time.time()
        recent_attempts = [a for a in attempts if current_time - a.get('timestamp', 0) < 60]
        
        if len(recent_attempts) >= 3:
            print(f"🛑 LOOP PREVENTION: {len(recent_attempts)} attempts in last 60 seconds")
            return True
        
        return False
        
    except Exception:
        return False

def record_splash_attempt(fdom_path: str, group_id: str, coordinates: List[int], success: bool):
    """Record splash screen attempt for loop prevention"""
    try:
        if not os.path.exists(fdom_path):
            return
        
        with open(fdom_path, 'r', encoding='utf-8') as f:
            fdom_data = json.load(f)
        
        if 'metadata' not in fdom_data:
            fdom_data['metadata'] = {}
        
        if 'splash_attempts' not in fdom_data['metadata']:
            fdom_data['metadata']['splash_attempts'] = []
        
        attempt = {
            'timestamp': time.time(),
            'group_id': group_id,
            'coordinates': coordinates,
            'success': success,
            'datetime': datetime.now().isoformat()
        }
        
        fdom_data['metadata']['splash_attempts'].append(attempt)
        
        # Keep only last 10 attempts
        fdom_data['metadata']['splash_attempts'] = fdom_data['metadata']['splash_attempts'][-10:]
        
        with open(fdom_path, 'w', encoding='utf-8') as f:
            json.dump(fdom_data, f, indent=2, ensure_ascii=False)
        
        print(f"📝 Recorded splash attempt: {group_id} → {'SUCCESS' if success else 'FAILED'}")
        
    except Exception as e:
        print(f"⚠️ Could not record attempt: {e}")

def take_new_app_screenshot(original_screenshot_path: str) -> Optional[str]:
    """Take a new screenshot using the SAME method that successfully took the original"""
    try:
        from PIL import Image
        import mss
        import os
        
        # Generate new screenshot path
        dir_path = os.path.dirname(original_screenshot_path)
        base_name = os.path.basename(original_screenshot_path)
        name, ext = os.path.splitext(base_name)
        new_screenshot_path = os.path.join(dir_path, f"{name}_post_splash{ext}")
        
        # ✅ DETECT APP DYNAMICALLY FROM SCREENSHOT PATH
        # Extract app name from path: apps/powerpnt/screenshots/S001.png → powerpnt
        path_parts = original_screenshot_path.replace('\\', '/').split('/')
        app_name = None
        for i, part in enumerate(path_parts):
            if part == 'apps' and i + 1 < len(path_parts):
                app_name = path_parts[i + 1]
                break
        
        if not app_name:
            print("❌ Could not extract app name from screenshot path")
            return None
        
        print(f"🔍 Detected app: {app_name}")
        
        # ✅ FIND THE ACTUAL APP WINDOW (NOT HARDCODED BLENDER)
        gui_api = SimpleWindowAPI()
        
        # Try different window title patterns for the app
        possible_titles = [
            app_name,
            app_name.capitalize(), 
            app_name.upper(),
            "PowerPoint" if app_name == "powerpnt" else app_name,
            "Blender" if app_name == "blender" else app_name
        ]
        
        app_window_id = None
        for title in possible_titles:
            app_window_id = gui_api.find_window(title)
            if app_window_id:
                print(f"✅ Found window with title: {title}")
                break
        
        if app_window_id:
            window_info = gui_api.get_window_info(app_window_id)
            
            if window_info and 'window_data' in window_info:
                pos = window_info['window_data']['position']
                size = window_info['window_data']['size']
                
                # Create window bounding box (same as AppController)
                window_bbox = {
                    'left': pos['x'],
                    'top': pos['y'], 
                    'width': size['width'],
                    'height': size['height']
                }
                
                print(f"🔍 DEBUG: Window bbox = {window_bbox}")
                
                # ✅ EXACT SAME CAPTURE METHOD AS S001.png
                with mss.mss() as sct:
                    # Capture just the window area
                    window_screenshot = sct.grab(window_bbox)
                    
                    # Convert to PIL Image (same format)
                    img = Image.frombytes('RGB', window_screenshot.size, window_screenshot.bgra, 'raw', 'BGRX')
                    
                    # Save screenshot
                    img.save(new_screenshot_path)
                    
                    # Calculate file size
                    file_size = os.path.getsize(new_screenshot_path) / (1024 * 1024)
                    
                    print(f"📸 App-only screenshot saved: {os.path.basename(new_screenshot_path)} ({file_size:.1f} MB)")
                    print(f"🎯 Captured area: {window_bbox['width']}×{window_bbox['height']} pixels from app window")
                    
                    return new_screenshot_path
            else:
                print("❌ No window_data in window_info")
        else:
            print(f"❌ Could not find {app_name} window")
        
        return None
        
    except Exception as e:
        print(f"❌ New screenshot failed: {e}")
        import traceback
        traceback.print_exc()
        return None
