"""Screenshot capture and management"""
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from rich.console import Console
from PIL import Image
import mss


class ScreenshotManager:
    """Handles screenshot capture, storage, and cleanup"""
    
    def __init__(self, app_controller, visual_differ, debug_mode: bool = True):
        self.app_controller = app_controller
        self.visual_differ = visual_differ
        self.console = Console()
        self.debug_mode = debug_mode
        
    def take_screenshot(self, suffix: str) -> Optional[str]:
        """Take screenshot of the current app window"""
        try:
            if not self.app_controller or not self.app_controller.current_app_info:
                self.console.print("[red]❌ No app controller or app info available[/red]")
                return None
            
            # Generate custom filename with timestamp and suffix
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            custom_filename = f"interaction_{timestamp}_{suffix}.png"
            
            # Get window info
            window_id = self.app_controller.current_app_info["window_id"]
            window_info = self.app_controller.gui_api.get_window_info(window_id)
            
            if not window_info:
                self.console.print("[yellow]🔄 Window lookup failed for screenshot[/yellow]")
                return None
            
            # Create bounding box for just the window
            pos = window_info['window_data']['position']
            size = window_info['window_data']['size']
            
            window_bbox = {
                'left': pos['x'],
                'top': pos['y'], 
                'width': size['width'],
                'height': size['height']
            }
            
            # Capture window area only using mss
            with mss.mss() as sct:
                window_screenshot = sct.grab(window_bbox)
                img = Image.frombytes('RGB', window_screenshot.size, window_screenshot.bgra, 'raw', 'BGRX')
                
                # Save screenshot
                screenshots_dir = self.app_controller.current_app_info["folder_paths"]["screenshots"]
                screenshot_path = screenshots_dir / custom_filename
                img.save(screenshot_path)
                
                self.console.print(f"[green]📸 Screenshot saved: {custom_filename}[/green]")
                return str(screenshot_path)
            
        except Exception as e:
            self.console.print(f"[red]❌ Screenshot capture failed: {e}[/red]")
            return None
    
    def cleanup_screenshot(self, screenshot_path: str) -> None:
        """Delete a single screenshot file - skip in debug mode"""
        if self.debug_mode:
            self.console.print(f"[yellow]🚫 DEBUG: Keeping {os.path.basename(screenshot_path)}[/yellow]")
            return
        
        try:
            if screenshot_path and os.path.exists(screenshot_path):
                os.remove(screenshot_path)
                filename = os.path.basename(screenshot_path)
                self.console.print(f"[dim]🗑️ Cleaned temp: {filename}[/dim]")
        except Exception as e:
            self.console.print(f"[yellow]⚠️ Cleanup failed for {screenshot_path}: {e}[/yellow]")
