"""
SeraphineIntegrator - Processes seraphine output into fDOM structure
Transforms seraphine_gemini_groups into fDOM nodes and saves element crops
"""
import os
import sys
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, TextColumn, BarColumn, TaskProgressColumn
from PIL import Image
import numpy as np

# Add parent directories to path for imports
current_file = Path(__file__).resolve()
utils_dir = current_file.parent.parent
sys.path.append(str(utils_dir))

from config_manager import ConfigManager
from seraphine import process_image_sync  # FIXED: Use actual function from seraphine.py

class SeraphineIntegrator:
    """
    Integrates seraphine analysis into fDOM framework
    """
    
    def __init__(self, app_name: str):
        self.app_name = app_name
        self.console = Console()
        self.config_manager = ConfigManager()
        self.config = self.config_manager.config
        
        # FIXED: Setup paths to point to root-level apps directory
        project_root = Path(__file__).parent.parent.parent  # utils/fdom -> utils -> project_root
        self.app_root = project_root / "apps" / app_name
        self.screenshots_dir = self.app_root / "screenshots"
        self.crops_dir = self.app_root / "crops"
        
        # Ensure directories exist
        self.crops_dir.mkdir(parents=True, exist_ok=True)
        
        self.console.print(f"[bold blue]🔍 SeraphineIntegrator initialized for: {app_name}[/bold blue]")
    
    def analyze_screenshot(self, screenshot_path: str, state_id: str, source_element_name: Optional[str] = None) -> Dict:
        """Analyze screenshot and convert to fDOM format"""
        
        # Call Seraphine
        self.console.print(f"[cyan]🔍 Analyzing screenshot: {screenshot_path}[/cyan]")
        seraphine_result = process_image_sync(screenshot_path)  # ✅ FIXED: Use imported function directly
        
        if not seraphine_result:
            self.console.print("[red]❌ Seraphine analysis failed[/red]")
            return {}
        
        # ✅ DEBUG: Show what Seraphine returned
        self.console.print(f"[cyan]🔍 DEBUG: seraphine_result keys: {list(seraphine_result.keys())}[/cyan]")
        
        # ✅ FIXED: Extract the correct groups structure
        seraphine_groups = seraphine_result.get('seraphine_gemini_groups', {})
        
        # ✅ NEW: If seraphine_gemini_groups contains metadata, extract group_details
        if 'group_details' in seraphine_groups:
            self.console.print(f"[cyan]🔧 Extracting group_details from seraphine_gemini_groups[/cyan]")
            actual_groups = seraphine_groups['group_details']
        else:
            # Fallback to the groups directly
            actual_groups = seraphine_groups
        
        # ✅ DEBUG: Show actual groups structure
        self.console.print(f"[cyan]🔍 DEBUG: actual_groups type: {type(actual_groups)}[/cyan]")
        if isinstance(actual_groups, dict) and actual_groups:
            sample_key = list(actual_groups.keys())[0]
            sample_value = actual_groups[sample_key]
            self.console.print(f"[cyan]🔍 DEBUG: Sample group {sample_key}: type={type(sample_value)}[/cyan]")
            if isinstance(sample_value, dict):
                self.console.print(f"[cyan]🔍 DEBUG: Sample group keys: {list(sample_value.keys())}[/cyan]")
        
        if not actual_groups:
            self.console.print("[red]❌ No actual groups found[/red]")
            return {}
        
        # Display results
        self._display_seraphine_results(seraphine_result)
        
        # Convert to fDOM format using the correct groups
        fdom_nodes = self._convert_seraphine_to_fdom(actual_groups, state_id)
        
        if not fdom_nodes:
            return {}
        
        # Save crops
        self._save_element_crops(screenshot_path, fdom_nodes, state_id, source_element_name)
        
        return {
            'nodes': fdom_nodes,
            'total_time': seraphine_result.get('total_time', 0),
            'total_icons_found': seraphine_result.get('total_icons_found', 0)
        }
    
    def _display_seraphine_results(self, seraphine_result: Dict):
        """Display seraphine analysis results in rich console"""
        
        # Summary panel
        summary_text = f"""
        [bold green]Analysis Complete![/bold green]
        
        ⏱️  Total Time: {seraphine_result.get('total_time', 0):.2f}s
        🎯  Icons Found: {seraphine_result.get('total_icons_found', 0)}
        🔍  Groups Detected: {len(seraphine_result.get('seraphine_gemini_groups', {}))}
        """
        
        self.console.print(Panel(summary_text, title="🔍 Seraphine Analysis Results"))
        
        # Detailed group table
        seraphine_groups = seraphine_result.get('seraphine_gemini_groups', {})
        # if seraphine_groups:
        #     table = Table(title="Detected UI Elements by Group")
        #     table.add_column("Group", style="cyan")
        #     table.add_column("Element", style="yellow")
        #     table.add_column("Name", style="green")
        #     table.add_column("Type", style="blue")
        #     table.add_column("IDs", style="magenta")
            
        #     for group_name, group_elements in seraphine_groups.items():
        #         for element_name, element_data in group_elements.items():
        #             ids_text = f"M:{element_data.get('m_id', 'None')} Y:{element_data.get('y_id', 'None')} O:{element_data.get('o_id', 'None')}"
        #             table.add_row(
        #                 group_name,
        #                 element_name,
        #                 element_data.get('g_icon_name', 'Unknown'),
        #                 element_data.get('type', 'unknown'),
        #                 ids_text
        #             )
            
        #     self.console.print(table)
    
    def _convert_seraphine_to_fdom(self, seraphine_groups: Dict, state_id: str) -> Dict:
        """Convert seraphine_gemini_groups to fDOM nodes format with dropdown merging"""
        
        # ✅ DEBUG: Check the structure of seraphine_groups
        self.console.print(f"[cyan]🔍 DEBUG: seraphine_groups type: {type(seraphine_groups)}[/cyan]")
        self.console.print(f"[cyan]🔍 DEBUG: seraphine_groups keys: {list(seraphine_groups.keys()) if isinstance(seraphine_groups, dict) else 'Not a dict'}[/cyan]")
        
        # First pass: collect all elements
        all_elements = []
        for group_name, group_elements in seraphine_groups.items():
            # ✅ DEFENSIVE: Check if group_elements is actually a dictionary
            if not isinstance(group_elements, dict):
                self.console.print(f"[red]⚠️ WARNING: group_elements for {group_name} is {type(group_elements)}, expected dict. Value: {group_elements}[/red]")
                self.console.print(f"[yellow]🔧 Skipping malformed group: {group_name}[/yellow]")
                continue
            
            for element_name, element_data in group_elements.items():
                # ✅ DEFENSIVE: Check if element_data is a dictionary
                if not isinstance(element_data, dict):
                    self.console.print(f"[red]⚠️ WARNING: element_data for {group_name}::{element_name} is {type(element_data)}, expected dict. Value: {element_data}[/red]")
                    continue
                
                element_data['group'] = group_name
                element_data['element_id'] = element_name
                all_elements.append(element_data)
        
        # ✅ SAFETY: Check if we have any valid elements
        if not all_elements:
            self.console.print(f"[red]❌ No valid elements found in seraphine_groups[/red]")
            return {}
        
        # ✅ NEW: Merge dropdown indicators
        merged_elements = self._merge_dropdown_indicators(all_elements)
        
        # Convert to fDOM format
        fdom_nodes = {}
        for element_data in merged_elements:
            element_name = element_data['element_id']
            
            fdom_node = {
                'bbox': element_data.get('bbox', []),
                'g_icon_name': element_data.get('g_icon_name', 'Unknown'),
                'g_brief': element_data.get('g_brief', 'No description'),
                'g_enabled': element_data.get('g_enabled', True),
                'g_interactive': element_data.get('g_interactive', True),
                'g_type': element_data.get('g_type', 'icon'),
                'explore': element_data.get('explore', True),  # NEW: Add explore field
                'm_id': element_data.get('m_id'),
                'y_id': element_data.get('y_id'),
                'o_id': element_data.get('o_id'),
                'type': element_data.get('type', 'unknown'),
                'source': element_data.get('source', 'unknown'),
                'group': element_data['group'],
                'interactivity': {
                    'click_result': None,
                    'type': self._guess_interaction_type(element_data)
                },
                'status': 'pending'
            }
            
            fdom_nodes[element_name] = fdom_node
        
        self.console.print(f"[green]✅ Converted {len(fdom_nodes)} elements to fDOM format[/green]")
        return fdom_nodes
    
    def _merge_dropdown_indicators(self, elements: List[Dict]) -> List[Dict]:
        """Merge standalone dropdown indicators with adjacent elements"""
        
        dropdown_indicators = [">", "v", "▼", "▲", "⌄", "⌃", "›", "‹"]
        elements_to_remove = []
        
        for i, element in enumerate(elements):
            icon_name = element.get('g_icon_name', '').strip()
            
            if icon_name in dropdown_indicators:
                # Find adjacent element (usually to the left)
                target_element = self._find_adjacent_element(element, elements, direction='left')
                
                if target_element:
                    # Merge bboxes
                    orig_bbox = target_element['bbox']
                    arrow_bbox = element['bbox']
                    
                    merged_bbox = [
                        min(orig_bbox[0], arrow_bbox[0]),  # x1
                        min(orig_bbox[1], arrow_bbox[1]),  # y1
                        max(orig_bbox[2], arrow_bbox[2]),  # x2
                        max(orig_bbox[3], arrow_bbox[3])   # y2
                    ]
                    
                    # Update target element
                    target_element['bbox'] = merged_bbox
                    target_element['g_icon_name'] = f"{target_element['g_icon_name']} {icon_name}"
                    target_element['g_brief'] = f"{target_element['g_brief']} (expandable)"
                    
                    # Mark arrow for removal
                    elements_to_remove.append(element)
                    
                    self.console.print(f"[cyan]🔗 Merged dropdown: {target_element['g_icon_name']}[/cyan]")
        
        # Remove merged elements
        for element in elements_to_remove:
            elements.remove(element)
        
        return elements
    
    def _find_adjacent_element(self, arrow_element: Dict, all_elements: List[Dict], direction: str = 'left') -> Optional[Dict]:
        """Find immediately adjacent element for merging (no distance limit)"""
        
        arrow_bbox = arrow_element['bbox']
        arrow_center_y = (arrow_bbox[1] + arrow_bbox[3]) / 2
        
        best_candidate = None
        best_distance = float('inf')
        
        for element in all_elements:
            if element == arrow_element:
                continue
            
            element_bbox = element['bbox']
            element_center_y = (element_bbox[1] + element_bbox[3]) / 2
            
            # Check if vertically aligned (same row) - be more flexible
            y_diff = abs(arrow_center_y - element_center_y)
            if y_diff > 30:  # Allow more vertical variance
                continue
            
            # Check horizontal adjacency
            if direction == 'left':
                # Element should be to the left of arrow
                if element_bbox[2] <= arrow_bbox[0]:  # element right edge <= arrow left edge
                    distance = arrow_bbox[0] - element_bbox[2]
                    # ✅ FIXED: Find the CLOSEST left element, no distance limit
                    if distance < best_distance:
                        best_distance = distance
                        best_candidate = element
        
        if best_candidate:
            self.console.print(f"[dim]🔍 Found immediate left element: {best_candidate.get('g_icon_name', 'unknown')} (distance: {best_distance}px)[/dim]")
        
        return best_candidate
    
    def _guess_interaction_type(self, element_data: Dict) -> str:
        """Guess interaction type based on element properties"""
        name = element_data.get('g_icon_name', '').lower()
        brief = element_data.get('g_brief', '').lower()
        
        if 'menu' in brief or 'opens the' in brief:
            return 'menu'
        elif 'button' in name or 'click' in brief:
            return 'button'
        elif 'text' in element_data.get('type', ''):
            return 'text_field'
        else:
            return 'unknown'
    
    def _save_element_crops(self, screenshot_path: str, fdom_nodes: Dict, state_id: str, source_element_name: Optional[str] = None):
        """FIXED: Handle semantic names and create proper subfolders"""
        try:
            # Determine crops subfolder
            if source_element_name and state_id != "root":
                # For child states: crops/View/, crops/File/, etc.
                clean_source = source_element_name.replace(' ', '_').replace('/', '_')
                crops_subfolder = self.crops_dir / clean_source
            else:
                # For root state: crops/ (no subfolder)
                crops_subfolder = self.crops_dir
            
            # Debug logging
            self.console.print(f"[yellow]📸 Cropping from: {screenshot_path}[/yellow]")
            self.console.print(f"[yellow]📁 Saving to: {crops_subfolder}[/yellow]")
            self.console.print(f"[yellow]📊 Processing {len(fdom_nodes)} nodes[/yellow]")
            
            # Ensure crops directory exists
            crops_subfolder.mkdir(parents=True, exist_ok=True)
            
            # Load original image
            original_image = Image.open(screenshot_path)
            self.console.print(f"[green]✅ Image loaded: {original_image.size}[/green]")
            
            saved_count = 0
            
            with Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=self.console
            ) as progress:
                
                task = progress.add_task("Saving element crops...", total=len(fdom_nodes))
                
                for element_name, node_data in fdom_nodes.items():
                    bbox = node_data.get('bbox', [])
                    m_id = node_data.get('m_id', 'Unknown')
                    icon_name = self._sanitize_filename(node_data.get('g_icon_name', 'Unknown'))
                    
                    if len(bbox) == 4:
                        # Crop element
                        x1, y1, x2, y2 = bbox
                        
                        # Validate coordinates
                        if x1 >= 0 and y1 >= 0 and x2 > x1 and y2 > y1:
                            try:
                                cropped = original_image.crop((x1, y1, x2, y2))
                                
                                # Save with naming convention: ElementID_MID_IconName_StateID.png
                                crop_filename = f"{element_name}_{m_id}_{icon_name}_{state_id}.png"
                                crop_path = crops_subfolder / crop_filename
                                
                                cropped.save(crop_path)
                                saved_count += 1
                                
                                # Update node with crop path
                                node_data['crop_path'] = str(crop_path.relative_to(self.app_root))
                                
                                # self.console.print(f"[green]✅ Saved: {crop_filename}[/green]")
                            
                            except Exception as e:
                                self.console.print(f"[red]❌ Failed to save {element_name}: {e}[/red]")
                        else:
                            self.console.print(f"[red]❌ Invalid bbox for {element_name}: {bbox}[/red]")
                    else:
                        self.console.print(f"[red]❌ Missing bbox for {element_name}[/red]")
                    
                    progress.update(task, advance=1)
            
            # self.console.print(f"[green]✅ Saved {saved_count}/{len(fdom_nodes)} element crops to: {crops_subfolder}[/green]")
            
        except Exception as e:
            self.console.print(f"[red]❌ Failed to save crops: {str(e)}[/red]")
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for Windows compatibility"""
        # Windows invalid characters: < > : " | ? * \ /
        invalid_chars = '<>:"|?*\\/'
        
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        
        # Also handle special cases and whitespace
        filename = filename.replace(' ', '_')
        filename = filename.replace('(', '').replace(')', '')
        filename = filename.replace('[', '').replace(']', '')
        
        return filename
    
    def test_analysis(self, screenshot_path: str):
        """Test seraphine integration with a specific screenshot"""
        self.console.print(f"\n[bold blue]🧪 TESTING SERAPHINE INTEGRATION[/bold blue]")
        self.console.print(f"[cyan]Screenshot: {screenshot_path}[/cyan]")
        
        if not Path(screenshot_path).exists():
            self.console.print(f"[red]❌ Screenshot not found: {screenshot_path}[/red]")
            return
        
        # Run analysis
        result = self.analyze_screenshot(screenshot_path, "TEST")
        
        # Display results summary
        nodes = result.get('nodes', {})
        metadata = result.get('analysis_metadata', {})
        
        summary_text = f"""
        [bold green]Test Complete![/bold green]
        
        📊 Nodes Created: {len(nodes)}
        ⏱️  Analysis Time: {metadata.get('total_time', 0):.2f}s
        🎯 Icons Found: {metadata.get('total_icons_found', 0)}
        📁 Crops Saved: {self.crops_dir}
        """
        
        self.console.print(Panel(summary_text, title="🧪 Test Results"))
        
        return result

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Seraphine Integration")
    parser.add_argument("--test-analysis", help="Test with specific screenshot")
    parser.add_argument("--app-name", default="notepad", help="App name for testing")
    
    args = parser.parse_args()
    
    if args.test_analysis:
        integrator = SeraphineIntegrator(args.app_name)
        integrator.test_analysis(args.test_analysis)
    else:
        print("Usage: python seraphine_integrator.py --test-analysis path/to/screenshot.png") 