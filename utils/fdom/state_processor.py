"""State creation and processing logic"""
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from rich.console import Console


class StateProcessor:
    """Handles state creation, semantic naming, and metadata"""
    
    def __init__(self, state_manager, seraphine_integrator, visual_differ):
        self.state_manager = state_manager
        self.seraphine_integrator = seraphine_integrator
        self.visual_differ = visual_differ
        self.console = Console()
        
    def process_successful_click(self, node_id: str, source_element_name: str, 
                            current_state: str, before_screenshot: str, 
                            after_screenshot: str, diff_path: str, 
                            perfect_diff_result: Dict = None) -> Optional[str]:
        """Process a successful click that caused state change - REUSE PERFECT CROP"""
        
        # Generate semantic state name
        new_state_name = self._generate_semantic_state_name(source_element_name, current_state)
        
        # ✅ REUSE PERFECT CROP from ClickEngine instead of creating new one
        if perfect_diff_result and perfect_diff_result.get("success"):
            diff_result = perfect_diff_result
            # Copy the perfect crop to our diff_path location
            import shutil
            perfect_crop_path = perfect_diff_result["diff_image_path"]
            shutil.copy2(perfect_crop_path, diff_path)
            self.console.print(f"[green]✅ Reused perfect crop from ClickEngine[/green]")
        else:
            # Fallback: create new crop (shouldn't happen)
            diff_result = self.visual_differ.extract_change_regions(
                before_screenshot, after_screenshot, diff_path, (0, 0)
            )
        
        if not diff_result["success"]:
            self.console.print("[red]❌ Failed to extract change regions[/red]")
            return None
        
        # Analyze with Seraphine using the actual difference image
        popup_crop_path = diff_result["diff_image_path"]
        seraphine_result = self.seraphine_integrator.analyze_screenshot(
            popup_crop_path, new_state_name, source_element_name
        )
        
        if not seraphine_result or not seraphine_result.get('nodes'):
            self.console.print("[red]❌ Seraphine analysis failed[/red]")
            return None
        
        # Create new state data
        new_state_data = self._create_semantic_state_data(
            new_state_name, seraphine_result, diff_path,
            source_element_name, node_id, current_state
        )
        
        # Add elements with coordinate mapping and deduplication
        unified_region = diff_result["regions"][0]
        x_offset, y_offset = unified_region[0], unified_region[1]
        
        new_nodes_added = 0
        for popup_node_id, popup_node_data in seraphine_result['nodes'].items():
            crop_bbox = popup_node_data['bbox']
            full_bbox = [
                crop_bbox[0] + x_offset, crop_bbox[1] + y_offset,
                crop_bbox[2] + x_offset, crop_bbox[3] + y_offset
            ]
            popup_node_data['bbox'] = full_bbox
            
            if not self._is_duplicate_element(popup_node_data, current_state):
                new_state_data["nodes"][popup_node_id] = popup_node_data
                self.state_manager.pending_nodes.add(f"{new_state_name}::{popup_node_id}")
                new_nodes_added += 1
            else:
                self.console.print(f"[dim]🔄 Skipped duplicate: {popup_node_data.get('g_icon_name', 'unknown')}[/dim]")
        
        self.console.print(f"[cyan]✅ Added {new_nodes_added}/{len(seraphine_result['nodes'])} new elements[/cyan]")
        
        # Save state and update tracking
        self.state_manager.fdom_data["states"][new_state_name] = new_state_data
        self.state_manager.mark_node_explored(node_id, click_result=new_state_name, interaction_type="menu")
        self._add_interaction_edge(current_state, new_state_name, node_id)
        self.state_manager.save_fdom_to_file()
        
        return new_state_name

    
    def _generate_semantic_state_name(self, element_name: str, current_state: str) -> str:
        """Generate file-safe semantic state name"""
        clean_name = element_name.lower().replace(' ', '_').replace('(', '').replace(')', '').replace('/', '_')
        
        if current_state == "root":
            return f"root_{clean_name}"
        else:
            return f"{current_state}_{clean_name}"
    
    def _create_semantic_state_data(self, state_name: str, seraphine_result: Dict, 
                                   diff_path: str, source_element: str, 
                                   trigger_node: str, parent_state: str) -> Dict:
        """Create state with semantic metadata"""
        display_breadcrumb = state_name.replace('_', '>')
        
        return {
            "id": state_name,
            "parent": parent_state,
            "trigger_node": trigger_node,
            "trigger_element": source_element,
            "breadcrumb": display_breadcrumb,
            "image": str(diff_path),
            "creation_timestamp": datetime.now().isoformat(),
            "analysis_time": seraphine_result.get('total_time', 0),
            "total_elements": len(seraphine_result['nodes']),
            "nodes": {}
        }
    
    def _is_duplicate_element(self, node_data: Dict, current_state: str) -> bool:
        """ENHANCED: Check if element is duplicate with stronger logic"""
        element_name = node_data.get('g_icon_name', '').lower().strip()
        element_bbox = node_data.get('bbox', [])
        
        if not element_name or not element_bbox or len(element_bbox) != 4:
            return False
        
        # Calculate element dimensions for proportional tolerance
        element_width = element_bbox[2] - element_bbox[0]
        element_height = element_bbox[3] - element_bbox[1]
        
        # ✅ FLEXIBLE: Tolerance based on element size (5% of width/height, min 10px, max 50px)
        position_tolerance = max(10, min(50, max(element_width * 0.05, element_height * 0.05)))
        
        # Check against ALL states in fDOM
        for state_name, state_data in self.state_manager.fdom_data.get("states", {}).items():
            for existing_node_id, existing_node_data in state_data.get("nodes", {}).items():
                existing_name = existing_node_data.get('g_icon_name', '').lower().strip()
                existing_bbox = existing_node_data.get('bbox', [])
                existing_status = existing_node_data.get('status', 'unknown')
                
                if not existing_name or len(existing_bbox) != 4:
                    continue
                
                # ✅ STRONG: Multiple criteria for duplicate detection
                name_match = element_name == existing_name
                
                # Position similarity with proportional tolerance
                position_match = (
                    abs(element_bbox[0] - existing_bbox[0]) < position_tolerance and
                    abs(element_bbox[1] - existing_bbox[1]) < position_tolerance
                )
                
                # Size similarity (within 20% variance)
                existing_width = existing_bbox[2] - existing_bbox[0]
                existing_height = existing_bbox[3] - existing_bbox[1]
                
                size_match = (
                    abs(element_width - existing_width) < max(element_width * 0.2, 10) and
                    abs(element_height - existing_height) < max(element_height * 0.2, 10)
                )
                
                if name_match and position_match and size_match:
                    # ✅ PRIORITY: If existing element is already explored, definitely skip
                    if existing_status == "explored":
                        self.console.print(f"[yellow]🔄 Skipped duplicate (already explored): {element_name} in {state_name}[/yellow]")
                        return True
                    
                    # ✅ SMART: Even if pending, avoid duplicates in different states
                    self.console.print(f"[yellow]🔄 Skipped duplicate (already exists): {element_name} in {state_name}[/yellow]")
                    return True
        
        return False
    
    def _add_interaction_edge(self, from_state: str, to_state: str, node_id: str) -> None:
        """Add edge with enhanced semantic information"""
        # Extract clean node ID
        if "::" in node_id:
            _, clean_node_id = node_id.split("::", 1)
        else:
            clean_node_id = node_id
        
        # Get element info for better edge description
        node_data = self._find_node_in_fdom(node_id)
        element_name = node_data.get('g_icon_name', 'unknown') if node_data else 'unknown'
        
        edge = {
            "from": from_state,
            "to": to_state,
            "action": f"click:{clean_node_id}",
            "element_name": element_name,
            "navigation": f"{from_state} → {to_state}",
            "timestamp": datetime.now().isoformat()
        }
        
        if "edges" not in self.state_manager.fdom_data:
            self.state_manager.fdom_data["edges"] = []
            
        self.state_manager.fdom_data["edges"].append(edge)
        
        self.console.print(f"[blue]🔗 Edge added: {from_state} --[{element_name}]--> {to_state}[/blue]")
    
    def _find_node_in_fdom(self, node_id: str) -> Optional[Dict]:
        """Find node data in fDOM"""
        if "::" in node_id:
            state_name, actual_node_id = node_id.split("::", 1)
            state_data = self.state_manager.fdom_data.get("states", {}).get(state_name, {})
            return state_data.get("nodes", {}).get(actual_node_id)
        
        # Fallback: search all states
        for state_data in self.state_manager.fdom_data.get("states", {}).values():
            nodes = state_data.get("nodes", {})
            if node_id in nodes:
                return nodes[node_id]
        return None
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for Windows compatibility"""
        # Windows invalid characters: < > : " | ? * \
        invalid_chars = '<>:"|?*\\'
        
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        
        # Also handle special cases
        filename = filename.replace('(', '').replace(')', '')
        filename = filename.replace('[', '').replace(']', '')
        
        return filename 
