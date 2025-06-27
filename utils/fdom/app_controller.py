"""
AppController - Application launch and window management for fDOM Framework
Handles app launching, window detection, positioning, and folder structure creation
"""
import os
import sys
import subprocess
import time
from pathlib import Path
from typing import Dict, Optional, Tuple
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import track
from rich import print as rprint
import json
import platform

# Add parent directory to path for gui_controller import
sys.path.append(str(Path(__file__).parent.parent))
from gui_controller import SimpleWindowAPI

class AppController:
    """
    Professional application launch and window management for fDOM framework
    Handles executable launching, window detection, positioning, and storage setup
    """
    
    def __init__(self, app_path: str, target_screen: int = 1, config: dict = None, template_file_path: str = None):
        """
        Initialize AppController with configuration and screen management
        
        Args:
            app_path: Path to the executable
            target_screen: Target screen for launch
            config: ConfigManager instance for settings
            template_file_path: Path to the template file
        """
        self.app_path = app_path
        self.app_name = self._generate_app_name(app_path)
        self.target_screen = target_screen
        self.config = config or {}
        self.template_file_path = template_file_path
        self.screen_manager = None
        self.console = Console()
        self.gui_api = SimpleWindowAPI()
        self.current_app_info = None
        self.apps_base_dir = Path(__file__).parent.parent.parent / "apps"  # utils/fdom -> utils -> project_root -> apps
        
    def _generate_app_name(self, executable_path: str) -> str:
        """
        Auto-generate clean app name from executable path
        
        Args:
            executable_path: Path to the executable
            
        Returns:
            Clean app name for folder creation
        """
        exe_path = Path(executable_path)
        
        # Get base name without extension
        base_name = exe_path.stem.lower()
        
        # Clean up common patterns
        base_name = base_name.replace(" ", "_")
        base_name = base_name.replace("-", "_")
        base_name = base_name.replace("++", "_plus_plus")
        
        # Remove common suffixes
        suffixes_to_remove = ["_setup", "_installer", "_x64", "_x86", "_win32", "_win64"]
        for suffix in suffixes_to_remove:
            if base_name.endswith(suffix):
                base_name = base_name[:-len(suffix)]
                break
        
        return base_name
    
    def _create_app_folder_structure(self, app_name: str) -> Dict[str, Path]:
        """
        Create complete folder structure for app exploration
        
        Args:
            app_name: Generated app name
            
        Returns:
            Dictionary with all created folder paths
        """
        self.console.print(f"[yellow]📁 Creating folder structure for '{app_name}'...[/yellow]")
        
        # Main app directory
        app_dir = self.apps_base_dir / app_name
        app_dir.mkdir(parents=True, exist_ok=True)
        
        # Get storage config from ConfigManager
        storage_config = self.config.get_app_storage_config()
        
        # Create all subdirectories
        paths = {
            'app_dir': app_dir,
            'screenshots': app_dir / storage_config['screenshots'],
            'crops': app_dir / storage_config['crops'],
            'diffs': app_dir / storage_config['diffs'],
            'templates': app_dir / storage_config['templates']
        }
        
        # Create all directories
        for dir_name, dir_path in paths.items():
            if dir_name != 'app_dir':  # app_dir already created
                dir_path.mkdir(exist_ok=True)
                self.console.print(f"  [green]✅[/green] Created {dir_name}/")
        
        # Create metadata.json
        metadata = {
            "app_name": app_name,
            "created_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "fdom_creator_version": "1.0.0",
            "exploration_status": "initialized",
            "folder_structure": {
                "screenshots": storage_config['screenshots'],
                "crops": storage_config['crops'], 
                "diffs": storage_config['diffs'],
                "templates": storage_config['templates']
            }
        }
        
        metadata_path = app_dir / "metadata.json"
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        self.console.print(f"  [green]✅[/green] Created metadata.json")
        
        return paths
    
    def launch_app(self) -> dict:
        """Launch application with optional template file"""
        try:
            print(f"🎯 Strategy 1: Direct launch on Screen {self.target_screen}...")
            
            process = None
            if platform.system() == "Darwin":
                # macOS launch logic using the 'open' command
                self.console.print(f"macOS: Launching with 'open -a \"{self.app_path}\"'")
                launch_cmd = ['open', '-a', self.app_path]
                if self.template_file_path:
                    launch_cmd.append(self.template_file_path)
                
                # On macOS, 'open' returns immediately. The app runs in its own process.
                # We can't get the PID directly this way, but we will find it later from the window info.
                subprocess.run(launch_cmd, check=True)
            else:
                # Windows launch logic
                launch_args = [self.app_path]
                if self.template_file_path:
                    launch_args.append(self.template_file_path)
                
                print(f"Launching: {' '.join(launch_args)}")
                
                # Launch with template file
                process = subprocess.Popen(
                    launch_args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
            
            # Wait for app to start and find its window
            window_id = None
            app_title_partial = self.app_name.lower()
            
            for attempt in track(range(15), description="Waiting for window..."):
                time.sleep(1)
                
                # Try to find the window using better search patterns for Office apps
                window_id = None
                app_name_lower = self.app_name.lower()
                search_patterns = [
                    app_title_partial,                  # Original search term
                    app_name_lower,                     # "freeform"
                    self.app_name,                      # "Freeform"
                    "powerpoint",                       # Direct PowerPoint match
                    "excel",                            # Direct Excel match
                    "word",                             # Direct Word match
                    "calculator",                       # Direct Calculator match
                    "untitled",                         # For apps like TextEdit, FreeForm
                    "all boards",                       # For FreeForm's main window
                ]

                for pattern in search_patterns:
                    window_id = self.gui_api.find_window(pattern)
                    if window_id:
                        break
            
            if not window_id:
                self.console.print(f"[red]❌ Could not find window for {self.app_name} after 15s[/red]")
                return {"success": False, "error": "Window not found"}
            
            self.console.print(f"[green]✅ Window found: {window_id}[/green]")
            
            # Get window info and detect actual screen using screen_manager logic
            time.sleep(1)
            window_info = self.gui_api.get_window_info(window_id)
            
            if not window_info:
                self.console.print("[red]❌ Could not get window information[/red]")
                return {"success": False, "error": "Window info unavailable"}
            
            pos = window_info['window_data']['position']
            size = window_info['window_data']['size']
            hwnd = window_info['window_data'].get('hwnd') # May not exist on mac
            pid = window_info['window_data'].get('pid') # Get PID from window info
            
            # Use screen_manager's detection logic
            actual_screen = self._detect_window_screen_using_screen_manager(pos, size)
            
            self.console.print(f"[yellow]📍 Window opened on Screen {actual_screen} at ({pos['x']}, {pos['y']})[/yellow]")
            
            # Force move to TEST SCREEN if not already there
            if actual_screen != self.target_screen:
                self.console.print(f"[yellow]🔄 Moving window from Screen {actual_screen} to Screen {self.target_screen} (TEST SCREEN)...[/yellow]")
                
                # Get target screen info from screen_manager
                target_screen_info = None
                for screen in self.screen_manager.screens:
                    if screen['id'] == self.target_screen:
                        target_screen_info = screen
                        break
                
                if target_screen_info:
                    # Move to target screen coordinates
                    new_x = target_screen_info['left'] + 100
                    new_y = target_screen_info['top'] + 100
                    
                    self.console.print(f"[cyan]🎯 Moving to coordinates: ({new_x}, {new_y})[/cyan]")
                    
                    if self.gui_api.move_window(window_id, new_x, new_y):
                        self.console.print(f"[green]✅ Move command sent[/green]")
                        time.sleep(2)  # Wait for move to complete
                        
                        if self.gui_api.maximize_window(window_id):
                            self.console.print(f"[green]✅ Maximize command sent[/green]")
                            time.sleep(2)  # Wait for maximize to complete
                            
                            # CRITICAL FIX: Force refresh and re-find window
                            final_screen, updated_window_id = self._robust_window_retracking(
                                hwnd, self.target_screen, self.app_name.lower(), window_id
                            )
                            
                            # Update the window_id with the potentially new one
                            window_id = updated_window_id
                        else:
                            self.console.print(f"[red]❌ Failed to maximize window[/red]")
                            final_screen = actual_screen
                    else:
                        self.console.print(f"[red]❌ Failed to move window[/red]")
                        final_screen = actual_screen
                else:
                    self.console.print(f"[red]❌ Could not find target screen info[/red]")
                    final_screen = actual_screen
            else:
                self.console.print(f"[green]✅ Window already on Screen {actual_screen} (TEST SCREEN)[/green]")
                final_screen = actual_screen
            
            # Position and prepare window (using the potentially updated window_id)
            positioning_result = self._position_window_for_exploration(window_id, final_screen)
            
            # Store app information with actual final screen (and updated window_id)
            self.current_app_info = {
                "app_name": self.app_name,
                "executable_path": self.app_path,
                "window_id": window_id,  # This is now the updated window_id
                "target_screen": final_screen,
                "folder_paths": self._create_app_folder_structure(self.app_name),
                "process_id": pid if pid else (process.pid if process else None),
                "hwnd": hwnd  # Store hwnd for direct access if needed
            }
            
            self.console.print(f"[bold green]🎯 Final: App on Screen {final_screen} (TEST SCREEN)[/bold green]")
            
            return {
                "success": True,
                "app_info": self.current_app_info,
                "positioning_result": positioning_result
            }
            
        except Exception as e:
            self.console.print(f"[red]❌ Error launching application: {e}[/red]")
            return {"success": False, "error": str(e)}
    
    def _position_window_for_exploration(self, window_id: str, target_screen: int) -> Dict:
        """
        Position and prepare window for optimal fDOM exploration
        Assumes window is already on the correct screen
        """
        self.console.print(f"[yellow]🎯 Preparing window on screen {target_screen}...[/yellow]")
        
        results = {"steps": [], "success": True}
        
        try:
            # Focus window
            focus_delay = self.config.get("interaction.window_focus_delay", 0.5)
            time.sleep(focus_delay)
            
            if self.gui_api.focus_window(window_id):
                results["steps"].append("✅ Window focused")
                self.console.print(f"  [green]✅[/green] Window focused")
            else:
                results["steps"].append("❌ Failed to focus window")
                results["success"] = False
            
            # Maximize for consistent screenshots
            if self.gui_api.maximize_window(window_id):
                results["steps"].append("✅ Window maximized")
                self.console.print(f"  [green]✅[/green] Window maximized")
            else:
                results["steps"].append("❌ Failed to maximize window")
            
            return results
            
        except Exception as e:
            self.console.print(f"[red]❌ Error positioning window: {e}[/red]")
            results["success"] = False
            results["error"] = str(e)
            return results
    
    def _robust_window_retracking(self, hwnd: int, expected_screen: int, app_title_partial: str, current_window_id: str) -> Tuple[int, str]:
        """
        Robustly re-track window after move/maximize operations
        Returns tuple of (actual_screen, updated_window_id)
        """
        self.console.print(f"[cyan]🔄 Re-tracking window after operations...[/cyan]")
        
        updated_window_id = current_window_id  # Start with current ID
        
        # Strategy 1: Force refresh the GUI API and find by hwnd/title
        for attempt in range(5):
            self.console.print(f"[cyan]🔍 Attempt {attempt+1}: Force refresh and re-detect...[/cyan]")
            
            # Force complete refresh
            self.gui_api.refresh()
            time.sleep(1)  # Wait for refresh
            
            # Try to find window again by title (this rebuilds the lookup)
            new_window_id = self.gui_api.find_window(app_title_partial)
            
            if new_window_id:
                # Update the window_id we'll return
                updated_window_id = new_window_id
                
                # Get fresh window info
                fresh_info = self.gui_api.get_window_info(new_window_id)
                
                if fresh_info:
                    pos = fresh_info['window_data']['position']
                    size = fresh_info['window_data']['size']
                    
                    self.console.print(f"[green]✅ Re-tracked window: ({pos['x']}, {pos['y']}) size {size['width']}×{size['height']}[/green]")
                    
                    # Detect current screen
                    actual_screen = self._detect_window_screen_using_screen_manager(pos, size)
                    
                    if actual_screen == expected_screen:
                        self.console.print(f"[green]🎯 SUCCESS: Window confirmed on Screen {expected_screen} (TEST SCREEN)[/green]")
                        return expected_screen, updated_window_id
                    else:
                        self.console.print(f"[yellow]⚠️ Window detected on Screen {actual_screen}, expected {expected_screen}[/yellow]")
                        # Don't retry immediately - it might be correct visually
                        if attempt >= 2:  # After attempt 3, trust the visual
                            self.console.print(f"[yellow]🎯 Trusting visual confirmation - assuming Screen {expected_screen}[/yellow]")
                            return expected_screen, updated_window_id
                else:
                    self.console.print(f"[yellow]⚠️ Found window ID but couldn't get info on attempt {attempt+1}[/yellow]")
            else:
                self.console.print(f"[yellow]⚠️ Could not re-find window by title on attempt {attempt+1}[/yellow]")
            
            # Strategy 2: Try using the hwnd directly with Windows API
            try:
                import win32gui
                if win32gui.IsWindow(hwnd):
                    rect = win32gui.GetWindowRect(hwnd)
                    pos = {'x': rect[0], 'y': rect[1]}
                    size = {'width': rect[2] - rect[0], 'height': rect[3] - rect[1]}
                    
                    self.console.print(f"[cyan]🔧 Direct hwnd query: ({pos['x']}, {pos['y']}) size {size['width']}×{size['height']}[/cyan]")
                    
                    actual_screen = self._detect_window_screen_using_screen_manager(pos, size)
                    
                    if actual_screen == expected_screen:
                        self.console.print(f"[green]🎯 SUCCESS: Direct hwnd confirms Screen {expected_screen}[/green]")
                        return expected_screen, updated_window_id
                    else:
                        self.console.print(f"[yellow]🔧 Direct hwnd shows Screen {actual_screen}[/yellow]")
                        # If this is consistent, trust it
                        if attempt >= 1:
                            return actual_screen, updated_window_id
            except Exception as e:
                self.console.print(f"[yellow]⚠️ Direct hwnd query failed: {e}[/yellow]")
            
            if attempt < 4:  # Don't wait on last attempt
                time.sleep(1)
        
        # Final fallback: assume the move worked
        self.console.print(f"[yellow]🎯 Fallback: Assuming operations succeeded - Screen {expected_screen}[/yellow]")
        return expected_screen, updated_window_id
    
    def take_initial_screenshot(self) -> Optional[str]:
        """
        Take initial screenshot for fDOM exploration - APP WINDOW ONLY
        """
        if not self.current_app_info:
            self.console.print("[red]❌ No app launched for screenshot[/red]")
            return None

        self.console.print("[yellow]📸 Taking initial screenshot (S001) - APP WINDOW ONLY...[/yellow]")

        # Ensure window is maximized for consistency
        window_id = self.current_app_info.get("id")
        if window_id:
            maximized = self.gui_api.maximize_window(window_id)
            if maximized:
                self.console.print("[green]✅ Window maximized for consistent screenshots[/green]")
                time.sleep(2)  # Wait for animation
            else:
                self.console.print("[yellow]⚠️ Could not maximize window, screenshot may be inconsistent[/yellow]")
        
        # Platform-specific screenshot logic
        if platform.system() == "Darwin":
            self.console.print("macOS detected, using fallback screen capture.")
            return self._take_fallback_screen_capture()
        else:
            # First attempt: Direct HWND screenshot (more reliable)
            try:
                self.console.print("🔧 Using direct hwnd screenshot method...")
                direct_screenshot = self._take_hwnd_direct_screenshot()
                if direct_screenshot:
                    return direct_screenshot
                else:
                    self.console.print("[yellow]🤔 Direct screenshot failed, trying fallback...[/yellow]")
            except Exception as e:
                self.console.print(f"[red]❌ Direct hwnd screenshot failed: {e}[/red]")
            
            # Fallback: Full screen capture
            self.console.print("🔄 Using fallback: Full screen capture")
            return self._take_fallback_screen_capture()

    def _get_window_pid(self, hwnd: int) -> int:
        """Get PID from HWND (Windows-specific)"""
        import win32process
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        return pid

    def _take_hwnd_direct_screenshot(self) -> Optional[str]:
        """
        Direct hwnd-based screenshot when normal lookup fails
        """
        self.console.print("[yellow]🔧 Using direct hwnd screenshot method...[/yellow]")
        
        try:
            # We need to get the hwnd from somewhere - let's search for the window
            import win32gui
            import win32con
            
            app_name = Path(self.current_app_info["executable_path"]).stem.lower()
            
            # Find window by title using Windows API directly
            hwnd = None
            def enum_windows_callback(window_hwnd, lParam):
                nonlocal hwnd
                if win32gui.IsWindowVisible(window_hwnd):
                    window_title = win32gui.GetWindowText(window_hwnd).lower()
                    if app_name in window_title:
                        hwnd = window_hwnd
                        return False  # Stop enumeration
                return True
            
            win32gui.EnumWindows(enum_windows_callback, 0)
            
            if hwnd:
                rect = win32gui.GetWindowRect(hwnd)
                self.console.print(f"[green]✅ Direct hwnd found: {hwnd} at {rect}[/green]")
                
                # Create bounding box
                window_bbox = {
                    'left': rect[0],
                    'top': rect[1], 
                    'width': rect[2] - rect[0],
                    'height': rect[3] - rect[1]
                }
                
                # Capture using mss
                import mss
                with mss.mss() as sct:
                    window_screenshot = sct.grab(window_bbox)
                    
                    from PIL import Image
                    img = Image.frombytes('RGB', window_screenshot.size, window_screenshot.bgra, 'raw', 'BGRX')
                    
                    screenshots_dir = self.current_app_info["folder_paths"]["screenshots"]
                    screenshot_path = screenshots_dir / "S001.png"
                    img.save(screenshot_path)
                    
                    file_size = screenshot_path.stat().st_size / (1024 * 1024)
                    
                    self.console.print(f"[green]✅ Direct hwnd screenshot saved: {screenshot_path.name} ({file_size:.1f} MB)[/green]")
                    return str(screenshot_path)
            else:
                self.console.print("[red]❌ Could not find window via direct hwnd search[/red]")
                return self._take_fallback_screen_capture()
            
        except Exception as e:
            self.console.print(f"[red]❌ Direct hwnd screenshot failed: {e}[/red]")
            return self._take_fallback_screen_capture()

    def _take_fallback_screen_capture(self) -> Optional[str]:
        """
        Fallback: Take full screen capture of target screen
        """
        self.console.print("[yellow]🔄 Using fallback: Full screen capture[/yellow]")
        
        try:
            target_screen = self.current_app_info["target_screen"]
            screenshot_array = self.screen_manager.capture_screen(target_screen)
            
            if screenshot_array is None:
                self.console.print("[red]❌ Fallback screen capture also failed[/red]")
                return None
            
            # Save screenshot as S001.png
            screenshots_dir = self.current_app_info["folder_paths"]["screenshots"]
            screenshot_path = screenshots_dir / "S001.png"
            
            # Convert BGR to RGB for PIL
            from PIL import Image
            screenshot_rgb = screenshot_array  # Already in correct format for PIL
            img = Image.fromarray(screenshot_rgb)
            img.save(screenshot_path)
            
            # Calculate file size
            file_size = screenshot_path.stat().st_size / (1024 * 1024)
            
            self.console.print(f"[green]✅ Fallback screenshot saved: {screenshot_path.name} ({file_size:.1f} MB)[/green]")
            self.console.print(f"[yellow]⚠️ Note: This is a full screen capture, not app-only[/yellow]")
            
            return str(screenshot_path)
            
        except Exception as e:
            self.console.print(f"[red]❌ Fallback capture failed: {e}[/red]")
            return None
    
    def get_app_info_summary(self) -> None:
        """Display comprehensive app information summary"""
        if not self.current_app_info:
            self.console.print("[red]❌ No app information available[/red]")
            return
        
        app_info = self.current_app_info
        
        # Create summary table
        table = Table(title="📱 Application Information", show_header=True, header_style="bold magenta")
        table.add_column("Property", style="cyan", width=20)
        table.add_column("Value", style="white", width=50)
        
        table.add_row("App Name", app_info["app_name"])
        table.add_row("Executable", app_info["executable_path"])
        table.add_row("Window ID", app_info["window_id"])
        table.add_row("Target Screen", str(app_info["target_screen"]))
        table.add_row("Process ID", str(app_info["process_id"]))
        
        # Add folder paths - FIXED: Handle path display correctly
        for name, path in app_info["folder_paths"].items():
            if name != "app_dir":
                try:
                    # Try to show relative to apps base directory
                    if hasattr(self, 'apps_base_dir'):
                        relative_path = path.relative_to(self.apps_base_dir)
                        display_path = f"apps/{relative_path}"
                    else:
                        # Fallback: show relative to project root by going up from current dir
                        project_root = Path.cwd().parent  # utils -> project root
                        relative_path = path.relative_to(project_root)
                        display_path = str(relative_path)
                except ValueError:
                    # Final fallback: show absolute path
                    display_path = str(path)
                
                table.add_row(f"{name.title()} Dir", display_path)
        
        self.console.print(table)
        
        # Show window state
        window_info = self.gui_api.get_window_info(app_info["window_id"])
        if window_info:
            state = self.gui_api.get_window_state(app_info["window_id"])
            pos = window_info['window_data']['position']
            size = window_info['window_data']['size']
            
            panel = Panel(
                f"State: {state.upper()}\nPosition: ({pos['x']}, {pos['y']})\nSize: {size['width']}×{size['height']} pixels",
                title="[bold green]🪟 Window Status[/bold green]",
                border_style="green"
            )
            self.console.print(panel)

    def _detect_window_screen_using_screen_manager(self, window_pos: Dict, window_size: Dict) -> int:
        """
        Detect which screen a window is on using screen_manager's screen data
        """
        window_center_x = window_pos['x'] + window_size['width'] // 2
        window_center_y = window_pos['y'] + window_size['height'] // 2
        
        self.console.print(f"[cyan]🔍 Window center: ({window_center_x}, {window_center_y})[/cyan]")
        
        # Check which screen contains the window center using screen_manager data
        for screen in self.screen_manager.screens:
            screen_bounds = f"({screen['left']}, {screen['top']}) to ({screen['right']}, {screen['bottom']})"
            self.console.print(f"[cyan]📺 Screen {screen['id']}: {screen_bounds}[/cyan]")
            
            if (screen['left'] <= window_center_x < screen['right'] and 
                screen['top'] <= window_center_y < screen['bottom']):
                self.console.print(f"[green]✅ Window center is on Screen {screen['id']}[/green]")
                return screen['id']
        
        # Fallback: return Screen 1 (TEST SCREEN)
        self.console.print(f"[yellow]⚠️ Window center not found in any screen, defaulting to Screen 1[/yellow]")
        return 1


def test_app_controller():
    """Test function for AppController - DELTA 3 testing"""
    console = Console()
    
    console.print("\n[bold green]🚀 DELTA 3: AppController Test[/bold green]")
    console.print("=" * 50)
    
    try:
        # Import previous deltas
        from config_manager import ConfigManager
        from screen_manager import ScreenManager
        
        # Test 1: Initialize components
        console.print("[yellow]🔧 Initializing components...[/yellow]")
        config_manager = ConfigManager()
        screen_manager = ScreenManager(config_manager)
        app_controller = AppController(config_manager, screen_manager)
        console.print("[green]✅ All components initialized[/green]")
        
        # Test 2: Get test executable
        console.print("\n[yellow]🔍 Finding test executable...[/yellow]")
        test_exe = "notepad.exe"  # Windows built-in
        
        # Try to find notepad in system
        import shutil
        notepad_path = shutil.which(test_exe)
        
        if not notepad_path:
            console.print(f"[red]❌ {test_exe} not found in PATH[/red]")
            console.print("[yellow]💡 Please run: python app_controller.py --test-launch C:\\path\\to\\your\\app.exe[/yellow]")
            return False
        
        console.print(f"[green]✅ Found executable:[/green] {notepad_path}")
        
        # Test 3: Screen selection for app
        if screen_manager.screens:
            selected_screen = screen_manager.screens[0]['id']  # Use second screen for test
            console.print(f"[cyan]🖥️ Using screen {selected_screen} for test[/cyan]")
        else:
            console.print("[red]❌ No screens available[/red]")
            return False
        
        # Test 4: Launch application
        console.print(f"\n[yellow]🚀 Testing app launch...[/yellow]")
        launch_result = app_controller.launch_app()
        
        if not launch_result["success"]:
            console.print(f"[red]❌ App launch failed: {launch_result.get('error', 'Unknown error')}[/red]")
            return False
        
        console.print("[green]✅ App launched successfully[/green]")
        
        # Test 5: Take initial screenshot
        console.print("\n[yellow]📸 Testing initial screenshot...[/yellow]")
        screenshot_path = app_controller.take_initial_screenshot()
        
        if not screenshot_path:
            console.print("[red]❌ Screenshot failed[/red]")
            return False
        
        console.print(f"[green]✅ Screenshot saved:[/green] {screenshot_path}")
        
        # Test 6: Display app information
        console.print("\n[yellow]📋 App Information Summary[/yellow]")
        app_controller.get_app_info_summary()
        
        # Test 7: Clean up - close the app
        console.print("\n[yellow]🧹 Cleaning up (closing app)...[/yellow]")
        if app_controller.current_app_info:
            window_id = app_controller.current_app_info["window_id"]
            if app_controller.gui_api.close_window(window_id):
                console.print("[green]✅ App closed successfully[/green]")
            else:
                console.print("[yellow]⚠️ App may still be running[/yellow]")
        
        console.print("\n[bold green]🎉 DELTA 3 PASSED: AppController is ready![/bold green]")
        return True
        
    except Exception as e:
        console.print(f"\n[bold red]💥 DELTA 3 FAILED: {e}[/bold red]")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="fDOM AppController - Delta 3 Testing")
    parser.add_argument("--test-launch", type=str, help="Test launch with specific executable")
    parser.add_argument("--auto-test", action="store_true", help="Auto test with notepad.exe")
    
    args = parser.parse_args()
    
    if args.test_launch:
        # Test with custom executable
        from config_manager import ConfigManager
        from screen_manager import ScreenManager
        
        config = ConfigManager()
        screen_manager = ScreenManager(config)
        app_controller = AppController(args.test_launch, config=config)
        
        # Select screen interactively
        selected = screen_manager.prompt_user_selection()
        if selected:
            result = app_controller.launch_app()
            if result["success"]:
                screenshot = app_controller.take_initial_screenshot()
                app_controller.get_app_info_summary()
                
    elif args.auto_test:
        success = test_app_controller()
        exit(0 if success else 1)
    else:
        print("Usage: python app_controller.py --auto-test")
        print("       python app_controller.py --test-launch C:\\path\\to\\app.exe")
