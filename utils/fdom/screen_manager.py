"""
ScreenManager - Multi-screen detection and selection for fDOM Framework
Handles screen discovery, user selection, and screenshot capture using mss
"""
import mss
import os
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from rich.console import Console
from rich.table import Table
from rich.prompt import IntPrompt
from rich.panel import Panel
from rich import print as rprint
import numpy as np
from PIL import Image

class ScreenManager:
    """
    Professional multi-screen management for fDOM framework
    Handles screen detection, selection, and capture operations
    """
    
    def __init__(self, config_manager):
        """
        Initialize ScreenManager with configuration
        
        Args:
            config_manager: ConfigManager instance for settings
        """
        self.config = config_manager
        self.console = Console()
        self.screens = self._detect_screens()
        self.selected_screen = None
        
    def _detect_screens(self) -> List[Dict]:
        """
        Detect all available monitors using mss
        FIXED: Keep 'id' field for compatibility
        """
        try:
            with mss.mss() as sct:
                screens = []
                
                # Get all monitors (index 0 is combined, 1+ are individual)
                for i, monitor in enumerate(sct.monitors):
                    if i == 0:  # Skip the combined monitor
                        continue
                        
                    screen_info = {
                        'id': i,  # Keep 'id' for compatibility
                        'monitor_id': i,  # Also keep monitor_id for clarity
                        'width': monitor['width'],
                        'height': monitor['height'],
                        'left': monitor['left'],
                        'top': monitor['top'],
                        'right': monitor['left'] + monitor['width'],
                        'bottom': monitor['top'] + monitor['height'],
                        'is_primary': monitor['left'] == 0 and monitor['top'] == 0,
                        'monitor_data': monitor
                    }
                    screens.append(screen_info)
                    
                    # Clear debug output
                    primary_text = " (Primary)" if screen_info['is_primary'] else ""
                    self.console.print(f"[cyan]Monitor {i}: {monitor['width']}x{monitor['height']} at ({monitor['left']}, {monitor['top']}){primary_text}[/cyan]")
                
                return screens
                
        except Exception as e:
            self.console.print(f"[red]❌ Error detecting monitors: {e}[/red]")
            return []
    
    def test_screen_detection(self) -> bool:
        """
        Test screen detection with comprehensive output and test screenshots
        
        Returns:
            True if all tests pass, False otherwise
        """
        self.console.print("\n[bold blue]🖥️ SCREEN DETECTION TEST[/bold blue]")
        self.console.print("=" * 50)
        
        try:
            # Test 1: Screen detection
            self.console.print(f"[yellow]🔍 Detecting screens...[/yellow]")
            
            if not self.screens:
                self.console.print("[red]❌ No screens detected![/red]")
                return False
            
            self.console.print(f"[green]✅ Found {len(self.screens)} screen(s)[/green]")
            
            # Test 2: Display screen information
            self._display_screen_table()
            
            # Test 3: Take test screenshots
            screenshot_results = self._take_test_screenshots()
            
            # Test 4: Verify screenshot files
            files_created = self._verify_test_screenshots()
            
            # Summary
            all_passed = len(self.screens) > 0 and screenshot_results and files_created
            status = "[green]✅ PASSED[/green]" if all_passed else "[red]❌ FAILED[/red]"
            self.console.print(f"\n[bold]🎯 Screen Detection Test Result: {status}[/bold]")
            
            return all_passed
            
        except Exception as e:
            self.console.print(f"[red]❌ Screen detection test failed: {e}[/red]")
            return False
    
    def _display_screen_table(self) -> None:
        """Display detected screens in a beautiful table"""
        table = Table(title="🖥️ Detected Screens", show_header=True, header_style="bold magenta")
        table.add_column("Screen ID", style="cyan", width=10)
        table.add_column("Resolution", style="white", width=15)
        table.add_column("Position", style="yellow", width=20)
        table.add_column("Size (MB)", style="green", width=12)
        table.add_column("Status", justify="center", width=10)
        
        for screen in self.screens:
            # Calculate approximate screenshot size
            pixels = screen['width'] * screen['height']
            size_mb = (pixels * 3) / (1024 * 1024)  # RGB, approximate
            
            table.add_row(
                str(screen['id']),
                f"{screen['width']}×{screen['height']}",
                f"({screen['left']}, {screen['top']})",
                f"{size_mb:.1f} MB",
                "[green]✓[/green]"
            )
        
        self.console.print(table)
    
    def _take_test_screenshots(self) -> bool:
        """Take test screenshots of all detected screens"""
        self.console.print("\n[yellow]📸 Taking test screenshots...[/yellow]")
        
        try:
            with mss.mss() as sct:
                for screen in self.screens:
                    screen_id = screen['id']
                    monitor = screen['monitor_data']
                    
                    # Capture screenshot
                    screenshot = sct.grab(monitor)
                    
                    # Convert to PIL Image
                    img = Image.frombytes('RGB', screenshot.size, screenshot.bgra, 'raw', 'BGRX')
                    
                    # Save test screenshot
                    filename = f"test_screen_{screen_id}.png"
                    img.save(filename)
                    
                    self.console.print(f"  [green]✅[/green] Screen {screen_id}: {filename} ({img.size[0]}×{img.size[1]})")
                
                return True
                
        except Exception as e:
            self.console.print(f"[red]❌ Error taking screenshots: {e}[/red]")
            return False
    
    def _verify_test_screenshots(self) -> bool:
        """Verify that test screenshot files were created"""
        self.console.print("\n[yellow]🔍 Verifying test screenshot files...[/yellow]")
        
        all_files_exist = True
        total_size = 0
        
        for screen in self.screens:
            filename = f"test_screen_{screen['id']}.png"
            
            if os.path.exists(filename):
                file_size = os.path.getsize(filename)
                size_mb = file_size / (1024 * 1024)
                total_size += size_mb
                
                self.console.print(f"  [green]✅[/green] {filename}: {size_mb:.1f} MB")
            else:
                self.console.print(f"  [red]❌[/red] {filename}: File not found")
                all_files_exist = False
        
        if all_files_exist:
            self.console.print(f"[green]📊 Total screenshot data: {total_size:.1f} MB[/green]")
        
        return all_files_exist
    
    def prompt_user_selection(self) -> Optional[int]:
        """
        Interactive screen selection - DEFAULT TO SCREEN 1 (TEST SCREEN)
        """
        if not self.screens:
            self.console.print("[red]❌ No screens available for selection[/red]")
            return None
        
        # Check config for auto-selection - DEFAULT TO SCREEN 1 (TEST SCREEN)
        if not self.config.get("capture.screen_selection_prompt", True):
            default_screen = 1  # SCREEN 1 = MONITOR 1 = TEST SCREEN (1920×1080)
            if any(screen['id'] == default_screen for screen in self.screens):
                self.console.print(f"[yellow]🎯 Auto-selecting Screen {default_screen} (Monitor 1 - TEST SCREEN)[/yellow]")
                self.selected_screen = default_screen
                return default_screen
        
        # Interactive selection
        self.console.print("\n[bold cyan]🖥️ SCREEN SELECTION[/bold cyan]")
        self.console.print("Please select a screen for fDOM exploration:")
        
        # Display options
        self._display_screen_table()
        
        # Get user input
        valid_ids = [screen['id'] for screen in self.screens]
        
        try:
            selected = IntPrompt.ask(
                "\n[bold]Enter screen ID[/bold]",
                choices=[str(id) for id in valid_ids],
                default="1"  # Default to Screen 1 (TEST SCREEN)
            )
            
            self.selected_screen = selected
            
            # Show selection confirmation
            selected_screen = next(s for s in self.screens if s['id'] == selected)
            panel = Panel(
                f"Screen {selected}\n{selected_screen['width']}×{selected_screen['height']} pixels\nPosition: ({selected_screen['left']}, {selected_screen['top']})",
                title="[bold green]✅ Selected Screen[/bold green]",
                border_style="green"
            )
            self.console.print(panel)
            
            return selected
            
        except KeyboardInterrupt:
            self.console.print("\n[yellow]⚠️ Screen selection cancelled[/yellow]")
            return None
        except Exception as e:
            self.console.print(f"\n[red]❌ Error during screen selection: {e}[/red]")
            return None
    
    def capture_screen(self, screen_id: Optional[int] = None) -> Optional[np.ndarray]:
        """
        Capture screenshot of specified screen
        FIXED: Default to Screen 1 (TEST SCREEN)
        """
        target_screen_id = screen_id or self.selected_screen
        
        if target_screen_id is None:
            target_screen_id = 1  # Default to Screen 1 (TEST SCREEN)
            self.console.print(f"[yellow]📺 No screen selected, defaulting to Screen {target_screen_id} (TEST SCREEN)[/yellow]")
        
        # Find target screen
        target_screen = None
        for screen in self.screens:
            if screen['id'] == target_screen_id:
                target_screen = screen
                break
        
        if not target_screen:
            self.console.print(f"[red]❌ Screen {target_screen_id} not found[/red]")
            return None
        
        self.console.print(f"[cyan]📸 Capturing Screen {target_screen_id}: {target_screen['width']}×{target_screen['height']}[/cyan]")
        
        try:
            with mss.mss() as sct:
                # Capture screenshot
                monitor = target_screen['monitor_data']
                screenshot = sct.grab(monitor)
                
                # Convert to numpy array (BGR format for OpenCV compatibility)
                img_array = np.frombuffer(screenshot.bgra, dtype=np.uint8)
                img_array = img_array.reshape(screenshot.height, screenshot.width, 4)
                
                # Convert BGRA to BGR
                img_rgb = img_array[:, :, [0, 1, 2]]  # Remove alpha, keep RGB order
                
                return img_rgb
                
        except Exception as e:
            self.console.print(f"[red]❌ Error capturing screen {target_screen_id}: {e}[/red]")
            return None
    
    def cleanup_test_files(self) -> None:
        """Clean up test screenshot files"""
        self.console.print("\n[yellow]🧹 Cleaning up test files...[/yellow]")
        
        cleaned_count = 0
        for screen in self.screens:
            filename = f"test_screen_{screen['id']}.png"
            if os.path.exists(filename):
                os.remove(filename)
                cleaned_count += 1
                self.console.print(f"  [green]✅[/green] Removed {filename}")
        
        self.console.print(f"[green]🧹 Cleaned up {cleaned_count} test file(s)[/green]")


def test_screen_manager():
    """Test function for ScreenManager - DELTA 2 testing"""
    console = Console()
    
    console.print("\n[bold green]🚀 DELTA 2: ScreenManager Test[/bold green]")
    console.print("=" * 50)
    
    try:
        # Import ConfigManager from DELTA 1
        from config_manager import ConfigManager
        
        # Test 1: Initialize with config
        console.print("[yellow]🔧 Initializing ScreenManager...[/yellow]")
        config_manager = ConfigManager()
        screen_manager = ScreenManager(config_manager)
        console.print("[green]✅ ScreenManager initialized successfully[/green]")
        
        # Test 2: Run screen detection test
        detection_result = screen_manager.test_screen_detection()
        
        # Test 3: Test screen selection (if screens detected)
        if detection_result and screen_manager.screens:
            console.print("\n[yellow]🎯 Testing screen selection...[/yellow]")
            selected = screen_manager.prompt_user_selection()
            
            if selected:
                console.print(f"[green]✅ Screen {selected} selected successfully[/green]")
                
                # Test 4: Test screen capture
                console.print("\n[yellow]📸 Testing screen capture...[/yellow]")
                screenshot = screen_manager.capture_screen(selected)
                
                if screenshot is not None:
                    console.print(f"[green]✅ Screenshot captured: {screenshot.shape}[/green]")
                    
                    # Save a test capture
                    from PIL import Image
                    # Convert BGR to RGB for PIL
                    screenshot_rgb = screenshot[:, :, [0, 1, 2]]
                    img = Image.fromarray(screenshot_rgb)
                    img.save(f"test_capture_screen_{selected}.png")
                    console.print(f"[green]�� Saved test_capture_screen_{selected}.png[/green]")
                else:
                    console.print("[red]❌ Screen capture failed[/red]")
                    detection_result = False
        
        # Test 5: Clean up test files
        screen_manager.cleanup_test_files()
        
        # Final result
        if detection_result:
            console.print("\n[bold green]🎉 DELTA 2 PASSED: ScreenManager is ready![/bold green]")
        else:
            console.print("\n[bold red]❌ DELTA 2 FAILED: Screen detection/capture issues[/bold red]")
            
        return detection_result
        
    except Exception as e:
        console.print(f"\n[bold red]💥 DELTA 2 FAILED: {e}[/bold red]")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="fDOM ScreenManager - Delta 2 Testing")
    parser.add_argument("--test-screens", action="store_true", help="Run comprehensive screen test")
    parser.add_argument("--interactive", action="store_true", help="Run interactive screen selection")
    
    args = parser.parse_args()
    
    if args.test_screens:
        success = test_screen_manager()
        exit(0 if success else 1)
    elif args.interactive:
        from config_manager import ConfigManager
        config = ConfigManager()
        sm = ScreenManager(config)
        selected = sm.prompt_user_selection()
        print(f"Selected screen: {selected}")
    else:
        print("Usage: python screen_manager.py --test-screens")
        print("       python screen_manager.py --interactive")
