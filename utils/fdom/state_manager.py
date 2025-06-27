"""
StateManager - fDOM graph creation and state tracking for fDOM Framework
Manages NetworkX-based graph structure and node status tracking (pending/explored/non_interactive)
"""
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass
from datetime import datetime
import networkx as nx
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.tree import Tree
from rich.progress import Progress, TextColumn, BarColumn, TaskProgressColumn
from rich import print as rprint

from config_manager import ConfigManager
from seraphine_integrator import SeraphineIntegrator


@dataclass
class FDOMNode:
    """
    Individual fDOM node representing a UI element
    """
    # ✅ FIELDS WITHOUT DEFAULTS (must come first)
    id: str                    # H0_1, H1_2, etc.
    bbox: List[int]           # [x1, y1, x2, y2]
    g_icon_name: str          # Seraphine-generated name
    g_brief: str              # Seraphine-generated description
    m_id: str                 # Master ID from seraphine
    type: str                 # "icon" or "text" (from yolo/ocr)
    source: str               # "yolo" or "ocr_det"
    group: str                # H0, H1, H2, etc.
    
    # ✅ OPTIONAL FIELDS (can have None defaults)
    y_id: Optional[str] = None       # YOLO detection ID
    o_id: Optional[str] = None       # OCR detection ID
    
    # ✅ FIELDS WITH DEFAULTS (must come last)
    g_enabled: bool = True           # Whether element is enabled (not grayed out)
    g_interactive: bool = True       # Whether element is interactive
    g_type: str = "icon"            # Gemini-analyzed type: "icon" or "text"
    status: str = "pending"          # "pending", "explored", "non_interactive"
    click_result: Optional[str] = None    # Points to next state ID
    interaction_type: Optional[str] = None # "menu", "dialog", "navigation", etc.
    
    def to_dict(self) -> Dict:
        """Convert to fDOM JSON format"""
        node_dict = {
            "bbox": self.bbox,
            "g_icon_name": self.g_icon_name,
            "g_brief": self.g_brief,
            "g_enabled": self.g_enabled,
            "g_interactive": self.g_interactive,
            "g_type": self.g_type,
            "m_id": self.m_id,
            "y_id": self.y_id,
            "o_id": self.o_id,
            "type": self.type,
            "source": self.source,
            "group": self.group,
            "status": self.status
        }
        
        # Add interactivity section if element has been explored
        if self.click_result or self.interaction_type:
            node_dict["interactivity"] = {}
            if self.click_result:
                node_dict["interactivity"]["click_result"] = self.click_result
            if self.interaction_type:
                node_dict["interactivity"]["type"] = self.interaction_type
                
        return node_dict


class StateManager:
    """
    Manages fDOM graph creation, state tracking, and NetworkX operations
    """
    
    def __init__(self, app_name: str):
        self.app_name = app_name
        self.config = ConfigManager()
        self.console = Console()
        self.seraphine = SeraphineIntegrator(app_name)
        
        # NetworkX graph for exploration logic
        self.exploration_graph = nx.DiGraph()
        
        # SEMANTIC NAMING: Start with root
        self.current_state_id = "root"  # ✅ Not "S001"
        
        # Initialize fDOM with semantic structure
        self.fdom_data = {
            "app_name": app_name,
            "loaded": False,
            "creation_timestamp": datetime.now().isoformat(),
            "navigation_tree": {},  # Track semantic hierarchy
            "states": {},
            "edges": []
        }
        
        # Tracking
        self.total_nodes = 0
        self.pending_nodes: Set[str] = set()
        self.explored_nodes: Set[str] = set()
        self.non_interactive_nodes: Set[str] = set()
        
        self.console.print(f"[green]🧠 StateManager initialized for: {app_name}[/green]")
    
    def create_initial_fdom_state(self, screenshot_path: str) -> Dict:
        """FIXED: Use semantic naming for root state"""
        self.console.print(f"\n[bold blue]🏗️ CREATING INITIAL ROOT STATE[/bold blue]")
        self.console.print(f"Screenshot: {screenshot_path}")
        
        # Process through seraphine - pass "root" instead of current_state_id
        seraphine_result = self.seraphine.analyze_screenshot(screenshot_path, "root")
        
        if not seraphine_result or not seraphine_result.get('nodes'):
            self.console.print("[red]❌ No nodes detected from screenshot[/red]")
            return {}
        
        # Create ROOT state data
        state_data = {
            "id": "root",  # ✅ Semantic name
            "parent": None,
            "trigger_node": None,
            "trigger_element": "initial_state",
            "breadcrumb": "root",
            "image": screenshot_path,  # ✅ This should be current screenshot, not S001.png
            "creation_timestamp": datetime.now().isoformat(),
            "analysis_time": seraphine_result.get('analysis_time', 0),
            "total_elements": len(seraphine_result['nodes']),
            "nodes": {}
        }
        
        # Convert seraphine nodes to fDOM nodes
        fdom_nodes = []
        for node_id, node_data in seraphine_result['nodes'].items():
            fdom_node = FDOMNode(
                id=node_id,
                bbox=node_data['bbox'],
                g_icon_name=node_data['g_icon_name'],
                g_brief=node_data['g_brief'],
                g_enabled=node_data.get('g_enabled', True),
                g_interactive=node_data.get('g_interactive', True),
                g_type=node_data.get('g_type', 'icon'),
                m_id=node_data['m_id'],
                y_id=node_data.get('y_id'),
                o_id=node_data.get('o_id'),
                type=node_data['type'],
                source=node_data['source'],
                group=node_data['group']
            )
            fdom_nodes.append(fdom_node)
            
            # Add to fDOM data
            state_data["nodes"][node_id] = fdom_node.to_dict()
            
            # Add to NetworkX graph
            self.exploration_graph.add_node(
                node_id,
                **fdom_node.__dict__
            )
            
            # Track as pending for exploration
            self.pending_nodes.add(f"root::{node_id}")
        
        # Save state to fDOM data
        self.fdom_data["states"]["root"] = state_data
        self.total_nodes = len(fdom_nodes)
        
        
        # ✅ FIXED: Save the fDOM data to file
        self.save_fdom_to_file()
        
        return state_data
    
    def get_next_pending_node(self) -> Optional[str]:
        """
        Get the next node that needs to be explored (graph-based traversal)
        
        Returns:
            Node ID to explore next, or None if all explored
        """
        if not self.pending_nodes:
            return None
            
        # For now, return first pending node (can implement smarter strategies later)
        return next(iter(self.pending_nodes))
    
    def mark_node_explored(self, node_id: str, click_result: Optional[str] = None, 
                          interaction_type: Optional[str] = None) -> None:
        """
        Mark a node as explored and update its interaction results
        
        Args:
            node_id: Node to mark as explored
            click_result: Result state ID if clicking caused state change
            interaction_type: Type of interaction (menu, dialog, etc.)
        """
        if node_id in self.pending_nodes:
            self.pending_nodes.remove(node_id)
            
        if click_result:
            self.explored_nodes.add(node_id)
            # Update in graph
            if self.exploration_graph.has_node(node_id):
                self.exploration_graph.nodes[node_id]['status'] = 'explored'
                self.exploration_graph.nodes[node_id]['click_result'] = click_result
                self.exploration_graph.nodes[node_id]['interaction_type'] = interaction_type
                
            # Update in fDOM data
            for state_id, state_data in self.fdom_data["states"].items():
                if node_id in state_data.get("nodes", {}):
                    state_data["nodes"][node_id]["status"] = "explored"
                    if "interactivity" not in state_data["nodes"][node_id]:
                        state_data["nodes"][node_id]["interactivity"] = {}
                    state_data["nodes"][node_id]["interactivity"]["click_result"] = click_result
                    if interaction_type:
                        state_data["nodes"][node_id]["interactivity"]["type"] = interaction_type
                    break
        else:
            self.non_interactive_nodes.add(node_id)
            # Update status to non_interactive
            if self.exploration_graph.has_node(node_id):
                self.exploration_graph.nodes[node_id]['status'] = 'non_interactive'
                
            # Update in fDOM data
            for state_id, state_data in self.fdom_data["states"].items():
                if node_id in state_data.get("nodes", {}):
                    state_data["nodes"][node_id]["status"] = "non_interactive"
                    break
    
    def save_fdom_to_file(self, output_path: Optional[str] = None) -> str:
        """
        Save the current fDOM structure to JSON file
        
        Args:
            output_path: Custom output path, or auto-generate if None
            
        Returns:
            Path where fDOM was saved
        """
        if not output_path:
            app_dir = Path(__file__).parent.parent.parent / "apps" / self.app_name
            app_dir.mkdir(parents=True, exist_ok=True)
            output_path = app_dir / "fdom.json"
        
        # Update metadata
        self.fdom_data.update({
            "last_updated": datetime.now().isoformat(),
            "total_states": len(self.fdom_data["states"]),
            "exploration_stats": {
                "pending_nodes": len(self.pending_nodes),
                "explored_nodes": len(self.explored_nodes),
                "non_interactive_nodes": len(self.non_interactive_nodes),
                "total_nodes": self.total_nodes
            }
        })
        
        # Save to file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.fdom_data, f, indent=2, ensure_ascii=False)
        
        self.console.print(f"[green]💾 fDOM saved to: {output_path}[/green]")
        return str(output_path)
    
    def _rebuild_tracking_sets(self) -> None:
        """FIXED: Handle duplicate node IDs across states"""
        self.pending_nodes.clear()
        self.explored_nodes.clear()
        self.non_interactive_nodes.clear()
        
        # Use state-prefixed node IDs to avoid collisions
        for state_name, state_data in self.fdom_data.get("states", {}).items():
            nodes = state_data.get("nodes", {})
            for node_id, node_data in nodes.items():
                status = node_data.get("status", "pending")
                
                # Create unique ID: state_name::node_id
                unique_node_id = f"{state_name}::{node_id}"
                
                if status == "pending":
                    self.pending_nodes.add(unique_node_id)
                elif status == "explored":
                    self.explored_nodes.add(unique_node_id)
                elif status == "non_interactive":
                    self.non_interactive_nodes.add(unique_node_id)
        
        self.total_nodes = len(self.pending_nodes) + len(self.explored_nodes) + len(self.non_interactive_nodes)
        
        self.console.print(f"[green]🔄 Rebuilt tracking sets: {len(self.pending_nodes)} pending, {len(self.explored_nodes)} explored, {len(self.non_interactive_nodes)} non-interactive[/green]")
        self.console.print(f"[cyan]🧭 Current state: {self.current_state_id}[/cyan]")

    
    def display_exploration_status(self) -> None:
        """Display current exploration status and graph statistics"""
        
        # Status panel
        status_panel = Panel(
            f"[bold]Exploration Status[/bold]\n\n"
            f"🟡 Pending: {len(self.pending_nodes)}\n"
            f"🟢 Explored: {len(self.explored_nodes)}\n"
            f"🔴 Non-Interactive: {len(self.non_interactive_nodes)}\n"
            f"📊 Total Nodes: {self.total_nodes}\n"
            f"📈 States Created: {len(self.fdom_data['states'])}",
            title="🧠 fDOM Exploration Status",
            border_style="green"
        )
        self.console.print(status_panel)
        
        # Next node to explore
        next_node = self.get_next_pending_node()
        if next_node:
            self.console.print(f"[yellow]⏭️  Next to explore: {next_node}[/yellow]")
        else:
            self.console.print("[green]✅ All nodes explored![/green]")


def test_fdom_creation(screenshot_path: str, app_name: str = "test_app"):
    """Test function for DELTA 5"""
    console = Console()
    
    console.print(Panel(
        f"[bold]🧪 TESTING fDOM CREATION[/bold]\n"
        f"Screenshot: {screenshot_path}\n"
        f"App: {app_name}",
        title="DELTA 5 Test",
        border_style="yellow"
    ))
    
    # Initialize StateManager
    state_manager = StateManager(app_name)
    
    # Create initial fDOM state
    state_data = state_manager.create_initial_fdom_state(screenshot_path)
    
    if not state_data:
        console.print("[red]❌ Test failed - no state created[/red]")
        return
    
    # Display exploration status
    state_manager.display_exploration_status()
    
    # Save fDOM to file
    fdom_path = state_manager.save_fdom_to_file()
    
    # Test results
    test_panel = Panel(
        f"[bold]Test Complete![/bold]\n\n"
        f"📊 Nodes Created: {len(state_data.get('nodes', {}))}\n"
        f"⏱️  Analysis Time: {state_data.get('analysis_time', 0):.2f}s\n"
        f"🟡 Pending: {len(state_manager.pending_nodes)}\n"
        f"💾 fDOM Saved: {fdom_path}",
        title="🧪 Test Results",
        border_style="green"
    )
    console.print(test_panel)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="StateManager for fDOM Framework")
    parser.add_argument("--test-fdom-creation", type=str, help="Test fDOM creation with screenshot path")
    parser.add_argument("--app-name", type=str, default="test_app", help="App name for testing")
    
    args = parser.parse_args()
    
    if args.test_fdom_creation:
        test_fdom_creation(args.test_fdom_creation, args.app_name)
    else:
        print("Use --test-fdom-creation <screenshot_path> to test")
