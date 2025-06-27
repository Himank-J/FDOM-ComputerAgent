"""ElementInteractor - Core exploration engine for fDOM Framework
Implements sophisticated click → detect → navigate strategy
"""
import json
import os
import sys
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

# ✅ ADD PATH RESOLUTION FOR DIRECT SCRIPT EXECUTION
if __name__ == "__main__":
    # Add the project root to Python path when running directly
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel as Pane
from rich.prompt import Prompt, IntPrompt
from rich import print as rprint
from PIL import Image
import numpy as np
import argparse
import psutil

# Import our framework modules
from config_manager import ConfigManager
from screen_manager import ScreenManager
from app_controller import AppController
from state_manager import StateManager
from seraphine_integrator import SeraphineIntegrator
from visual_differ import VisualDiffer

# Import modular components
from utils.fdom.interaction_types import ClickResult, BacktrackStrategy
from utils.fdom.interaction_utils import (
    sanitize_app_name, 
    sanitize_node_id_for_files
)
from utils.fdom.interactive_cli import InteractiveCLI
from utils.fdom.screenshot_manager import ScreenshotManager
from utils.fdom.state_processor import StateProcessor
from utils.fdom.navigation_engine import NavigationEngine
from utils.fdom.click_engine import ClickEngine


class ElementInteractor:
    """
    Core exploration engine implementing depth-first interaction strategy
    CLEANED: Pure orchestration - delegates to modular components
    """
    
    def __init__(self, app_executable_path: str, state_manager: Optional[StateManager] = None, app_controller: Optional[AppController] = None):
        """Initialize ElementInteractor for specific app exploration"""
        self.console = Console()
        self.app_executable_path = app_executable_path
        
        # Initialize framework components
        self.config = ConfigManager()
        self.screen_manager = ScreenManager(self.config)
        
        # ✅ LOAD TEMPLATE FILE CONFIG
        template_config = load_template_file_config()
        template_file_path = None
        
        if template_config.get('auto_load_on_launch', True):
            template_file_path = get_template_file_for_app(app_executable_path, template_config)
            
            if template_file_path:
                self.console.print(f"[yellow]🎯 Will launch with template: {os.path.basename(template_file_path)}[/yellow]")
        
        # ✅ Use AppController properly with correct constructor
        if app_controller:
            self.app_controller = app_controller
            self.console.print(f"[green]🔗 Using provided AppController instance[/green]")
        else:
            # ✅ FIXED: Use correct target screen (default to Screen 1 = TEST SCREEN)
            target_screen = self.config.get("capture.default_screen", 1)  # Screen 1 = Monitor 1 = 1920×1080
            
            self.app_controller = AppController(
                app_path=app_executable_path,
                target_screen=target_screen, 
                config=self.config,
                template_file_path=template_file_path  # ← PASS TEMPLATE FILE
            )
            
            # Set screen_manager on AppController after creation
            self.app_controller.screen_manager = self.screen_manager
            
            # ✅ PROPER APP LAUNCH using AppController
            self.console.print(f"[yellow]🚀 Launching app: {app_executable_path}[/yellow]")
            launch_result = self.app_controller.launch_app()  # ← Use launch_app() method
            
            if not launch_result["success"]:
                raise Exception(f"Failed to launch app: {launch_result.get('error', 'Unknown error')}")
            
            self.console.print(f"[green]✅ App launched successfully![/green]")
        
        # Extract app name from AppController's info
        if hasattr(self.app_controller, 'current_app_info') and self.app_controller.current_app_info:
            self.app_name = self.app_controller.current_app_info["app_name"]
        else:
            self.app_name = sanitize_app_name(Path(app_executable_path).stem)
        
        # ✅ Use StateManager with proper app name
        if state_manager:
            self.state_manager = state_manager
        else:
            self.state_manager = StateManager(self.app_name)
            self._load_existing_fdom()
        
        self.seraphine_integrator = SeraphineIntegrator(self.app_name)
        self.visual_differ = VisualDiffer(self.config)
        
        # Initialize modular components
        self.interactive_cli = InteractiveCLI(self)
        self.screenshot_manager = ScreenshotManager(self.app_controller, self.visual_differ, debug_mode=True)
        self.state_processor = StateProcessor(self.state_manager, self.seraphine_integrator, self.visual_differ)
        self.navigation_engine = NavigationEngine(self.app_controller, self.visual_differ, self.state_manager, self)
        self.click_engine = ClickEngine(self.app_controller, self.visual_differ, self.config)
        
        # Interaction settings
        self.click_offset = self.config.get("interaction.click_center_offset", 2)
        self.wait_times = [3, 5, 10]
        self.max_human_retries = 3
        self.current_state_id = "root"
        self.state_breadcrumb = ["root"]
        self.screenshot_stack = []
        self.debug_mode = True
        
        self.console.print(Pane(
            f"[bold]🎯 ElementInteractor Ready[/bold]\n\n"
            f"🎮 Strategy: Depth-first exploration\n"
            f"📱 App: {self.app_name}\n"
            f"⏱️ Wait times: {' → '.join(map(str, self.wait_times))}s\n"
            f"🎯 Click: Center + {self.click_offset}px offset\n"
            f"🔄 Backtrack: Multi-strategy with human fallback",
            title="🧠 Interaction Strategy",
            border_style="green"
        ))
        
        # ✅ FIXED: Build initial DOM only if no existing fDOM data was loaded
        if not self.state_manager.fdom_data.get("states"):
            self._build_initial_dom()
            
            # 🎯 NEW: Auto-run captioner after successful initial DOM build
            self._auto_run_captioner_on_first_launch()

    def _load_existing_fdom(self) -> None:
        """Load existing fDOM file if it exists"""
        app_dir = Path(__file__).parent.parent.parent / "apps" / self.app_name
        fdom_path = app_dir / "fdom.json"
        
        if fdom_path.exists():
            try:
                with open(fdom_path, 'r', encoding='utf-8') as f:
                    existing_fdom = json.load(f)
                
                self.state_manager.fdom_data = existing_fdom
                
                # CRITICAL: Always rebuild tracking sets after loading
                self.state_manager._rebuild_tracking_sets()
                
                # Set current state to latest state
                states = existing_fdom.get("states", {})
                if states:
                    state_ids = sorted(states.keys())
                    self.current_state_id = state_ids[-1]
                
                self.console.print(f"[green]📂 Loaded existing fDOM: {len(states)} states[/green]")
                
                # DEBUG: Show what was loaded
                self.console.print(f"[cyan]🔍 DEBUG: Loaded {len(self.state_manager.pending_nodes)} pending nodes[/cyan]")
                
            except Exception as e:
                self.console.print(f"[yellow]⚠️ Could not load existing fDOM: {e}[/yellow]")
    
    def click_element(self, node_id: str) -> Dict:
        """Execute click with comprehensive interaction workflow"""
        
        # ✅ CRITICAL: Check if app is still running BEFORE every interaction
        if not self._ensure_app_is_running():
            return {
                "success": False,
                "error_message": "App not running and restart failed",
                "state_changed": False
            }
        
        # ✅ CAPTURE BEFORE SCREENSHOT FIRST - BEFORE NAVIGATION
        before_screenshot = self.screenshot_manager.take_screenshot("before_click")
        if not before_screenshot:
            return ClickResult(success=False, state_changed=False, error_message="Could not take before screenshot")
        
        # PHASE 1: Navigation
        target_state = self._find_node_state(node_id)
        original_state = self.current_state_id
        
        if target_state and target_state != self.current_state_id:
            self.console.print(f"[cyan]🧭 Need to navigate: {self.current_state_id} → {target_state}[/cyan]")
            navigation_success = self.navigation_engine.navigate_to_state(target_state, self.current_state_id)
            if not navigation_success:
                # ✅ DON'T GIVE UP! Try backtracking first
                self.console.print(f"[yellow]⚠️ Navigation failed, attempting smart backtracking...[/yellow]")
                
                # Take current screenshot as reference for backtracking
                current_screenshot = self.screenshot_manager.take_screenshot("pre_backtrack")
                backtrack_success = self._smart_backtrack_to_state(target_state, current_screenshot)
                
                if backtrack_success:
                    self.console.print(f"[green]✅ Backtracking successful! Now in {target_state}[/green]")
                    self.current_state_id = target_state
                else:
                    self.console.print(f"[red]❌ Both navigation and backtracking failed[/red]")
                    return ClickResult(success=False, state_changed=False, error_message=f"Failed to navigate to state {target_state} - both direct navigation and backtracking failed")
            else:
                self.current_state_id = target_state
        elif target_state:
            self.console.print(f"[cyan]✅ Already in target state: {target_state}[/cyan]")
        else:
            self.console.print(f"[yellow]⚠️ Node {node_id} not found in any state, assuming current state[/yellow]")
        
        # ✅ PHASE 2: Continue with rest of logic using ORIGINAL before_screenshot
        node_data = self._find_node_in_fdom(node_id)
        if not node_data:
            return ClickResult(success=False, state_changed=False, error_message=f"Node {node_id} not found")
        
        # ✅ NEW: Check if element is enabled
        if not node_data.get('g_enabled', True):
            self.console.print(f"[yellow]⚠️ Element '{node_data.get('g_icon_name', 'unknown')}' is disabled - marking as non-interactive[/yellow]")
            self.state_manager.mark_node_explored(node_id, click_result=None, interaction_type="disabled")
            self.state_manager.save_fdom_to_file()
            return ClickResult(success=True, state_changed=False, interaction_type="disabled")
        
        window_pos = self._get_current_window_position()
        if not window_pos:
            return ClickResult(success=False, state_changed=False, error_message="Could not get window position")
        
        source_element_name = node_data.get('g_icon_name', 'unknown')
        self.console.print(f"\n[bold yellow]🎯 CLICKING ELEMENT: {node_id}[/bold yellow]")
        self.console.print(f"[cyan]📍 Target: {source_element_name}[/cyan]")
        
        # ✅ DELEGATE TO CLICK ENGINE
        click_result = self.click_engine.execute_click_with_centroids(
            node_data, window_pos, source_element_name
        )
        
        # PHASE 3: Process Results (delegate to StateProcessor)
        if click_result.success and click_result.state_changed:
            
            # 🎯 INJECTION 1: Check app closure BEFORE Seraphine processing
            if not self._verify_app_still_running():
                return self._handle_app_closure_simple(node_id, source_element_name, click_result)
            
            # 🎯 INJECTION 2: Check state reversion BEFORE Seraphine processing
            reverted_state = self._check_state_reversion(click_result.after_screenshot)
            if reverted_state:
                return self._handle_state_reversion(node_id, source_element_name, click_result, reverted_state)
            
            # Continue with existing logic - Create diff path
            diffs_dir = self.app_controller.current_app_info["folder_paths"]["diffs"]
            diffs_dir.mkdir(exist_ok=True)
            safe_node_id = sanitize_node_id_for_files(node_id)
            diff_filename = f"{self.current_state_id}_to_processing_via_{safe_node_id}.png"
            diff_path = str(diffs_dir / diff_filename)
            
            # ✅ DELEGATE TO STATE PROCESSOR - PASS PERFECT DIFF_RESULT
            new_state_name = self.state_processor.process_successful_click(
                node_id,                        # node_id: str
                source_element_name,           # source_element_name: str  
                self.current_state_id,         # current_state: str
                before_screenshot,             # before_screenshot: str
                click_result.after_screenshot, # after_screenshot: str
                diff_path,                     # diff_path: str
                click_result.diff_result       # ✅ NEW: Pass perfect diff_result from ClickEngine
            )
            
            if new_state_name:
                # State processing succeeded
                self.current_state_id = new_state_name
                click_result.new_state_id = new_state_name
                click_result.screenshot_path = diff_path
                
                self.console.print(f"[green]🎯 New state created: {new_state_name}[/green]")
                
                # ✅ PHASE 4: AUTO-CAPTIONER on updated DOM
                self.console.print(f"[bold cyan]🤖 PHASE 4: AUTO-CAPTIONER on updated DOM[/bold cyan]")
                pending_list = self.interactive_cli.show_pending_nodes_list(showTable=False)
                if pending_list:
                    self.interactive_cli._run_auto_captioner(pending_list)
                    self.console.print("[green]✅ Auto-captioner completed on new state![/green]")
                else:
                    self.console.print("[yellow]⚠️ No pending nodes found for auto-captioning[/yellow]")
                
                # ✅ PHASE 5: AUTOMATED EXPLORATION - Always auto-backtrack for systematic exploration
                if original_state != self.current_state_id:
                    self.console.print(f"[bold blue]🔄 AUTO-BACKTRACK: Systematic exploration, returning to {original_state}[/bold blue]")
                    
                    # ✅ FIXED: Use BEFORE screenshot as reference, not AFTER
                    self.console.print(f"[dim]🔍 DEBUG: Using reference screenshot: {before_screenshot}[/dim]")
                    backtrack_success = self._smart_backtrack_to_state(original_state, before_screenshot)
                    
                    if backtrack_success:
                        self.current_state_id = original_state
                        self.console.print(f"[green]✅ Smart backtrack successful[/green]")
                    else:
                        self.console.print(f"[red]❌ Smart backtrack failed - manual intervention may be needed[/red]")
                
                return click_result
            else:
                # State processing failed
                click_result.success = False
                click_result.state_changed = False
                click_result.error_message = "State processing failed"
                self.console.print(f"[red]❌ State processing failed[/red]")
            
            # Cleanup
            if not self.debug_mode:
                self.screenshot_manager.cleanup_screenshot(before_screenshot)
                self.screenshot_manager.cleanup_screenshot(click_result.after_screenshot)
            
            return click_result
        elif click_result.success and not click_result.state_changed:
            # Non-interactive element
            self.state_manager.mark_node_explored(node_id, click_result=None, interaction_type="non_interactive")
            self.state_manager.save_fdom_to_file()
            return click_result
        else:
            # Click execution failed
            return click_result

    def navigate_back_to_state(self, target_state_id: str, failure_reference_screenshot: str = None) -> bool:
        """CLEANED: Delegate to NavigationEngine"""
        return self.navigation_engine.navigate_back_to_state(target_state_id, failure_reference_screenshot)

    # =====================================================================
    # CORE UTILITY METHODS (Keep - these are essential orchestration)
    # =====================================================================

    def _find_node_in_fdom(self, node_id: str) -> Optional[Dict]:
        """Find node data in fDOM - handles both state::node_id and old format"""
        # NEW FORMAT: state::node_id
        if "::" in node_id:
            state_name, actual_node_id = node_id.split("::", 1)
            state_data = self.state_manager.fdom_data.get("states", {}).get(state_name, {})
            return state_data.get("nodes", {}).get(actual_node_id)
        
        # OLD FORMAT: search all states (fallback)
        for state_data in self.state_manager.fdom_data.get("states", {}).values():
            nodes = state_data.get("nodes", {})
            if node_id in nodes:
                return nodes[node_id]
        return None

    def _get_current_window_position(self) -> Optional[Dict]:
        """Get current app window position on screen"""
        try:
            if not self.app_controller.current_app_info:
                self.console.print("[red]❌ No app currently tracked[/red]")
                return None
            
            window_id = self.app_controller.current_app_info['window_id']
            window_info = self.app_controller.gui_api.get_window_info(window_id)
            
            if window_info:
                pos = window_info['window_data']['position']
                return {
                    'left': pos['x'],
                    'top': pos['y'],
                    'width': window_info['window_data']['size']['width'],
                    'height': window_info['window_data']['size']['height']
                }
            else:
                self.console.print("[red]❌ Could not get window position info[/red]")
                return None
            
        except Exception as e:
            self.console.print(f"[red]❌ Window position detection failed: {e}[/red]")
            return None

    def _find_node_state(self, unique_node_id: str) -> Optional[str]:
        """Find which state contains the node - handle state::node_id format"""
        # NEW FORMAT: state::node_id
        if "::" in unique_node_id:
            state_name, node_id = unique_node_id.split("::", 1)
            # Verify the node exists in that state
            state_data = self.state_manager.fdom_data.get("states", {}).get(state_name, {})
            if node_id in state_data.get("nodes", {}):
                return state_name
            return None
        
        # OLD FORMAT: search all states (fallback)
        for state_id, state_data in self.state_manager.fdom_data.get("states", {}).items():
            if unique_node_id in state_data.get("nodes", {}):
                return state_id
        return None

    # =====================================================================
    # INTERACTIVE MODE (Delegate to InteractiveCLI)
    # =====================================================================

    def interactive_exploration_mode(self) -> None:
        """CLEANED: Delegate to InteractiveCLI"""
        self.interactive_cli.run_interactive_mode()

    def _build_initial_dom(self):
        """Build initial DOM using AppController's screenshot and Seraphine"""
        self.console.print(f"[yellow]🏗️ Building initial DOM for {self.app_name}...[/yellow]")
        time.sleep(2)
        
        # ✅ Use AppController's screenshot method
        initial_screenshot = self.app_controller.take_initial_screenshot()
        
        if not initial_screenshot:
            self.console.print("[red]❌ Failed to take initial screenshot[/red]")
            return
        
        self.console.print(f"[green]✅ Initial screenshot: {initial_screenshot}[/green]")
        
        # ✅ FIXED: Use correct method name with only screenshot_path parameter
        initial_state = self.state_manager.create_initial_fdom_state(initial_screenshot)
        
        if initial_state and initial_state.get("nodes"):
            self.console.print(f"[green]✅ Initial DOM created with {len(self.state_manager.pending_nodes)} nodes[/green]")
        else:
            self.console.print(f"[red]❌ Initial state creation failed or returned no nodes[/red]")

    def _smart_backtrack_to_state(self, target_state: str, reference_screenshot: str) -> bool:
        """Smart 4-step backtracking for automated exploration"""
        return self.navigation_engine.smart_backtrack_to_state(target_state, reference_screenshot)

    def _ensure_app_is_running(self) -> bool:
        """Ensure app is running, restart if needed"""
        try:
            if not self.app_controller.current_app_info:
                self.console.print(f"[yellow]⚠️ No app info - attempting restart...[/yellow]")
                return self._restart_app_for_exploration()
            
            window_id = self.app_controller.current_app_info['window_id']
            window_info = self.app_controller.gui_api.get_window_info(window_id)
            
            if window_info is None:
                self.console.print(f"[yellow]⚠️ App window not found - restarting app...[/yellow]")
                return self._restart_app_for_exploration()
            
            return True
            
        except Exception as e:
            self.console.print(f"[red]❌ Error checking app status: {e}[/red]")
            return self._restart_app_for_exploration()

    def _restart_app_for_exploration(self) -> bool:
        """Restart app without running Seraphine (fDOM exists)"""
        try:
            launch_result = self.app_controller.launch_app()
            
            if launch_result["success"]:
                self.console.print(f"[green]✅ App restarted successfully[/green]")
                
                # ✅ CRITICAL FIX: Refresh coordinates after restart
                self.console.print(f"[yellow]🔄 Refreshing window coordinates after restart...[/yellow]")
                
                # Force complete refresh of window API
                self.app_controller.gui_api.refresh()
                time.sleep(0.5)
                
                # Get fresh window info...
                window_id = self.app_controller.current_app_info['window_id']
                window_info = self.app_controller.gui_api.get_window_info(window_id)
                
                if window_info:
                    pos = window_info['window_data']['position']
                    size = window_info['window_data']['size']
                    self.console.print(f"[green]🔍 Fresh coordinates after restart: ({pos['x']}, {pos['y']}) size {size['width']}×{size['height']}[/green]")
                
                time.sleep(2)  # Wait for app to be ready
                return True
            else:
                self.console.print(f"[red]❌ App restart failed: {launch_result.get('error')}[/red]")
                return False
            
        except Exception as e:
            self.console.print(f"[red]❌ Exception during app restart: {e}[/red]")
            return False

    def _handle_app_closure_simple(self, node_id: str, element_name: str, click_result: Dict) -> Dict:
        """Simple app closure handler - no Seraphine, no auto-backtrack"""
        self.console.print(f"[yellow]🚪 App closed by: {element_name}[/yellow]")
        
        # Mark as explored with closes_app type
        self.state_manager.mark_node_explored(
            node_id, 
            click_result="app_closed", 
            interaction_type="closes_app"
        )
        self.state_manager.save_fdom_to_file()
        
        # Restart app
        self.console.print(f"[cyan]🔄 Restarting app for continued exploration...[/cyan]")
        restart_success = self._restart_app_for_exploration()
        
        # Update click result
        click_result.success = restart_success
        click_result.state_changed = False
        click_result.app_closed = True
        click_result.message = f"App closed by {element_name}, restarted successfully" if restart_success else f"App closed by {element_name} but restart failed"
        
        if restart_success:
            self.console.print(f"[green]✅ App restarted - ready to continue exploration[/green]")
        else:
            self.console.print(f"[red]❌ App restart failed[/red]")
        
        return click_result

    def _verify_app_still_running(self) -> bool:
        """SIMPLE: Check if app process is still running"""
        try:
            # Get app name from executable path
            app_name = Path(self.app_executable_path).stem.lower()
            
            # Check if process exists
            for proc in psutil.process_iter(['pid', 'name']):
                if proc.info['name'] and app_name in proc.info['name'].lower():
                    self.console.print(f"[dim]🔍 App running check: YES (process found)[/dim]")
                    return True
            
            self.console.print(f"[dim]🔍 App closure detected: No {app_name} process[/dim]")
            return False
            
        except Exception as e:
            self.console.print(f"[yellow]⚠️ Process check failed: {e}[/yellow]")
            # Fallback to window check
            try:
                window_pos = self._get_current_window_position()
                return window_pos is not None
            except:
                return False

    def _check_state_reversion(self, current_screenshot: str) -> Optional[str]:
        """Check if current UI matches any known previous state"""
        
        # Get all known states to check against
        known_states = self.state_manager.fdom_data.get("states", {})
        
        # Priority order: Check navigation chain states first, then all others
        check_order = []
        
        # 1. Add navigation chain states (most likely to match)
        for nav_step in reversed(self.navigation_engine.navigation_chain):
            from_state = nav_step.get('from_state')
            if from_state and from_state not in check_order:
                check_order.append(from_state)
        
        # 2. Add root state (very common for cancel actions)
        if "root" not in check_order:
            check_order.append("root")
        
        # 3. Add any other states
        for state_id in known_states:
            if state_id not in check_order:
                check_order.append(state_id)
        
        self.console.print(f"[cyan]🔍 Checking state reversion against: {check_order[:5]}{'...' if len(check_order) > 5 else ''}[/cyan]")
        
        # Check similarity against each state
        for state_id in check_order:
            state_data = known_states.get(state_id, {})
            state_image = state_data.get("image")
            
            if state_image and Path(state_image).exists():
                similarity = self.visual_differ.calculate_similarity_percentage(
                    current_screenshot, state_image
                )
                
                self.console.print(f"[dim]📊 {state_id}: {similarity}%[/dim]")
                
                # ✅ STRICT: 99.99% threshold for state reversion
                if similarity >= 99.99:
                    self.console.print(f"[green]🔄 State reversion detected: → {state_id} ({similarity}%)[/green]")
                    return state_id
        
        self.console.print(f"[dim]❌ No state reversion detected[/dim]")
        return None

    def _handle_state_reversion(self, node_id: str, element_name: str, click_result: Dict, reverted_state: str) -> Dict:
        """Handle UI reversion to known state - no Seraphine needed"""
        self.console.print(f"[yellow]🔄 State reversion: {element_name} → {reverted_state}[/yellow]")
        
        # Mark as explored with reversion type
        self.state_manager.mark_node_explored(
            node_id, 
            click_result=f"reverted_to_{reverted_state}", 
            interaction_type="state_reversion"
        )
        self.state_manager.save_fdom_to_file()
        
        # Update current state
        original_state = self.current_state_id
        self.current_state_id = reverted_state
        
        # Update navigation chain (remove states after the reverted state)
        self._update_navigation_chain_for_reversion(reverted_state)
        
        # Update click result
        click_result.success = True
        click_result.state_changed = True
        click_result.state_reversion = True
        click_result.reverted_to = reverted_state
        click_result.message = f"{element_name} reverted UI to {reverted_state}"
        
        self.console.print(f"[green]✅ State reversion handled: {original_state} → {reverted_state}[/green]")
        self.console.print(f"[green]✅ Skipped Seraphine analysis (state already known)[/green]")
        
        return click_result

    def _update_navigation_chain_for_reversion(self, reverted_state: str):
        """Update navigation chain when UI reverts to a previous state"""
        # Find the position of reverted_state in navigation chain
        chain = self.navigation_engine.navigation_chain
        
        # Remove navigation steps that are no longer valid
        for i in range(len(chain) - 1, -1, -1):
            if chain[i]['to_state'] == reverted_state:
                # Keep up to this point
                self.navigation_engine.navigation_chain = chain[:i+1]
                self.console.print(f"[dim]🔗 Navigation chain updated: {len(self.navigation_engine.navigation_chain)} steps[/dim]")
                return
        
        # If reverted to root or a state not in chain, clear the chain
        if reverted_state == "root":
            self.navigation_engine.navigation_chain.clear()
            self.console.print(f"[dim]🔗 Navigation chain cleared (reverted to root)[/dim]")

    def _auto_run_captioner_on_first_launch(self) -> None:
        """Automatically run auto-captioner after first-time DOM build"""
        try:
            # Check if initial DOM build was successful
            if not self.state_manager.fdom_data.get("states") or not self.state_manager.pending_nodes:
                self.console.print("[yellow]⚠️ Skipping auto-captioner: No DOM data or pending nodes[/yellow]")
                return
            
            self.console.print(Pane(
                "[bold green]🤖 AUTO-CAPTIONER STARTING[/bold green]\n\n"
                "First-time launch detected - automatically discovering element captions.\n"
                "This will help improve element identification accuracy.",
                title="🎯 Automatic Caption Discovery",
                border_style="green"
            ))
            
            # ✅ CLEANEST: Use the same pattern as interactive CLI
            pending_list = self.interactive_cli.show_pending_nodes_list(showTable=False)
            
            if pending_list:
                self.interactive_cli._run_auto_captioner(pending_list)
                self.console.print("[green]✅ Auto-captioner completed! Element captions discovered.[/green]")
            else:
                self.console.print("[yellow]⚠️ No pending nodes found for auto-captioning[/yellow]")
            
        except Exception as e:
            self.console.print(f"[red]❌ Auto-captioner failed: {e}[/red]")
            self.console.print("[yellow]💡 You can manually run it later using option '0' in interactive mode[/yellow]")
            
    def raw_click_node(self, node_id, state_id=None):
        """
        Directly click a node using GUI API, NO focus/minimize/maximize, NO screenshot, NO analysis.
        """
        if state_id is None:
            state_id = self.current_state_id
        state = self.state_manager.fdom_data.get("states", {}).get(state_id, {})
        node_data = state.get("nodes", {}).get(node_id)
        if not node_data:
            self.console.print(f"[red]Node {node_id} not found in state {state_id}![/red]")
            return
        window_pos = self._get_current_window_position()
        if not window_pos:
            self.console.print("[red]Could not get window position![/red]")
            return
        bbox = node_data.get('bbox', [0, 0, 0, 0])
        # Support both [x1, y1, x2, y2] and [x, y, w, h]
        if len(bbox) == 4 and bbox[2] > bbox[0] and bbox[3] > bbox[1]:
            # [x1, y1, x2, y2]
            x = window_pos['left'] + (bbox[0] + bbox[2]) // 2
            y = window_pos['top'] + (bbox[1] + bbox[3]) // 2
        else:
            # fallback: [x, y, w, h]
            x = window_pos['left'] + bbox[0] + bbox[2] // 2
            y = window_pos['top'] + bbox[1] + bbox[3] // 2
        self.console.print(f"[bold yellow]RAW CLICK (no focus): {node_id} ({node_data.get('g_icon_name', '')}) at ({x}, {y}) in state {state_id}[/bold yellow]")
        self.app_controller.gui_api.click(x, y)
        time.sleep(0.5)

    def manual_persistent_click_mode(self):
        """
        Smart manual persistent click mode: show all nodes from all states, let user pick index, auto-navigate if needed, click, repeat.
        All clicks are direct, no focus/minimize/maximize, no screenshot, no fDOM update.
        """
        all_states = self.state_manager.fdom_data.get("states", {})
        all_edges = self.state_manager.fdom_data.get("edges", [])
        all_nodes = []
        node_to_state = {}

        def collect_nodes(state_id, node_id, data, level=0):
            icon_name = data.get("g_icon_name", "")
            if icon_name != "unanalyzed":
                all_nodes.append((state_id, node_id, data, level))
                node_to_state[node_id] = state_id
            for child_id, child_data in data.get("children", {}).items():
                collect_nodes(state_id, child_id, child_data, level + 1)

        for state_id, state in all_states.items():
            nodes = state.get("nodes", {})
            for node_id, data in nodes.items():
                collect_nodes(state_id, node_id, data)

        node_list = [(i, state_id, node_id, data, level) for i, (state_id, node_id, data, level) in enumerate(all_nodes)]

        if not node_list:
            self.console.print("[red]No valid nodes found in any state![/red]")
            return

        def find_path_via_edges(from_state, to_state):
            from collections import deque, defaultdict
            graph = defaultdict(list)
            for edge in all_edges:
                graph[edge['from']].append(edge)
            queue = deque([(from_state, [])])
            visited = set()
            while queue:
                state, path = queue.popleft()
                if state == to_state:
                    return path
                if state in visited:
                    continue
                visited.add(state)
                for edge in graph.get(state, []):
                    queue.append((edge['to'], path + [edge]))
            return None

        while True:
            table = Table(title="Manual Clickable Nodes (All States, Smart Navigation, NO FOCUS)")
            table.add_column("Index", style="cyan")
            table.add_column("State", style="magenta")
            table.add_column("Node ID", style="magenta")
            table.add_column("Icon Name", style="green")
            table.add_column("Brief", style="blue")
            table.add_column("Type", style="yellow")
            for idx, state_id, node_id, data, level in node_list:
                indent = "  " * level
                icon_name = data.get("g_icon_name", "")
                brief = data.get("g_brief", "")
                node_type = data.get("g_type", "")
                table.add_row(str(idx), state_id, f"{indent}{node_id}", icon_name, brief, node_type)
            self.console.print(table)

            try:
                idx = IntPrompt.ask("Enter index to click (or blank to exit)", default=None)
            except Exception:
                break
            if idx is None or not str(idx).isdigit():
                break
            idx = int(idx)
            if idx < 0 or idx >= len(node_list):
                self.console.print("[yellow]Invalid index![/yellow]")
                continue

            target_state_id, node_id, node_data, level = node_list[idx][1:]
            base_state = "root"  # or whatever your true base state is

            # Always start navigation from base_state
            nav_state = base_state
            if nav_state != target_state_id:
                path = find_path_via_edges(nav_state, target_state_id)
                if not path:
                    self.console.print(f"[red]No navigation path from {nav_state} to {target_state_id}![/red]")
                    continue
                self.console.print(f"[cyan]Navigating from {nav_state} to {target_state_id}...[/cyan]")
                for edge in path:
                    trigger_node = edge.get('trigger_node')
                    if not trigger_node:
                        action = edge.get('action', '')
                        if action.startswith('click:'):
                            trigger_node = action.split('click:')[1]
                    if not trigger_node:
                        self.console.print(f"[red]Edge missing trigger_node and action: {edge}![/red]")
                        break
                    self.console.print(f"[blue]RAW clicking navigation node: {trigger_node} to reach {edge['to']}[/blue]")
                    self.raw_click_node(trigger_node, state_id=edge['from'])
                    time.sleep(1)
                    nav_state = edge['to']

            # Now in the correct state, click the node (NO FOCUS LOGIC)
            self.raw_click_node(node_id, state_id=target_state_id)

def load_template_file_config(config_path: str = "utils/fdom/fdom_config.json") -> dict:
    """Load template file configuration from fdom_config.json"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config.get('template_files', {})
    except Exception as e:
        print(f"⚠️ Could not load template file config: {e}")
        return {}

def get_template_file_for_app(app_path: str, template_config: dict) -> str:
    """Get the appropriate template file for the given app"""
    if not template_config.get('enabled', False):
        return None
    
    # Extract executable name from full path
    app_exe = os.path.basename(app_path).upper()
    
    # Look up in app mappings (case-insensitive)
    app_mappings = template_config.get('app_mappings', {})
    
    # ✅ MAKE CASE-INSENSITIVE LOOKUP
    matching_key = None
    for key in app_mappings.keys():
        if key.upper() == app_exe:
            matching_key = key
            break
    
    if matching_key:
        template_info = app_mappings[matching_key]
        template_filename = template_info['template_file']
        
        # Build full path to template file
        base_dir = template_config.get('base_directory', 'utils/fdom/template_files')
        template_path = os.path.join(base_dir, template_filename)
        
        # Verify file exists
        if os.path.exists(template_path):
            print(f"📄 Found template file for {app_exe}: {template_filename}")
            print(f"   Type: {template_info.get('file_type', 'Unknown')}")
            return os.path.abspath(template_path)
        else:
            print(f"⚠️ Template file not found: {template_path}")
    else:
        print(f"ℹ️ No template mapping found for: {app_exe}")
    
    # Handle fallback behavior
    fallback = template_config.get('fallback_behavior', {})
    if fallback.get('show_warning', True):
        print(f"⚠️ No template file configured for {app_exe}")
    
    return None

def main():
    """Enhanced CLI with interactive node selection"""
    parser = argparse.ArgumentParser(description="Enhanced fDOM Element Interaction")
    parser.add_argument("--app-name", default="notepad", help="App to test")
    parser.add_argument("--click-node", help="Specific node to click")
    parser.add_argument("--interactive", action="store_true", help="Interactive node selection mode")
    parser.add_argument("--list-pending", action="store_true", help="Just list pending nodes")
    parser.add_argument("--manual-click", action="store_true", help="Manual persistent click mode (no fdom update, no screenshots)")

    args = parser.parse_args()

    interactor = ElementInteractor(args.app_name)

    if args.list_pending:
        interactor.interactive_cli.show_pending_nodes_list()
        return

    if args.manual_click:
        interactor.manual_persistent_click_mode()
        return

    if args.interactive:
        print("🚀 STARTING INTERACTIVE EXPLORATION")
        print("=" * 60)
        print("✅ App already launched and DOM built during initialization")
        print("✅ Auto-captioner completed")
        print("🎯 Starting interactive exploration mode...")
        interactor.interactive_exploration_mode()
        return

    if args.click_node:
        result = interactor.click_element(args.click_node)
        print(f"Result: {result}")
        return

    print("Use --interactive for manual node selection")
    print("Use --list-pending to see available nodes")
    print("Use --click-node <node_id> to test specific node")
    print("Use --manual-click for persistent manual click mode")


if __name__ == "__main__":
    main() 