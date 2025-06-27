"""Click execution engine with centroid strategies and verification"""
import time
import sys
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from rich.console import Console

from .interaction_types import ClickResult
from .screenshot_manager import ScreenshotManager


class ClickEngine:
    """Handles actual clicking operations with advanced strategies"""
    
    def __init__(self, app_controller, visual_differ, config):
        self.app_controller = app_controller
        self.visual_differ = visual_differ
        self.config = config
        self.console = Console()
        self.screenshot_manager = ScreenshotManager(app_controller, visual_differ)
        
    def execute_click_with_centroids(self, node_data: Dict, window_pos: Dict, 
                                   source_element_name: str) -> ClickResult:
        """Execute 3-centroid clicking strategy with verification"""
        
        # ✅ CRITICAL: Ensure window has focus before clicking
        if not self._ensure_window_has_focus():
            return ClickResult(
                success=False, 
                state_changed=False, 
                error_message="Failed to ensure window focus"
            )
        
        # Calculate adaptive centroids based on element shape
        bbox = node_data['bbox']
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        cx = (bbox[0] + bbox[2]) // 2
        cy = (bbox[1] + bbox[3]) // 2
        
        if width > height:  # Horizontal element
            centroids = [
                (cx, cy),                    # C1: Center
                (cx - width // 4, cy),       # C2: Left-center
                (cx + width // 4, cy)        # C3: Right-center
            ]
            self.console.print(f"[cyan]📐 Horizontal element ({width}x{height}) - using horizontal spread[/cyan]")
        else:  # Vertical element
            centroids = [
                (cx, cy),                    # C1: Center
                (cx, cy - height // 4),      # C2: Upper-center
                (cx, cy + height // 4)       # C3: Lower-center
            ]
            self.console.print(f"[cyan]📐 Vertical element ({width}x{height}) - using vertical spread[/cyan]")
        
        # Convert to absolute coordinates
        abs_centroids = []
        for rel_x, rel_y in centroids:
            abs_x = window_pos['left'] + rel_x
            abs_y = window_pos['top'] + rel_y
            abs_centroids.append((abs_x, abs_y))
        
        self.console.print(f"[cyan]🎯 Centroids: C1{abs_centroids[0]} C2{abs_centroids[1]} C3{abs_centroids[2]}[/cyan]")
        
        # Take before screenshot
        before_screenshot = self.screenshot_manager.take_screenshot("before_click")
        if not before_screenshot:
            return ClickResult(success=False, state_changed=False, error_message="Could not take before screenshot")
        
        before_hash = self.visual_differ.calculate_image_hash(before_screenshot)
        
        # Try each centroid
        wait_times = [2, 2, 2]
        
        for attempt, (centroid, wait_time) in enumerate(zip(abs_centroids, wait_times), 1):
            abs_x, abs_y = centroid
            
            self.console.print(f"\n[yellow]🎯 ATTEMPT {attempt}/3: Centroid C{attempt} at ({abs_x}, {abs_y})[/yellow]")
            
            success = self._attempt_single_click(abs_x, abs_y, wait_time, before_hash, before_screenshot, f"C{attempt}")
            if success:
                return ClickResult(
                    success=True,
                    state_changed=True,
                    wait_time_used=wait_time,
                    hash_before=before_hash,
                    hash_after=self._temp_after_hash,
                    after_screenshot=self._temp_after_screenshot,
                    diff_result=self._temp_diff_result
                )
            
            # Try nudging if not last attempt
            if attempt < 3:
                self.console.print(f"[yellow]🔄 C{attempt} failed, trying nudge strategy...[/yellow]")
                if self._try_nudge_strategy(abs_x, abs_y, wait_time, before_hash, before_screenshot, f"C{attempt}"):
                    return ClickResult(
                        success=True,
                        state_changed=True,
                        wait_time_used=wait_time,
                        hash_before=before_hash,
                        hash_after=self._temp_after_hash,
                        after_screenshot=self._temp_after_screenshot,
                        diff_result=self._temp_diff_result
                    )
        
        # Mark as non-interactive if all attempts failed
        return ClickResult(
            success=True,
            state_changed=False,
            interaction_type="non_interactive",
            error_message="No UI response to clicks"
        )
    
    def _ensure_window_has_focus(self) -> bool:
        """Ensure the target app window has focus before clicking"""
        try:
            if not self.app_controller.current_app_info:
                self.console.print("[red]❌ No app info available for focus[/red]")
                return False
            
            window_id = self.app_controller.current_app_info['window_id']

            if sys.platform == "darwin":
                self.console.print("[cyan]macOS detected. Activating app to focus.[/cyan]")
                # Get the window number from the window info
                window_info = self.app_controller.gui_api.get_window_info(window_id)
                if not window_info:
                    self.console.print("[red]❌ Could not get window info[/red]")
                    return False

                window_number = window_info['window_data'].get('window_number')
                if not window_number:
                    self.console.print("[red]❌ Could not get window number[/red]")
                    return False

                # Use the macOS-specific bring_to_foreground method
                success, message = self.app_controller.gui_api.controller.wm.bring_to_foreground(window_number)
                if not success:
                    self.console.print(f"[red]❌ Failed to focus window: {message}[/red]")
                    return False

                self.console.print(f"[green]✅ Window focused: {message}[/green]")
                time.sleep(1.5)  # Allow time for focus to take effect

            elif sys.platform == "win32":
                window_info = self.app_controller.gui_api.get_window_info(window_id)
                if not window_info or 'hwnd' not in window_info.get('window_data', {}):
                    self.console.print("[red]❌ Could not get window info or HWND for focus[/red]")
                    return False
                
                hwnd = window_info['window_data']['hwnd']
                focus_success, focus_message = self.app_controller.gui_api.controller.wm.smart_foreground(hwnd)
                
                if focus_success:
                    self.console.print(f"[green]🎯 Window focused successfully: {focus_message}[/green]")
                    time.sleep(2)
                else:
                    self.console.print(f"[red]❌ Smart foreground failed: {focus_message}[/red]")
                    return False
            else:
                self.console.print(f"[yellow]⚠️ Untested platform '{sys.platform}'. Skipping explicit focus.[/yellow]")

            self.console.print("[yellow]🔄 Refreshing window coordinates after focus...[/yellow]")
            self.app_controller.gui_api.refresh()
            time.sleep(0.5)
            
            fresh_window_info = self.app_controller.gui_api.get_window_info(window_id)
            
            if fresh_window_info:
                pos = fresh_window_info['window_data']['position']
                size = fresh_window_info['window_data']['size']
                self.console.print(f"[cyan]🔍 WINDOW STATE (post-focus):[/cyan]")
                self.console.print(f"   Window ID: {window_id}")
                self.console.print(f"   Position: ({pos['x']}, {pos['y']})")
                self.console.print(f"   Size: {size['width']}×{size['height']}")
                return True
            else:
                self.console.print("[red]❌ Could not get fresh window info after focus[/red]")
                return False
            
        except Exception as e:
            self.console.print(f"[red]❌ Smart focus operation failed: {e}[/red]")
            return False
    
    def _attempt_single_click(self, abs_x: int, abs_y: int, wait_time: int, 
                             before_hash: str, before_screenshot: str, label: str) -> bool:
        """Attempt a single click with timing and change detection"""
        try:
            # Move to position and click immediately (no hover wait)
            self.app_controller.gui_api.set_cursor_position(abs_x, abs_y)
            time.sleep(0.1)  # ✅ REDUCED: Minimal delay instead of 1 second hover
            
            # Click
            self.app_controller.gui_api.click(abs_x, abs_y)
            self.console.print(f"[green]✅ {label} click sent to ({abs_x}, {abs_y})[/green]")
            
            # Wait for UI response
            self.console.print(f"[yellow]⏱️ Waiting {wait_time}s for UI response...[/yellow]")
            time.sleep(wait_time)
            
            # Check for change
            after_screenshot = self.screenshot_manager.take_screenshot(f"after_{label}_wait_{wait_time}s")
            if not after_screenshot:
                return False
            
            after_hash = self.visual_differ.calculate_image_hash(after_screenshot)
            
            if before_hash != after_hash:
                self.console.print(f"[green]🎯 Hash change detected with {label} - validating visual changes...[/green]")
                
                # Validate meaningful changes
                temp_diff_path = f"temp_validation_{label}.png"
                diff_result = self.visual_differ.extract_change_regions(
                    before_screenshot, after_screenshot, temp_diff_path, (abs_x, abs_y)
                )
                
                if diff_result["success"] and diff_result.get("regions"):
                    self.console.print(f"[bold green]🎉 MEANINGFUL STATE CHANGE with {label}![/bold green]")
                    self._temp_after_screenshot = after_screenshot
                    self._temp_after_hash = after_hash
                    self._temp_diff_result = diff_result
                    return True
                else:
                    self.console.print(f"[yellow]⚠️ Hash changed but no meaningful visual regions with {label}[/yellow]")
                    self.screenshot_manager.cleanup_screenshot(after_screenshot)
                    return False
            else:
                self.console.print(f"[yellow]⚠️ No change detected with {label}[/yellow]")
                self.screenshot_manager.cleanup_screenshot(after_screenshot)
                return False
            
        except Exception as e:
            self.console.print(f"[red]❌ {label} click failed: {e}[/red]")
            return False
    
    def _try_nudge_strategy(self, abs_x: int, abs_y: int, wait_time: int, 
                           before_hash: str, before_screenshot: str, label: str) -> bool:
        """Try nudging in different directions"""
        nudge_directions = [(25, 0), (-25, 0), (0, 25), (0, -25)]
        
        for nudge_x, nudge_y in nudge_directions:
            nudge_abs_x = abs_x + nudge_x
            nudge_abs_y = abs_y + nudge_y
            
            self.console.print(f"[dim]🔄 Nudge +({nudge_x}, {nudge_y}) to ({nudge_abs_x}, {nudge_abs_y})[/dim]")
            
            try:
                # Move to nudge position
                self.app_controller.gui_api.set_cursor_position(nudge_abs_x, nudge_abs_y)
                time.sleep(0.2)
                
                # Return to centroid and click
                success = self._attempt_single_click(abs_x, abs_y, wait_time, before_hash, before_screenshot, f"{label}_nudge")
                if success:
                    return True
            except Exception as e:
                self.console.print(f"[dim]❌ Nudge failed: {e}[/dim]")
                continue
            
            break  # Only try first nudge direction
        
        return False
