"""Interactive CLI for element exploration"""
from typing import List, Dict
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt
from pathlib import Path
import time


class InteractiveCLI:
    """Handles interactive command-line interface for exploration"""
    
    def __init__(self, element_interactor):
        self.interactor = element_interactor
        self.console = Console()
    
    def run_interactive_mode(self) -> None:
        """Enhanced interactive mode with natural navigation"""
        self.console.print(Panel(
            "[bold]🎮 Natural Navigation Mode[/bold]\n\n"
            "[green]Commands:[/green]\n"
            "• Enter number to click element\n"
            "• 0 - Run auto-captioner on all elements\n"
            "• -1 - Auto-explore mode (explore 5 nodes sequentially)\n"
            "• 'back' - Natural backtrack to previous state\n"
            "• 'root' - Backtrack to root state\n"
            "• 'chain' - Show current navigation chain\n"
            "• 'quit' - Exit interactive mode",
            title="🧭 Interactive Explorer",
            border_style="blue"
        ))
        
        while True:
            try:
                # Show current state
                self.console.print(f"\n[bold]📍 Current State: {self.interactor.current_state_id}[/bold]")
                
                # Show pending nodes
                pending_list = self.show_pending_nodes_list()
                
                if not pending_list:
                    self.console.print("[yellow]No more nodes to explore![/yellow]")
                    break
                
                # Get user input
                user_input = Prompt.ask("Enter number to click, 0 for auto-captioner, -1 for auto-explore, or command")
                
                # Handle commands
                if user_input.lower() == 'quit':
                    break
                elif user_input.strip() == '0':
                    # Auto captioner
                    self._run_auto_captioner(pending_list)
                    continue
                elif user_input.strip() == '-1':
                    # ✅ NEW: Auto-explore mode
                    self._run_auto_explorer(pending_list)
                    continue
                elif user_input.lower() == 'back':
                    self._handle_back_command()
                    continue
                elif user_input.lower() == 'root':
                    self._handle_root_command()
                    continue
                elif user_input.lower() == 'chain':
                    self._show_navigation_chain()
                    continue
                
                # Handle number input
                try:
                    index = int(user_input) - 1
                    if 0 <= index < len(pending_list):
                        self._interactive_click_node_by_index(index, pending_list)
                    else:
                        self.console.print("[red]❌ Invalid number. Please try again.[/red]")
                except ValueError:
                    self.console.print("[red]❌ Invalid input. Enter a number or command.[/red]")
                
            except KeyboardInterrupt:
                self.console.print("\n[yellow]👋 Exiting interactive mode...[/yellow]")
                break
    
    def show_pending_nodes_list(self, showTable = True) -> List[str]:
        """Show pending nodes in natural discovery order and return the list"""
        if not self.interactor.state_manager.pending_nodes:
            self.console.print("[yellow]⚠️ No pending nodes available.[/yellow]")
            return []
        
        # ✅ FIX: Get nodes in discovery order from fDOM states
        pending_list = []
        
        # Iterate through states in creation order
        states = self.interactor.state_manager.fdom_data.get("states", {})
        state_names = sorted(states.keys())  # This gives us root, root_file, etc. in order
        
        for state_name in state_names:
            state_data = states[state_name]
            nodes = state_data.get("nodes", {})
            
            # Get nodes in the order they appear in the JSON (discovery order)
            for node_id, node_data in nodes.items():
                unique_node_id = f"{state_name}::{node_id}"
                
                # Only include if it's still pending
                if unique_node_id in self.interactor.state_manager.pending_nodes:
                    pending_list.append(unique_node_id)
        
        # ✅ NEW: Filter out "unanalyzed" elements
        filtered_pending_list = []
        for unique_node_id in pending_list:
            node_data = self.interactor._find_node_in_fdom(unique_node_id)
            if node_data:
                element_name = node_data.get('g_icon_name', 'unknown')
                # Skip elements with "unanalyzed" names
                if element_name.lower() != 'unanalyzed':
                    filtered_pending_list.append(unique_node_id)
        
        # Use filtered list for display
        display_list = filtered_pending_list
        unfiltered_count = len(pending_list)
        filtered_count = len(display_list)
        
        # Update table title to show filtered count
        filter_info = f" (Showing {filtered_count}/{unfiltered_count} analyzed elements)" if filtered_count != unfiltered_count else ""
        table = Table(title=f"🟡 Pending Nodes - Choose a Number (Discovery Order){filter_info}")
        table.add_column("#", style="cyan", width=3)
        table.add_column("Node ID", style="green", width=8)
        table.add_column("Element Name", style="yellow", width=25)
        table.add_column("Type", style="magenta", width=6)
        table.add_column("G-Type", style="bright_magenta", width=6)
        table.add_column("Group", style="blue", width=6)
        table.add_column("Enabled", style="cyan", width=8)
        table.add_column("Interactive", style="green", width=11)
        
        for i, unique_node_id in enumerate(display_list, 1):
            # Handle state::node_id format
            if "::" in unique_node_id:
                state_name, node_id = unique_node_id.split("::", 1)
            else:
                state_name = "unknown"
                node_id = unique_node_id
            
            # Find node data
            node_data = self.interactor._find_node_in_fdom(unique_node_id)
            
            if node_data:
                element_name = node_data.get('g_icon_name', 'unknown')
                node_type = node_data.get('type', 'unknown')  # Original type
                g_type = node_data.get('g_type', 'icon')      # New Gemini type
                group = node_data.get('group', 'unknown')
                
                # ✅ ENHANCED: Combined enabled + interactive status
                enabled = node_data.get('g_enabled', True)
                interactive = node_data.get('g_interactive', True)
                
                # Create combined status indicator
                if not enabled:
                    status = "🚫 Disabled"
                elif not interactive:
                    status = "ℹ️ Info Only"
                else:
                    status = "✅ Active"
                
            else:
                element_name = "Not found"
                node_type = "unknown"
                g_type = "unknown"
                group = "unknown"
                status = "❓ Unknown"
            
            # ✅ Truncate long element names to fit
            if len(element_name) > 25:
                element_name = element_name[:22] + "..."
            
            enabled_status = "✅ Yes" if enabled else "🚫 No"
            interactive_status = "⚡ Yes" if interactive else "ℹ️ Info"
            
            table.add_row(
                str(i),
                node_id,
                element_name,
                node_type,    # Original yolo/ocr type
                g_type,       # New Gemini type
                group,
                enabled_status,
                interactive_status
            )
        if showTable:
            self.console.print(table)
        
        # ✅ IMPORTANT: Return the filtered list so numbering works correctly
        return display_list
    
    def _interactive_click_node_by_index(self, index: int, pending_list: List[str]) -> None:
        """Click a node by its index in the pending list"""
        
        if index < 0 or index >= len(pending_list):
            self.console.print(f"[red]❌ Invalid number. Choose 1-{len(pending_list)}[/red]")
            return
        
        selected_node_id = pending_list[index]
        
        # Find node info for display
        node_data = self.interactor._find_node_in_fdom(selected_node_id)
        element_name = node_data.get('g_icon_name', 'unknown') if node_data else 'unknown'
        
        self.console.print(f"\n[bold yellow]🎯 {index + 1}. {element_name} ({selected_node_id})[/bold yellow]")
        self.console.print(f"[cyan]🚀 Executing full interaction workflow...[/cyan]")
        
        # Perform the click with full workflow
        result = self.interactor.click_element(selected_node_id)
        
        # Show detailed result
        if result.success:
            if result.state_changed:
                self.console.print(f"[bold green]✅ SUCCESS: State changed to {result.new_state_id}![/bold green]")
                self.console.print(f"[cyan]📸 Screenshots: Before/After captured[/cyan]")
                self.console.print(f"[cyan]🔍 Visual diff: {result.screenshot_path}[/cyan]")
                self.console.print(f"[cyan]🤖 Seraphine: Analyzed new elements[/cyan]")
                self.console.print(f"[cyan]💾 fDOM: Updated and saved[/cyan]")
            else:
                self.console.print(f"[yellow]✅ SUCCESS: Element marked as {result.interaction_type}[/yellow]")
                if result.interaction_type == "non_interactive":
                    self.console.print(f"[dim]ℹ️ This element doesn't change the UI[/dim]")
        else:
            self.console.print(f"[red]❌ FAILED: {result.error_message}[/red]")
        
        # Show updated exploration stats
        explored_count = len(self.interactor.state_manager.explored_nodes)
        pending_count = len(self.interactor.state_manager.pending_nodes)
        non_interactive_count = len(self.interactor.state_manager.non_interactive_nodes)
        
        self.console.print(f"\n[cyan]📊 Progress: {explored_count} explored, {pending_count} pending, {non_interactive_count} non-interactive[/cyan]")
    
    def _handle_back_command(self):
        """Handle 'back' command for natural backtracking"""
        if len(self.interactor.navigation_engine.navigation_chain) == 0:
            self.console.print("[yellow]⚠️ Already at starting point[/yellow]")
            return
        
        # Get previous state
        previous_step = self.interactor.navigation_engine.navigation_chain[-1]
        target_state = previous_step['from_state']
        
        self.console.print(f"[cyan]🔄 Backing up to: {target_state}[/cyan]")
        
        success = self.interactor.navigation_engine.navigate_back_to_state(target_state)
        
        if success:
            self.console.print(f"[green]✅ Successfully navigated back to {target_state}[/green]")
        else:
            self.console.print(f"[red]❌ Failed to navigate back to {target_state}[/red]")
    
    def _handle_root_command(self):
        """Handle 'root' command to return to root state"""
        self.console.print(f"[cyan]🏠 Returning to root state...[/cyan]")
        
        success = self.interactor.navigation_engine.navigate_back_to_state("root")
        
        if success:
            self.console.print(f"[green]✅ Successfully returned to root[/green]")
            # Clear navigation chain
            self.interactor.navigation_engine.navigation_chain.clear()
        else:
            self.console.print(f"[red]❌ Failed to return to root[/red]")
    
    def _show_navigation_chain(self):
        """Show current navigation chain"""
        chain = self.interactor.navigation_engine.navigation_chain
        
        if not chain:
            self.console.print("[yellow]📍 Navigation chain is empty (at starting point)[/yellow]")
            return
        
        self.console.print("[cyan]🔗 Current Navigation Chain:[/cyan]")
        for i, step in enumerate(chain):
            self.console.print(f"[dim]  {i+1}. {step['from_state']} → {step['to_state']} (via {step['element_name']})[/dim]")
    
    def _run_auto_captioner(self, pending_list: List[str]) -> None:
        """Run auto captioner on all pending elements"""
        from .auto_captioner import AutoCaptioner
        
        self.console.print(f"\n[bold yellow]🤖 AUTO CAPTIONER STARTING...[/bold yellow]")
        self.console.print(f"[cyan]Will hover over {len(pending_list)} elements to discover captions/tooltips[/cyan]")
        
        # Create auto captioner
        auto_captioner = AutoCaptioner(self.interactor)
        
        # Discover captions
        discovered_captions = auto_captioner.discover_all_captions(pending_list)
        
        # ✅ ENSURE CLEANUP: Explicitly call cleanup after completion
        self.console.print(f"[yellow]🧹 Cleaning up temporary interaction screenshots...[/yellow]")
        auto_captioner._cleanup_temp_files()
        
        # Show results
        if discovered_captions:
            # self.console.print(f"\n[bold green]🎉 CAPTIONS DISCOVERED:[/bold green]")
            for node_id, crop_path in discovered_captions.items():
                clean_node_id = node_id.split("::")[-1] if "::" in node_id else node_id
                crop_filename = Path(crop_path).name
                # self.console.print(f"[green]📸 {clean_node_id}: {crop_filename}[/green]")
        else:
            self.console.print(f"[yellow]ℹ️ No captions found for any elements[/yellow]")
        
        # input("\nPress Enter to continue...") 
    
    def _run_auto_explorer(self, pending_list: List[str]) -> None:
        """Auto-explore mode: sequentially explore up to 5 nodes"""
        
        if not pending_list:
            self.console.print("[yellow]⚠️ No pending nodes to explore[/yellow]")
            return
        
        self.console.print(f"\n[bold cyan]🚀 AUTO-EXPLORE MODE STARTING...[/bold cyan]")
        self.console.print(f"[cyan]Will explore up to 5 nodes sequentially[/cyan]")
        self.console.print(f"[dim]Total pending: {len(pending_list)} nodes[/dim]")
        
        # Track exploration results
        exploration_results = []
        explored_count = 0
        max_explorations = 50
        
        # ✅ FIX: Use a copy of the original list and track position
        remaining_nodes = pending_list.copy()
        
        while explored_count < max_explorations and remaining_nodes:
            # Take the first node from remaining list
            selected_node_id = remaining_nodes.pop(0)
            
            # Find node info for display
            node_data = self.interactor._find_node_in_fdom(selected_node_id)
            element_name = node_data.get('g_icon_name', 'unknown') if node_data else 'unknown'
            
            self.console.print(f"\n[bold yellow]🎯 AUTO-EXPLORE {explored_count + 1}/{max_explorations}: {element_name} ({selected_node_id})[/bold yellow]")
            self.console.print(f"[cyan]🚀 Executing full interaction workflow...[/cyan]")
            
            # Perform the click with full workflow
            try:
                result = self.interactor.click_element(selected_node_id)
                
                # Track result
                exploration_results.append({
                    'node_id': selected_node_id,
                    'element_name': element_name,
                    'success': result.success,
                    'state_changed': result.state_changed if result.success else False,
                    'interaction_type': result.interaction_type if result.success else 'failed',
                    'error_message': result.error_message if not result.success else None
                })
                
                # Show detailed result
                if result.success:
                    if result.state_changed:
                        self.console.print(f"[bold green]✅ SUCCESS: State changed to {result.new_state_id}![/bold green]")
                        self.console.print(f"[cyan]📸 Screenshots: Before/After captured[/cyan]")
                        self.console.print(f"[cyan]🔍 Visual diff: {result.screenshot_path}[/cyan]")
                        self.console.print(f"[cyan]🤖 Seraphine: Analyzed new elements[/cyan]")
                        self.console.print(f"[cyan]💾 fDOM: Updated and saved[/cyan]")
                    else:
                        self.console.print(f"[yellow]✅ SUCCESS: Element marked as {result.interaction_type}[/yellow]")
                        if result.interaction_type == "non_interactive":
                            self.console.print(f"[dim]ℹ️ This element doesn't change the UI[/dim]")
                else:
                    self.console.print(f"[red]❌ FAILED: {result.error_message}[/red]")
                    self.console.print(f"[yellow]⏭️ Skipping to next node...[/yellow]")
                
                # ✅ CRITICAL: Increment counter regardless of success/failure
                explored_count += 1
                
                # Small delay between explorations for stability
                if explored_count < max_explorations and remaining_nodes:  # Don't wait after the last one
                    self.console.print(f"[dim]⏳ Waiting 2 seconds before next exploration...[/dim]")
                    time.sleep(2)
                    
            except Exception as e:
                self.console.print(f"[red]❌ EXCEPTION during exploration: {e}[/red]")
                exploration_results.append({
                    'node_id': selected_node_id,
                    'element_name': element_name,
                    'success': False,
                    'state_changed': False,
                    'interaction_type': 'exception',
                    'error_message': str(e)
                })
                
                # ✅ CRITICAL: Increment counter even on exception
                explored_count += 1
                
                self.console.print(f"[yellow]⏭️ Skipping to next node...[/yellow]")
        
        # ✅ SAFETY: Show why we stopped
        if explored_count >= max_explorations:
            self.console.print(f"[green]✅ Completed {max_explorations} explorations as planned[/green]")
        elif not remaining_nodes:
            self.console.print(f"[yellow]⚠️ No more nodes to explore (completed {explored_count} explorations)[/yellow]")
        
        # Show final summary
        self._show_auto_explore_summary(exploration_results)
        
        # Show updated exploration stats
        explored_count_total = len(self.interactor.state_manager.explored_nodes)
        pending_count = len(self.interactor.state_manager.pending_nodes)
        non_interactive_count = len(self.interactor.state_manager.non_interactive_nodes)
        
        self.console.print(f"\n[cyan]📊 Progress: {explored_count_total} explored, {pending_count} pending, {non_interactive_count} non-interactive[/cyan]")
        
        # Pause for user review
        self.console.print(f"\n[bold yellow]⏸️ AUTO-EXPLORE SESSION COMPLETE[/bold yellow]")
        input("Press Enter to continue with manual exploration...")

    def _show_auto_explore_summary(self, results: List[Dict]) -> None:
        """Show summary of auto-exploration results"""
        
        if not results:
            return
        
        self.console.print(f"\n[bold blue]📋 AUTO-EXPLORE SUMMARY:[/bold blue]")
        
        # Create summary table
        summary_table = Table(title="Auto-Exploration Results")
        summary_table.add_column("#", style="cyan", width=3)
        summary_table.add_column("Element", style="yellow", width=20)
        summary_table.add_column("Result", style="green", width=15)
        summary_table.add_column("Type", style="magenta", width=12)
        summary_table.add_column("Error", style="red", width=25)
        
        success_count = 0
        state_change_count = 0
        
        for i, result in enumerate(results, 1):
            element_name = result['element_name']
            if len(element_name) > 20:
                element_name = element_name[:17] + "..."
                
            error_msg = result.get('error_message', '')
            if error_msg and len(error_msg) > 25:
                error_msg = error_msg[:22] + "..."
            
            # Format result status
            if result['success']:
                if result['state_changed']:
                    status = "✅ State Change"
                    state_change_count += 1
                else:
                    status = f"✅ {result['interaction_type'].title()}"
                success_count += 1
                error_msg = "-"
            else:
                status = "❌ Failed"
            
            summary_table.add_row(
                str(i),
                element_name,
                status,
                result['interaction_type'],
                error_msg or "-"
            )
        
        self.console.print(summary_table)
        
        # Show statistics
        total = len(results)
        if total > 0:
            self.console.print(f"\n[cyan]📈 Statistics:[/cyan]")
            self.console.print(f"[green]✅ Successful: {success_count}/{total} ({success_count/total*100:.1f}%)[/green]")
            self.console.print(f"[blue]🔄 State Changes: {state_change_count}/{total} ({state_change_count/total*100:.1f}%)[/blue]")
            self.console.print(f"[red]❌ Failed: {total-success_count}/{total} ({(total-success_count)/total*100:.1f}%)[/red]") 