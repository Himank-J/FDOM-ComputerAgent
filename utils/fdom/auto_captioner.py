"""
Auto Captioner - Automatically discover tooltips/captions by hovering over elements
Uses SendInput to bypass Windows 10 SetCursorPos bug for proper hover events
Extended with Seraphine Pipeline integration for Gemini analysis
"""
import time
import ctypes
import os
import asyncio
from pathlib import Path
from ctypes import wintypes
from typing import Dict, List, Optional, Tuple
from rich.console import Console
from rich.progress import Progress
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import io
import json

from .screenshot_manager import ScreenshotManager
from .visual_differ import VisualDiffer


class AutoCaptioner:
    """Automatically discover element captions by hovering and visual comparison"""
    
    def __init__(self, element_interactor):
        self.element_interactor = element_interactor
        self.app_controller = element_interactor.app_controller
        self.visual_differ = element_interactor.visual_differ
        self.console = Console()
        self.screenshot_manager = ScreenshotManager(self.app_controller, self.visual_differ, debug_mode=False)
        
        # DISABLE CONSOLE OUTPUT FOR SCREENSHOT MANAGER AND VISUAL DIFFER
        # Create a UTF-8 compatible null stream
        null_stream = io.StringIO()
        null_console = Console(file=null_stream, force_terminal=False)
        
        self.screenshot_manager.console = null_console
        self.visual_differ.console = null_console
        
        # Setup paths
        self.app_info = self.app_controller.current_app_info
        self.captions_dir = self.app_info["folder_paths"]["app_dir"] / "captions"
        self.captions_dir.mkdir(exist_ok=True)
        
        # Settings
        self.hover_wait_time = 3
        
        # Track our temporary files for cleanup
        self.temp_files = []
        
        # FDOM path
        self.fdom_path = self.app_info["folder_paths"]["app_dir"] / "fdom.json"
        
        # NEW: Track processing batch and results  
        self.ordered_node_ids = []  # Preserve order from discovered_captions
        self.processed_nodes = []   # All nodes in this batch (for marking as done)
        self.gemini_results = {}    # Store gemini results for fdom update
        
    def discover_all_captions(self, pending_list: List[str]) -> Dict[str, str]:
        """Main function: Discover captions for all pending elements and analyze with Gemini"""
        
        # Debug: Show what we're starting with
        self.console.print(f"[yellow]🔍 DEBUG: Input pending_list: {pending_list[:5]}...[/yellow]")
        
        # ✅ ENHANCED FILTERING: Filter out HL nodes AND already processed nodes
        filtered_list = []
        skipped_hl_nodes = []
        skipped_done_nodes = []
        
        for node_id in pending_list:
            # Handle both simple node IDs and state::node_id format
            actual_node_id = node_id.split("::")[-1] if "::" in node_id else node_id
            
            # Skip HL nodes
            if actual_node_id.startswith('HL'):
                skipped_hl_nodes.append(node_id)
                continue
            
            # ✅ NEW: Skip nodes that already have autocaptioning done
            if self._is_node_already_processed(node_id):
                skipped_done_nodes.append(node_id)
                continue
            
            filtered_list.append(node_id)
        
        # Report filtering results
        if skipped_hl_nodes:
            self.console.print(f"[yellow]⚠️ Skipped {len(skipped_hl_nodes)} HL nodes[/yellow]")
        if skipped_done_nodes:
            self.console.print(f"[yellow]⚠️ Skipped {len(skipped_done_nodes)} already processed nodes[/yellow]")
        
        # ✅ BACK TO WORKING VERSION: Sort by distance from trigger, prioritizing current state
        sorted_list = self._sort_nodes_by_distance_from_trigger(filtered_list)
        
        self.console.print(f"\n[bold green]🔍 AUTO CAPTIONER - Starting Discovery[/bold green]")
        self.console.print(f"[cyan]📊 Elements to process: {len(sorted_list)} (filtered from {len(pending_list)})[/cyan]")
        
        # Use sorted list instead of original pending_list
        if not sorted_list:
            self.console.print("[yellow]⚠️ No elements to process after filtering[/yellow]")
            return {}
        
        # Take global "before" screenshot
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        before_screenshot = self.screenshot_manager.take_screenshot(f"auto_caption_before_{timestamp}")
        self.temp_files.append(before_screenshot)
        
        if not before_screenshot:
            return {}
        
        # ✅ DYNAMIC EXPLORATION: Process elements with dynamic distance calculation
        discovered_captions = {}
        self.processed_nodes = pending_list.copy()
        
        # Track current position for dynamic distance calculation
        current_state_id = self.element_interactor.current_state_id
        fdom_data = self.element_interactor.state_manager.fdom_data
        current_state_data = fdom_data.get("states", {}).get(current_state_id, {})
        trigger_node = current_state_data.get("trigger_node")
        
        # ✅ ENHANCED: Initialize with trigger node corners
        if trigger_node:
            trigger_bbox = self._get_node_bbox(trigger_node)
            if trigger_bbox:
                self.current_corners = self._get_element_corners(trigger_bbox)
                center_coords = self._get_node_center_coordinates(trigger_node)
                self.current_hover_position = center_coords
            else:
                self.current_hover_position = None
                self.current_corners = []
        else:
            self.current_hover_position = None
            self.current_corners = []
        
        with Progress() as progress:
            task = progress.add_task("[cyan]Discovering captions...", total=len(sorted_list))
            
            # ✅ DYNAMIC: Update remaining list after each hover
            remaining_nodes = sorted_list.copy()
            
            for i in range(len(sorted_list)):
                if not remaining_nodes:
                    break
                
                # ✅ FIND NEXT: Always find closest to current position from remaining nodes
                next_node = self._find_closest_current_state_node(remaining_nodes)
                
                if not next_node:
                    # No more current state nodes, pick first remaining
                    next_node = remaining_nodes[0]
                
                remaining_nodes.remove(next_node)
                
                caption_result = self._discover_single_caption(next_node, before_screenshot, i+1, len(sorted_list))
                
                if caption_result:
                    discovered_captions[next_node] = caption_result
                
                # ✅ UPDATE: Current position after hover
                self._update_current_hover_position(next_node)
                
                progress.update(task, advance=1)
        
        # Store the order for mapping (use sorted order)
        self.ordered_node_ids = list(discovered_captions.keys())
        
        # 🤖 Seraphine Pipeline Analysis
        if discovered_captions:
            self.console.print(f"\n[bold cyan]🤖 Sending to Seraphine - Analyzing {len(discovered_captions)} captions with Gemini[/bold cyan]")
            asyncio.run(self._analyze_captions_with_seraphine(discovered_captions))
            
            # NOW add caption files to cleanup list AFTER Gemini analysis is complete
            for caption_path in discovered_captions.values():
                self.temp_files.append(caption_path)
        
        # 🔄 NEW: UPDATE FDOM with results
        self._update_fdom_with_results()
        
        # 🧹 CLEANUP: Delete all temporary files
        self._cleanup_temp_files()
        self._cleanup_seraphine_files()
        
        # Summary
        self.console.print(f"\n[bold green]✅ AUTO CAPTIONER COMPLETE[/bold green]")
        
        return discovered_captions
    
    async def _analyze_captions_with_seraphine(self, discovered_captions: Dict[str, str]) -> None:
        """Analyze discovered caption images using PROPER seraphine pipeline infrastructure"""
        try:
            # 🔥 CREATE FAKE DETECTION DATA FOR SERAPHINE
            fake_detections = self._create_fake_detections_for_captions(discovered_captions)
            
            # 🔥 USE SERAPHINE PROCESSOR TO CREATE PROPER IMAGES
            from utils.seraphine_pipeline.seraphine_processor import FinalSeraphineProcessor
            
            # Create processor with proper parameters
            processor = FinalSeraphineProcessor(enable_timing=False, enable_debug=False)
            
            # Process the fake detections (creates groups, final_groups, etc.)
            seraphine_analysis = processor.process_detections(fake_detections)
            
            # Create a dummy image (we'll replace the crops with our caption images)
            dummy_image_path = self._create_dummy_background_image()
            
            # 🔥 REPLACE BBOX PROCESSOR CROPS WITH OUR CAPTION IMAGES
            bbox_processor = seraphine_analysis['bbox_processor']
            self._inject_caption_images_into_processor(bbox_processor, discovered_captions)
            
            # 🔥 USE SERAPHINE'S IMAGE GENERATOR (1280x1280, proper layout, lightgray borders, labels)
            from utils.seraphine_pipeline.seraphine_generator import FinalGroupImageGenerator
            
            generator = FinalGroupImageGenerator(
                output_dir=str(self.captions_dir),
                save_mapping=False,
                enable_debug=False
            )
            
            # Generate properly formatted seraphine images
            result = generator.create_grouped_images(
                image_path=dummy_image_path,
                seraphine_analysis=seraphine_analysis,
                filename_base="caption_analysis",
                return_direct_images=True
            )
            
            # 🔧 FIX: Check if any images have "combined" in the name
            combined_images = [(img, filename) for img, filename in result['direct_images'] if "combined" in filename]
            
            if not combined_images:
                return
            
            # 🔥 USE SERAPHINE'S GEMINI ANALYZER
            from utils.seraphine_pipeline.gemini_analyzer import GeminiIconAnalyzer
            
            analyzer = GeminiIconAnalyzer(
                prompt_path=None,  # Use default prompt
                output_dir=str(self.captions_dir),
                max_concurrent_requests=1,
                save_results=False
            )
            
            # Use only the combined images
            gemini_results = await analyzer.analyze_grouped_images(
                grouped_image_paths=None,
                filename_base="caption_analysis",
                direct_images=combined_images  # Only send combined images
            )
            
            # 🔧 NEW: Process Gemini results and map back to original fdom IDs
            self._process_gemini_results(gemini_results, discovered_captions)
            
            # Display results
            self._display_gemini_caption_results(gemini_results, discovered_captions)
            
            # 🧹 IMMEDIATE CLEANUP: Add dummy file to cleanup list right after Gemini is done
            self.temp_files.append(dummy_image_path)
            
        except Exception as e:
            pass
    
    def _create_fake_detections_for_captions(self, discovered_captions: Dict[str, str]) -> Dict:
        """Create fake detection data that seraphine can process"""
        fake_detections = []
        
        for i, (node_id, caption_path) in enumerate(discovered_captions.items()):
            if os.path.exists(caption_path):
                # Get image dimensions
                from PIL import Image
                with Image.open(caption_path) as img:
                    width, height = img.size
                
                # Create fake detection with proper structure for VERTICAL grouping
                # Spread them out vertically so they get grouped into V0, V1, V2...
                fake_y_position = i * 100  # Space them out vertically
                
                fake_detection = {
                    'bbox': [10, fake_y_position, 10 + width, fake_y_position + height],
                    'id': i + 1,
                    'merged_id': i + 1,
                    'type': 'text',  # Caption is text
                    'source': 'caption',
                    'confidence': 1.0,
                    'explore': True,  # NEW: Force explore=True for auto-captioner
                }
                fake_detections.append(fake_detection)
        
        # Create fake detection results structure (matching expected format)
        return fake_detections  # Just return the list, not the dict!
    
    def _create_dummy_background_image(self) -> str:
        """Create a dummy white background image for seraphine"""
        from PIL import Image
        
        # Create white background
        dummy_image = Image.new('RGB', (1280, 1280), 'white')
        
        # Save it
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dummy_path = str(self.captions_dir / f"dummy_background_{timestamp}.png")
        dummy_image.save(dummy_path)
        
        # EXPLICITLY close the image to release file handle
        dummy_image.close()
        
        return dummy_path
    
    def _inject_caption_images_into_processor(self, bbox_processor, discovered_captions: Dict[str, str]) -> None:
        """Replace bbox processor's crop method to return our caption images"""
        
        # Create mapping from merged_id to caption path
        caption_mapping = {}
        for i, (node_id, caption_path) in enumerate(discovered_captions.items()):
            caption_mapping[i + 1] = caption_path  # merged_id starts from 1
        
        # Store original method
        original_crop_method = bbox_processor.crop_bbox_from_image
        
        # Create our replacement method
        def custom_crop_bbox_from_image(bbox):
            """Custom crop method that returns our caption images"""
            merged_id = bbox.merged_id
            if merged_id in caption_mapping:
                caption_path = caption_mapping[merged_id]
                if os.path.exists(caption_path):
                    from PIL import Image
                    return Image.open(caption_path)
            
            # Fallback to original method
            return original_crop_method(bbox)
        
        # Replace the method
        bbox_processor.crop_bbox_from_image = custom_crop_bbox_from_image
    
    def _display_gemini_caption_results(self, results: Dict, discovered_captions: Dict[str, str]) -> None:
        """Display Gemini analysis results for captions"""
        if not results or not results.get('images'):
            return
        
        self.console.print(f"\n[bold green]🤖 FOUND CAPTIONS[/bold green]")
        
        total_analyzed = 0
        for image_result in results['images']:
            if image_result['analysis_success'] and image_result.get('icons'):
                for icon in image_result['icons']:
                    # Show only top 4 results
                    if total_analyzed >= 4:
                        break
                        
                    icon_id = icon.get('id', 'unknown')
                    icon_name = icon.get('name', 'unknown')
                    usage = icon.get('usage', 'No description')
                    
                    # self.console.print(f"[cyan]📝 {icon_id}:[/cyan] [bold]{icon_name}[/bold]")
                    # self.console.print(f"    💬 {usage}")
                    # self.console.print()
                    total_analyzed += 1
                    
                if total_analyzed >= 4:
                    break
            
            if total_analyzed >= 4:
                break
    
    def _cleanup_temp_files(self) -> None:
        """Clean up all temporary files created during the session"""
        if not self.temp_files:
            return
        
        self.console.print(f"\n[yellow]🧹 Deleting {len(self.temp_files)} temporary files...[/yellow]")
        
        # Force garbage collection to release any file handles
        import gc
        gc.collect()
        
        # Add delay to ensure file handles are released
        time.sleep(0.3)
        
        cleaned_count = 0
        for temp_file in self.temp_files:
            try:
                if temp_file and os.path.exists(temp_file):
                    # Try multiple times with delays if file is locked
                    for attempt in range(3):
                        try:
                            os.remove(temp_file)
                            cleaned_count += 1
                            break
                        except PermissionError:
                            if attempt < 2:  # Not the last attempt
                                time.sleep(0.2)
                                gc.collect()
                            else:
                                # If still locked after 3 attempts, skip it
                                pass
            except Exception:
                pass
        
        self.temp_files.clear()
    
    def _cleanup_seraphine_files(self) -> None:
        """Clean up seraphine-generated files in captions directory"""
        try:
            # Force garbage collection to release any file handles
            import gc
            gc.collect()
            
            # Add delay to ensure file handles are released
            time.sleep(0.5)
            
            seraphine_patterns = [
                "combined_groups_*.png",
                "caption_analysis_*.png", 
                "dummy_background_*.png"
            ]
            
            import glob
            files_deleted = 0
            
            for pattern in seraphine_patterns:
                pattern_path = str(self.captions_dir / pattern)
                for file_path in glob.glob(pattern_path):
                    try:
                        if os.path.exists(file_path):
                            # Try multiple times with delays if file is locked
                            for attempt in range(5):  # More attempts for stubborn files
                                try:
                                    os.remove(file_path)
                                    files_deleted += 1
                                    break
                                except PermissionError:
                                    if attempt < 4:  # Not the last attempt
                                        time.sleep(0.3)
                                        gc.collect()
                                    else:
                                        # If still locked after 5 attempts, skip it
                                        pass
                    except Exception:
                        pass
            
            if files_deleted > 0:
                self.console.print(f"[yellow]🧹 Cleaned up {files_deleted} seraphine files[/yellow]")
                
        except Exception:
            pass
    
    def _send_input_hover(self, abs_x: int, abs_y: int, element_name: str) -> bool:
        """Send actual WM_MOUSEMOVE messages using SendInput to trigger hover events"""
        try:
            # Get current position
            current_pos = self.app_controller.gui_api.get_cursor_position()
            start_x, start_y = current_pos if current_pos else (abs_x - 50, abs_y - 20)
            
            # Define Windows structures
            class MOUSEINPUT(ctypes.Structure):
                _fields_ = [
                    ("dx", ctypes.c_long),
                    ("dy", ctypes.c_long),
                    ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))
                ]
            
            class INPUT(ctypes.Structure):
                class _INPUT(ctypes.Union):
                    _fields_ = [("mi", MOUSEINPUT)]
                _anonymous_ = ("_input",)
                _fields_ = [
                    ("type", wintypes.DWORD),
                    ("_input", _INPUT)
                ]
            
            user32 = ctypes.windll.user32
            
            # Get screen dimensions
            screen_width = user32.GetSystemMetrics(0)
            screen_height = user32.GetSystemMetrics(1)
            
            # Send smooth movement using SendInput
            steps = 15
            for i in range(steps + 1):
                progress = i / steps
                eased_progress = 1 - (1 - progress) ** 2  # Ease-out
                
                current_x = int(start_x + (abs_x - start_x) * eased_progress)
                current_y = int(start_y + (abs_y - start_y) * eased_progress)
                
                # Convert to SendInput coordinates (0-65535 range)
                input_x = int((current_x * 65535) / screen_width)
                input_y = int((current_y * 65535) / screen_height)
                
                # Create input structure
                inp = INPUT()
                inp.type = 0  # INPUT_MOUSE
                inp.mi.dx = input_x
                inp.mi.dy = input_y
                inp.mi.mouseData = 0
                inp.mi.dwFlags = 0x8001  # MOUSEEVENTF_MOVE + MOUSEEVENTF_ABSOLUTE
                inp.mi.time = 0
                inp.mi.dwExtraInfo = None
                
                # Send the input
                result = user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
                if result != 1:
                    return False
                
                time.sleep(0.02)
            
            # Hold position for hover duration
            time.sleep(self.hover_wait_time)
            
            return True
            
        except Exception:
            return False
    
    def _discover_single_caption(self, unique_node_id: str, before_screenshot: str, index: int, total: int) -> Optional[str]:
        """Discover caption for a single element"""
        try:
            # Parse node ID
            if "::" in unique_node_id:
                state_name, node_id = unique_node_id.split("::", 1)
            else:
                node_id = unique_node_id
            
            # Find node data
            node_data = self.element_interactor._find_node_in_fdom(unique_node_id)
            if not node_data:
                return None
            
            element_name = node_data.get('g_icon_name', 'unknown')
            bbox = node_data.get('bbox', [])
            
            if not bbox or len(bbox) != 4:
                return None
            
            # ✅ FIX: Calculate hover position 20px from left edge instead of center
            hover_x = bbox[0] + 20  # Left edge + 20px
            hover_y = (bbox[1] + bbox[3]) // 2  # Vertical center
            
            # Get window position
            window_pos = self._get_window_position()
            if not window_pos:
                return None
            
            # Convert to absolute coordinates
            abs_x = window_pos['x'] + hover_x
            abs_y = window_pos['y'] + hover_y
            
            # ✅ DEBUG: Show hover position for first few elements
            if index <= 3:
                self.console.print(f"[cyan]🎯 Hovering on {element_name} at left+20px: ({hover_x}, {hover_y}) → abs ({abs_x}, {abs_y})[/cyan]")
            
            # Perform SendInput hover
            hover_success = self._send_input_hover(abs_x, abs_y, element_name)
            if not hover_success:
                return None
            
            # Take after screenshot
            after_screenshot = self.screenshot_manager.take_screenshot(f"auto_caption_after_{node_id}")
            if not after_screenshot:
                return None
            
            self.temp_files.append(after_screenshot)
            
            # Create diff output path
            safe_element_name = element_name.encode('ascii', 'ignore').decode('ascii').replace(' ', '_').replace('°', 'deg')
            crop_filename = f"caption_{node_id}_{safe_element_name}.png"
            diff_output_path = str(self.captions_dir / crop_filename)
            
            # Compare screenshots - use hover position for click_coords
            diff_result = self.visual_differ.extract_change_regions(
                before_screenshot,
                after_screenshot,
                diff_output_path,
                click_coords=(abs_x, abs_y)
            )
            
            # Check results
            if diff_result.get("success", False) and diff_result.get("regions", []):
                return diff_output_path
            else:
                return None
            
        except Exception:
            return None
    
    def _get_window_position(self) -> Optional[Dict]:
        """Get current window position"""
        try:
            window_id = self.app_controller.current_app_info["window_id"]
            window_info = self.app_controller.gui_api.get_window_info(window_id)
            
            if window_info and 'window_data' in window_info and 'position' in window_info['window_data']:
                position = window_info['window_data']['position']
                if 'x' in position and 'y' in position:
                    return position
            
            return None
            
        except Exception:
            return None

    def _create_string_sort_mapping(self, num_items: int) -> Dict[str, int]:
        """Create mapping from string-sorted Gemini IDs back to original order indices"""
        
        # Generate the group IDs seraphine will create: H0, H1, H2, ..., H(num_items-1)
        seraphine_groups = [f"H{i}" for i in range(num_items)]
        
        # Sort them the same way Python/Gemini does (string sort)
        string_sorted_groups = sorted(seraphine_groups)
        
        # Create mapping: string-sorted Gemini ID -> original index
        mapping = {}
        for gemini_index, group_id in enumerate(string_sorted_groups):
            # Extract original index from group ID
            original_index = int(group_id[1:])  # H10 -> 10
            gemini_id = f"{group_id}_1"  # H10_1
            mapping[gemini_id] = original_index
            
            # self.console.print(f"[cyan]🗺️ String-sort mapping: {gemini_id} -> original index {original_index}[/cyan]")
        
        return mapping

    def _process_gemini_results(self, gemini_results: Dict, discovered_captions: Dict[str, str]) -> None:
        """Process Gemini results using string-sort-aware mapping"""
        try:
            if not gemini_results or not gemini_results.get('images'):
                self.console.print("[yellow]⚠️ No gemini_results or images found[/yellow]")
                return
            
            # Create string-sort mapping
            num_items = len(self.ordered_node_ids)
            string_sort_mapping = self._create_string_sort_mapping(num_items)
            
            self.console.print(f"[cyan]🔍 Processing Gemini results with string-sort compensation[/cyan]")
            self.console.print(f"[cyan]📊 Processing {len(gemini_results['images'])} image results[/cyan]")
            
            total_processed = 0
            for image_result in gemini_results['images']:
                if image_result['analysis_success'] and image_result.get('icons'):
                    self.console.print(f"[green]✅ Image success: {len(image_result['icons'])} icons found[/green]")
                    for icon in image_result['icons']:
                        # Extract Gemini icon ID (H0_1, H1_1, H10_1, etc.)
                        gemini_id = icon.get('id', 'unknown')
                        
                        # Look up original index using string-sort mapping
                        if gemini_id in string_sort_mapping:
                            original_index = string_sort_mapping[gemini_id]
                            
                            # Get original fdom ID using the index
                            if 0 <= original_index < len(self.ordered_node_ids):
                                original_fdom_id = self.ordered_node_ids[original_index]
                                
                                # Store processed result
                                self.gemini_results[original_fdom_id] = {
                                    'icon_name': icon.get('name', ''),
                                    'usage': icon.get('usage', '')
                                }
                                total_processed += 1
                                
                                if total_processed <= 5:  # Show first 5 for debugging
                                    self.console.print(f"[green]✅ String-sort mapped {gemini_id} -> index {original_index} -> {original_fdom_id}: {icon.get('name', 'Unknown')}[/green]")
                            else:
                                self.console.print(f"[yellow]⚠️ Index out of range: {original_index}[/yellow]")
                        else:
                            self.console.print(f"[yellow]⚠️ No string-sort mapping found for Gemini ID: {gemini_id}[/yellow]")
                else:
                    self.console.print(f"[yellow]⚠️ Image failed or no icons: {image_result.get('analysis_success', False)}[/yellow]")
            
            self.console.print(f"[green]✅ Auto-captioner processed {total_processed} Gemini results into self.gemini_results[/green]")
                            
        except Exception as e:
            self.console.print(f"[red]❌ Error processing Gemini results: {str(e)}[/red]")
            import traceback
            self.console.print(f"[red]📋 Traceback: {traceback.format_exc()}[/red]")

    def _update_fdom_with_results(self) -> None:
        """Update fdom.json with gemini results and mark all nodes as processed"""
        try:
            # Load current fdom
            if not self.fdom_path.exists():
                self.console.print("[red]❌ fdom.json not found![/red]")
                return
            
            with open(self.fdom_path, 'r', encoding='utf-8') as f:
                fdom_data = json.load(f)
            
            updates_made = 0
            gemini_updates_made = 0
            
            self.console.print(f"[cyan]🔄 Updating fDOM with {len(self.gemini_results)} Gemini results[/cyan]")
            
            # Process all nodes in batch
            for node_id in self.processed_nodes:
                # Parse state and node ID
                if "::" in node_id:
                    state_name, actual_node_id = node_id.split("::", 1)
                else:
                    state_name = "root"
                    actual_node_id = node_id
                
                # Navigate to the node
                if (state_name in fdom_data.get("states", {}) and 
                    actual_node_id in fdom_data["states"][state_name].get("nodes", {})):
                    
                    node_data = fdom_data["states"][state_name]["nodes"][actual_node_id]
                    
                    # Mark as processed (for all nodes, including HL)
                    node_data["autocaptioning"] = "done"
                    updates_made += 1
                    
                    # Update with Gemini results (only for non-HL nodes with results)
                    if node_id in self.gemini_results and not actual_node_id.startswith('HL'):
                        gemini_result = self.gemini_results[node_id]
                        
                        # Update icon name: new + ", " + original
                        original_icon_name = node_data.get("g_icon_name", "")
                        new_icon_name = gemini_result.get("icon_name", "")
                        if new_icon_name:
                            node_data["g_icon_name"] = f"{new_icon_name}, {original_icon_name}"
                            gemini_updates_made += 1
                            
                            if gemini_updates_made <= 3:  # Show first 3 updates
                                self.console.print(f"[green]✅ Updated {actual_node_id}: '{new_icon_name}' + '{original_icon_name}'[/green]")
                        
                        # Update brief: OVERWRITE with new usage
                        new_usage = gemini_result.get("usage", "")
                        if new_usage:
                            node_data["g_brief"] = new_usage  # Direct overwrite, no comma
            
            # Save updated fdom
            if updates_made > 0:
                with open(self.fdom_path, 'w', encoding='utf-8') as f:
                    json.dump(fdom_data, f, indent=2, ensure_ascii=False)
                
                self.element_interactor.state_manager.fdom_data = fdom_data
                self.element_interactor.state_manager._rebuild_tracking_sets()
                self.console.print(f"[green]✅ Updated fdom.json - {updates_made} nodes marked as processed, {gemini_updates_made} got Gemini updates[/green]")
            
        except Exception as e:
            self.console.print(f"[red]❌ Failed to update fdom.json: {str(e)}[/red]")
            import traceback
            self.console.print(f"[red]📋 Traceback: {traceback.format_exc()}[/red]")

    def _is_node_already_processed(self, node_id: str) -> bool:
        """Check if node already has autocaptioning done"""
        try:
            # Load current fdom
            if not self.fdom_path.exists():
                return False
            
            with open(self.fdom_path, 'r', encoding='utf-8') as f:
                fdom_data = json.load(f)
            
            # Parse node ID
            if "::" in node_id:
                state_name, actual_node_id = node_id.split("::", 1)
            else:
                state_name = "root"
                actual_node_id = node_id
            
            # Check if node exists and has autocaptioning done
            if (state_name in fdom_data.get("states", {}) and 
                actual_node_id in fdom_data["states"][state_name].get("nodes", {})):
                
                node_data = fdom_data["states"][state_name]["nodes"][actual_node_id]
                return node_data.get("autocaptioning") == "done"
            
            return False
            
        except Exception:
            return False

    def _sort_nodes_by_distance_from_trigger(self, node_list: List[str]) -> List[str]:
        """Sort nodes by distance from trigger, prioritizing current state"""
        try:
            if not node_list:
                return node_list
            
            # Get trigger node as starting point
            current_state_id = self.element_interactor.current_state_id
            fdom_data = self.element_interactor.state_manager.fdom_data
            current_state_data = fdom_data.get("states", {}).get(current_state_id, {})
            trigger_node = current_state_data.get("trigger_node")
            
            if not trigger_node:
                self.console.print(f"[yellow]⚠️ No trigger node - using original order[/yellow]")
                return node_list
            
            # Get starting coordinates (trigger node)
            current_pos = self._get_node_center_coordinates(trigger_node)
            if not current_pos:
                self.console.print(f"[yellow]⚠️ No trigger coordinates - using original order[/yellow]")
                return node_list
            
            current_x, current_y = current_pos
            self.console.print(f"[cyan]📍 Starting enhanced nearest neighbor from trigger {trigger_node} at ({current_x}, {current_y})[/cyan]")
            
            # ✅ PRIORITIZE: Current state elements first, then others
            current_state_nodes = [n for n in node_list if n.startswith(f"{current_state_id}::")]
            other_state_nodes = [n for n in node_list if not n.startswith(f"{current_state_id}::")]
            
            # ✅ ENHANCED: Use 4-corner distance algorithm for current state elements
            current_ordered = self._enhanced_nearest_neighbor_order(current_state_nodes, current_x, current_y)
            
            # ✅ STATIC DISTANCE: Other elements sorted by distance from trigger
            other_ordered = []
            if other_state_nodes:
                other_distances = []
                for node_id in other_state_nodes:
                    node_coords = self._get_node_center_coordinates(node_id)
                    if node_coords:
                        node_x, node_y = node_coords
                        distance = ((node_x - current_x) ** 2 + (node_y - current_y) ** 2) ** 0.5
                        other_distances.append((node_id, distance))
                    else:
                        other_distances.append((node_id, 9999))
                
                other_distances.sort(key=lambda x: x[1])
                other_ordered = [node_id for node_id, _ in other_distances]
            
            # Combine: Current state (enhanced nearest neighbor) + Other states (distance sorted)
            final_order = current_ordered + other_ordered
            
            # Show the exploration path
            self.console.print(f"[green]🎯 Enhanced nearest neighbor exploration path:[/green]")
            if current_ordered:
                self.console.print(f"[green]📋 Current state path ({len(current_ordered)} elements):[/green]")
                for i, node_id in enumerate(current_ordered[:5]):
                    actual_node_id = node_id.split("::")[-1] if "::" in node_id else node_id
                    self.console.print(f"[green]  {i+1}. {actual_node_id}[/green]")
                
                if len(current_ordered) > 5:
                    self.console.print(f"[green]  ... and {len(current_ordered) - 5} more[/green]")
            
            return final_order
            
        except Exception as e:
            self.console.print(f"[yellow]⚠️ Error in enhanced nearest neighbor exploration: {e}[/yellow]")
            return node_list

    def _enhanced_nearest_neighbor_order(self, node_list: List[str], start_x: int, start_y: int) -> List[str]:
        """Enhanced nearest neighbor: considers all 4 corners of each element for optimal pathfinding"""
        if not node_list:
            return []
        
        unvisited = node_list.copy()
        ordered = []
        current_corners = [(start_x, start_y)]  # Start with trigger point
        
        self.console.print(f"[cyan]🔍 Starting enhanced pathfinding with {len(node_list)} elements[/cyan]")
        
        while unvisited:
            best_node = None
            best_distance = float('inf')
            best_connection = None  # Store which corners connect
            
            # 🎯 FIND MINIMUM: Test all current corners → all target corners
            for node_id in unvisited:
                node_bbox = self._get_node_bbox(node_id)
                if not node_bbox:
                    continue
                    
                # Get all 4 corners of candidate element
                target_corners = self._get_element_corners(node_bbox)
                
                # Test all combinations of current corners → target corners
                for current_corner in current_corners:
                    for i, target_corner in enumerate(target_corners):
                        distance = self._calculate_distance(current_corner, target_corner)
                        
                        if distance < best_distance:
                            best_distance = distance
                            best_node = node_id
                            corner_names = ["top-left", "top-right", "bottom-left", "bottom-right"]
                            best_connection = (current_corner, target_corner, corner_names[i])
            
            if best_node:
                ordered.append(best_node)
                unvisited.remove(best_node)
                
                # 🚀 UPDATE: Current position is now ALL corners of the selected element
                best_bbox = self._get_node_bbox(best_node)
                if best_bbox:
                    current_corners = self._get_element_corners(best_bbox)
                    
                    # Debug: Show the optimal connection for first few elements
                    if len(ordered) <= 3:
                        actual_node_id = best_node.split("::")[-1] if "::" in best_node else best_node
                        self.console.print(f"[green]🔗 {actual_node_id}: {best_connection[0]} → {best_connection[1]} ({best_connection[2]}, {best_distance:.1f}px)[/green]")
                else:
                    # Fallback to single point if bbox fails
                    current_corners = [best_connection[1]] if best_connection else [(start_x, start_y)]
        
        return ordered

    def _get_element_corners(self, bbox: List[int]) -> List[Tuple[int, int]]:
        """Get all 4 corners of an element"""
        if len(bbox) != 4:
            return []
        
        x1, y1, x2, y2 = bbox
        
        # Return all 4 corners: top-left, top-right, bottom-left, bottom-right
        corners = [
            (x1, y1),      # Top-left
            (x2, y1),      # Top-right  
            (x1, y2),      # Bottom-left
            (x2, y2)       # Bottom-right
        ]
        
        return corners

    def _get_node_bbox(self, node_id: str) -> Optional[List[int]]:
        """Get the bounding box of a node"""
        try:
            # Handle state::node_id format
            if "::" in node_id:
                state_name, actual_node_id = node_id.split("::", 1)
            else:
                state_name = self.element_interactor.current_state_id
                actual_node_id = node_id
            
            # Get node data from FDOM
            fdom_data = self.element_interactor.state_manager.fdom_data
            state_data = fdom_data.get("states", {}).get(state_name, {})
            nodes = state_data.get("nodes", {})
            
            if actual_node_id not in nodes:
                return None
            
            node_data = nodes[actual_node_id]
            bbox = node_data.get('bbox', [])
            
            # Validate bbox format
            if len(bbox) != 4:
                return None
            
            return bbox
            
        except Exception:
            return None

    def _calculate_distance(self, point1: Tuple[int, int], point2: Tuple[int, int]) -> float:
        """Calculate Euclidean distance between two points"""
        x1, y1 = point1
        x2, y2 = point2
        return ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5

    def _find_closest_current_state_node(self, remaining_nodes: List[str]) -> Optional[str]:
        """Enhanced: Find closest current state node using 4-corner analysis"""
        if not remaining_nodes or not self.current_hover_position:
            return remaining_nodes[0] if remaining_nodes else None
        
        current_state_id = self.element_interactor.current_state_id
        
        # Filter to current state nodes only
        current_state_nodes = [n for n in remaining_nodes if n.startswith(f"{current_state_id}::")]
        
        if not current_state_nodes:
            # No more current state nodes, return first remaining (other state)
            return remaining_nodes[0]
        
        # ✅ ENHANCED: Use corner-to-corner distance instead of center-to-center
        current_corners = [self.current_hover_position]  # Current position
        
        best_node = None
        best_distance = float('inf')
        
        for node_id in current_state_nodes:
            node_bbox = self._get_node_bbox(node_id)
            if node_bbox:
                target_corners = self._get_element_corners(node_bbox)
                
                # Find minimum distance from current position to any corner of target
                for current_corner in current_corners:
                    for target_corner in target_corners:
                        distance = self._calculate_distance(current_corner, target_corner)
                        
                        if distance < best_distance:
                            best_distance = distance
                            best_node = node_id
        
        return best_node or current_state_nodes[0]

    def _update_current_hover_position(self, node_id: str):
        """Enhanced: Update current hover position to ALL corners of the element"""
        node_bbox = self._get_node_bbox(node_id)
        if node_bbox:
            # Store all corners of current element for next distance calculation
            corners = self._get_element_corners(node_bbox)
            if corners:
                # For simplicity, use center of element as current position
                # But store corners in self.current_corners for enhanced algorithm
                x1, y1, x2, y2 = node_bbox
                center_x = (x1 + x2) // 2
                center_y = (y1 + y2) // 2
                self.current_hover_position = (center_x, center_y)
                
                # Also store corners for enhanced algorithm
                self.current_corners = corners
                
                # Debug for first few elements
                if hasattr(self, '_debug_counter'):
                    self._debug_counter += 1
                else:
                    self._debug_counter = 1
                    
                if self._debug_counter <= 3:
                    actual_node_id = node_id.split("::")[-1] if "::" in node_id else node_id
                    self.console.print(f"[dim]📍 Updated position: {actual_node_id} center={self.current_hover_position}, corners={len(corners)}[/dim]")

    def _get_node_center_coordinates(self, node_id: str) -> Optional[Tuple[int, int]]:
        """Get center coordinates of a node"""
        bbox = self._get_node_bbox(node_id)
        if bbox:
            x1, y1, x2, y2 = bbox
            center_x = (x1 + x2) // 2
            center_y = (y1 + y2) // 2
            return (center_x, center_y)
        return None
