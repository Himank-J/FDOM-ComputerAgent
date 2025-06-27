"""
FDOMCreator - Main orchestrator for the fDOM Framework
Integrates all modules into a single cohesive exploration service
"""
import json
import argparse
from pathlib import Path
from typing import Dict, Optional
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

# Import all our modules
from config_manager import ConfigManager
from screen_manager import ScreenManager  
from app_controller import AppController
from state_manager import StateManager
from element_interactor import ElementInteractor

class FDOMCreator:
    """
    Main orchestrator for fDOM exploration
    Coordinates all modules with centralized state management
    """
    
    def __init__(self):
        self.console = Console()
        
        # SINGLE config load point
        self.config_manager = ConfigManager()  # Loads fdom_config.json
        self.config = self.config_manager.config  # Direct access to all settings
        
        # Pass config to ALL modules
        self.screen_manager = ScreenManager(self.config_manager)
        self.app_controller = AppController(self.config_manager, self.screen_manager)
        
        # App-specific modules (initialized when app is set)
        self.state_manager = None
        self.element_interactor = None
        
        # Centralized state
        self.current_app_name = None
        self.exploration_active = False
        
        # CENTRALIZED path management
        self.project_root = Path(__file__).parent.parent.parent
        self.apps_base_dir = self.project_root / "apps"  # ROOT LEVEL
        
        # All modules use THESE paths, not their own
        self.app_controller.apps_base_dir = self.apps_base_dir  # Override
        
    def create_fdom_for_app(self, executable_path: str) -> Dict:
        """Complete fDOM creation workflow with smart detection"""
        
        try:
            # STEP 1: Screen Selection
            screen_id = self._handle_screen_selection()
            if not screen_id:
                return {"success": False, "error": "Screen selection failed"}
            
            # STEP 2: Launch Application  
            app_result = self._launch_application(executable_path, screen_id)
            if not app_result["success"]:
                return app_result
            
            # STEP 3: Initialize App-Specific Modules (loads existing fDOM if present)
            if not self._initialize_app_modules():
                return {"success": False, "error": "Module initialization failed"}
            
            # STEP 4: CONDITIONAL - Create Initial fDOM only if needed
            initial_state = None
            if len(self.state_manager.fdom_data.get("states", {})) == 0:
                # Fresh run - create initial fDOM
                self.console.print(f"[yellow]🆕 Fresh session detected - creating initial fDOM[/yellow]")
                initial_state = self._create_initial_fdom()
                if not initial_state["success"]:
                    return initial_state
            else:
                # Existing data - skip Step 4
                self.console.print(f"[green]♻️ Existing session detected - skipping fDOM creation[/green]")
                initial_state = {"success": True, "mode": "resumed"}
            
            # STEP 5: Start Exploration Loop
            exploration_result = self._start_exploration_loop()
            
            return {
                "success": True,
                "app_name": self.current_app_name,
                "initial_state": initial_state,
                "exploration_result": exploration_result
            }
            
        except Exception as e:
            self.console.print(f"[red]❌ Error in fDOM creation: {e}[/red]")
            return {"success": False, "error": str(e)}
    
    def _handle_screen_selection(self) -> Optional[int]:
        """Centralized screen selection - used by ALL modules"""
        
        # Check config for auto-selection
        auto_select = not self.config.get("capture.screen_selection_prompt", True)
        default_screen = self.config.get("capture.default_screen", 1)
        
        if auto_select:
            self.selected_screen_id = default_screen
            self.console.print(f"[green]📺 Auto-selected Screen {default_screen} from config[/green]")
        else:
            self.selected_screen_id = self.screen_manager.prompt_user_selection()
        
        # STORE for all modules to use
        self.screen_id = self.selected_screen_id
        return self.selected_screen_id
    
    def _launch_application(self, executable_path: str, screen_id: int) -> Dict:
        """Launch application and take initial screenshot"""
        self.console.print(f"\n[bold yellow]🚀 STEP 2: LAUNCHING APPLICATION[/bold yellow]")
        
        # Launch with app_controller
        launch_result = self.app_controller.launch_app_for_exploration(executable_path, screen_id)
        
        if launch_result["success"]:
            self.current_app_name = launch_result["app_info"]["app_name"]
            
            # Take initial screenshot using app_controller's method (app-only)
            screenshot_path = self.app_controller.take_initial_screenshot()
            
            if screenshot_path:
                self.console.print(f"[green]✅ Initial screenshot: {screenshot_path}[/green]")
                return {"success": True, "screenshot_path": screenshot_path}
            else:
                return {"success": False, "error": "Failed to take initial screenshot"}
        
        return launch_result
    
    def _initialize_app_modules(self) -> bool:
        """Initialize ALL modules with centralized state"""
        
        # Initialize StateManager first
        self.state_manager = StateManager(app_name=self.current_app_name)
        
        # Check for existing fDOM data
        fdom_file = self.apps_base_dir / self.current_app_name / "fdom.json"
        if fdom_file.exists():
            try:
                with open(fdom_file, 'r', encoding='utf-8') as f:
                    existing_fdom = json.load(f)
                
                self.state_manager.fdom_data = existing_fdom
                self.state_manager._rebuild_tracking_sets()
                
                states_count = len(existing_fdom.get('states', {}))
                pending_count = len(self.state_manager.pending_nodes)
                
                self.console.print(f"[green]📂 Loaded existing fDOM: {states_count} states[/green]")
                self.console.print(f"[green]🔄 Restored: {pending_count} pending nodes[/green]")
                
            except Exception as e:
                self.console.print(f"[yellow]⚠️ Could not load existing fDOM: {e}[/yellow]")
        else:
            self.console.print("[cyan]🆕 Fresh session - no existing fDOM found[/cyan]")
        
        # Initialize ElementInteractor with loaded StateManager
        self.element_interactor = ElementInteractor(
            app_name=self.current_app_name,
            state_manager=self.state_manager,
            app_controller=self.app_controller
        )
        
        return True
    
    def _create_initial_fdom(self) -> Dict:
        """Create initial fDOM from screenshot"""
        self.console.print(f"\n[bold yellow]📊 STEP 4: CREATE INITIAL FDOM[/bold yellow]")
        
        # Get the screenshot path using centralized apps_base_dir
        initial_screenshot = self.apps_base_dir / self.current_app_name / "screenshots" / "S001.png"
        
        if not initial_screenshot.exists():
            return {"success": False, "error": "Initial screenshot not found"}
        
        # Use state_manager to create fDOM (this calls seraphine internally)
        state_data = self.state_manager.create_initial_fdom_state(str(initial_screenshot))
        
        if state_data:
            # CRITICAL FIX: Save fDOM to JSON file
            fdom_file_path = self.state_manager.save_fdom_to_file()
            self.console.print(f"[green]💾 fDOM saved to: {fdom_file_path}[/green]")
            
            return {"success": True, "state_data": state_data, "fdom_file": fdom_file_path}
        else:
            return {"success": False, "error": "fDOM creation failed"}
    
    def _start_exploration_loop(self) -> Dict:
        """Start the interactive exploration loop WITH USER CHOICE"""
        self.console.print(f"\n[bold yellow]🎯 STEP 5: START EXPLORATION[/bold yellow]")
        
        # Display current exploration status
        self.state_manager.display_exploration_status()
        
        exploration_results = []
        self.exploration_active = True
        
        while self.exploration_active:
            # 🎯 NEW: Let user select which node to test
            next_node = self._interactive_node_selection()
            
            if not next_node:
                self.console.print("[yellow]🛑 Exploration stopped by user[/yellow]")
                break
            
            # Test the selected node
            self.console.print(f"\n[bold yellow]🎯 Testing: {next_node}[/bold yellow]")
            click_result = self.element_interactor.click_element(next_node)
            exploration_results.append({
                "node": next_node,
                "result": click_result
            })
            
            # Display result
            if click_result.success and click_result.state_changed:
                self.console.print(f"[green]✅ {next_node}: State changed → {click_result.new_state_id}[/green]")
            elif click_result.success:
                self.console.print(f"[yellow]⚪ {next_node}: No state change (non-interactive)[/yellow]")
            else:
                self.console.print(f"[red]❌ {next_node}: Failed - {click_result.error_message}[/red]")
        
        return {"nodes_explored": len(exploration_results), "results": exploration_results}

    def _interactive_node_selection(self) -> Optional[str]:
        """Let user choose which pending node to test"""
        
        # ✅ FIX: ALWAYS reload from JSON before showing selection
        self._force_reload_fdom_from_file()
        
        if not self.state_manager.pending_nodes:
            self.console.print("[green]✅ No pending nodes - all explored![/green]")
            return None
        
        # Collect all pending nodes with details
        pending_list = []
        for node_id in sorted(self.state_manager.pending_nodes):
            node_data = self._find_node_in_fdom(node_id)
            if node_data:
                state_id = self._find_node_state(node_id)
                pending_list.append({
                    'id': node_id,
                    'name': node_data.get('g_icon_name', 'Unknown'),
                    'type': node_data.get('type', 'unknown'),
                    'state': state_id or 'unknown'
                })
        
        # Display options
        self.console.print(f"\n[bold blue]📋 PENDING NODES ({len(pending_list)} total)[/bold blue]")
        for i, node in enumerate(pending_list, 1):
            state_display = node['state'].replace('_', '>') if node['state'] != 'unknown' else 'unknown'
            self.console.print(f"[white]{i:2d}. {node['id']} - {node['name']} ({node['type']}) - State: {state_display}[/white]")
        
        # Simple comma-separated list
        node_ids = [node['id'] for node in pending_list]
        self.console.print(f"\n[dim]Simple list: {', '.join(node_ids)}[/dim]")
        
        # Enhanced prompt
        self.console.print(Panel(
            f"[bold]Choose a node to test:[/bold]\n\n"
            f"• Enter number (1-{len(pending_list)})\n"
            f"• Enter node ID directly (e.g., H1_2)\n"
            f"• Enter 'skip' to manually describe\n"
            f"• Enter 'exit' to stop exploration",
            title="🎯 Node Selection",
            border_style="cyan"
        ))
        
        user_input = Prompt.ask("Your choice").strip()
        
        if user_input.lower() == 'exit':
            return None
        
        if user_input.lower() == 'skip':
            # Let user select which node to skip
            skip_choice = Prompt.ask(f"Which node to skip? (1-{len(pending_list)} or node_id)")
            selected_node = self._parse_node_choice(skip_choice, pending_list, node_ids)
            if selected_node:
                self._handle_manual_skip(selected_node)
            return self._interactive_node_selection()  # Recurse to show menu again
        
        # Parse the selection
        return self._parse_node_choice(user_input, pending_list, node_ids)

    def _parse_node_choice(self, user_input: str, pending_list: list, node_ids: list) -> Optional[str]:
        """Parse user input and return selected node_id"""
        try:
            choice_num = int(user_input)
            if 1 <= choice_num <= len(pending_list):
                selected_node = pending_list[choice_num - 1]['id']
                self.console.print(f"[green]✅ Selected: {selected_node}[/green]")
                return selected_node
            else:
                self.console.print(f"[red]❌ Invalid number. Please choose 1-{len(pending_list)}[/red]")
                return None
        except ValueError:
            # Try as direct node ID
            if user_input in node_ids:
                self.console.print(f"[green]✅ Selected: {user_input}[/green]")
                return user_input
            else:
                self.console.print(f"[red]❌ Invalid choice. Available: {', '.join(node_ids)}[/red]")
                return None

    def _handle_manual_skip(self, node_id: str):
        """Handle manual skip with description"""
        custom_description = Prompt.ask(
            f"[blue]Describe {node_id}[/blue] (e.g., 'closes app', 'opens file menu')"
        )
        
        self.state_manager.mark_node_explored(
            node_id, 
            click_result=None,
            interaction_type="manual_skip"
        )
        
        self._add_manual_description(node_id, custom_description)
        self.state_manager.save_fdom_to_file()
        
        self.console.print(f"[blue]📝 {node_id}: Skipped - '{custom_description}'[/blue]")

    def _find_node_in_fdom(self, unique_node_id: str) -> Optional[Dict]:
        """Find node data using state::node_id format"""
        if "::" in unique_node_id:
            state_name, node_id = unique_node_id.split("::", 1)
            state_data = self.state_manager.fdom_data.get("states", {}).get(state_name, {})
            return state_data.get("nodes", {}).get(node_id)
        
        # Fallback for old format
        return self._find_node_in_fdom_old(unique_node_id)

    def _find_node_state(self, unique_node_id: str) -> Optional[str]:
        """Find which state contains the node - handle state::node_id format"""
        if "::" in unique_node_id:
            state_name, node_id = unique_node_id.split("::", 1)
            # Verify the node exists in that state
            state_data = self.state_manager.fdom_data.get("states", {}).get(state_name, {})
            if node_id in state_data.get("nodes", {}):
                return state_name
            return None
        
        # Fallback for old format
        for state_id, state_data in self.state_manager.fdom_data.get("states", {}).items():
            if unique_node_id in state_data.get("nodes", {}):
                return state_id
        return None


    def _add_manual_description(self, node_id: str, description: str) -> None:
        """Add manual description to a node"""
        for state_id, state_data in self.state_manager.fdom_data["states"].items():
            if node_id in state_data.get("nodes", {}):
                node = state_data["nodes"][node_id]
                node["status"] = "manual_skip"
                if "interactivity" not in node:
                    node["interactivity"] = {}
                node["interactivity"]["manual_description"] = description
                node["interactivity"]["type"] = "manual_skip"
                break

    def _force_reload_fdom_from_file(self) -> None:
        """Force reload fDOM data from JSON file to ensure latest state"""
        try:
            fdom_file = self.apps_base_dir / self.current_app_name / "fdom.json"
            if fdom_file.exists():
                with open(fdom_file, 'r', encoding='utf-8') as f:
                    latest_fdom = json.load(f)
                
                # Replace in-memory data with latest from file
                self.state_manager.fdom_data = latest_fdom
                
                # Rebuild tracking sets with fresh data
                self.state_manager._rebuild_tracking_sets()
                
                self.console.print(f"[cyan]📂 Reloaded fresh fDOM: {len(self.state_manager.pending_nodes)} pending nodes[/cyan]")
            else:
                self.console.print("[yellow]⚠️ No fDOM file found to reload[/yellow]")
                
        except Exception as e:
            self.console.print(f"[red]❌ Failed to reload fDOM: {e}[/red]")

def main():
    parser = argparse.ArgumentParser(description="fDOM Creator - Complete Application Exploration")
    parser.add_argument("executable_path", help="Path to executable to explore")
    parser.add_argument("--continue-session", action="store_true", help="Continue existing session")
    
    args = parser.parse_args()
    
    # Create and run fDOM creator
    creator = FDOMCreator()
    result = creator.create_fdom_for_app(args.executable_path)
    
    if result["success"]:
        print(f"\n🎉 fDOM creation completed for {result['app_name']}")
    else:
        print(f"\n❌ fDOM creation failed: {result['error']}")

if __name__ == "__main__":
    main()
