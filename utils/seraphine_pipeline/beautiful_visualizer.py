"""
Beautiful visualization utility inspired by omni_utils.py
Creates stunning bounding box visualizations for all pipeline results
"""

import os
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional
from .helpers import debug_print


class BeautifulVisualizer:
    """
    Creates beautiful visualizations for detection pipeline results
    Inspired by omni_utils.py with enhanced styling and Seraphine integration
    """
    
    def __init__(self, output_dir: str = "outputs", config: Dict = None):
        self.output_dir = output_dir
        self.config = config or {}
        os.makedirs(output_dir, exist_ok=True)
        
        # Color schemes
        self.colors = {
            'yolo': (63, 81, 181),      # Blue - YOLO detections
            'ocr': (46, 125, 50),       # Green - OCR detections  
            'merged': (156, 39, 176),   # Purple - Merged results
            'complete': (255, 152, 0),  # Orange - Complete results
            'grouped': (244, 67, 54),   # Red - Grouped items
            'ungrouped': (96, 125, 139) # Gray - Ungrouped items
        }
        
        # Group colors for Seraphine visualization (from seraphine_check.py)
        self.seraphine_colors = [
            (255, 0, 0),    # Red
            (0, 255, 0),    # Green
            (0, 0, 255),    # Blue
            (255, 255, 0),  # Yellow
            (255, 0, 255),  # Magenta
            (0, 255, 255),  # Cyan
            (255, 165, 0),  # Orange
            (128, 0, 128),  # Purple
            (255, 192, 203), # Pink
            (0, 128, 0),    # Dark Green
            (128, 128, 0),  # Olive
            (0, 0, 128),    # Navy
            (128, 0, 0),    # Maroon
            (0, 128, 128),  # Teal
            (192, 192, 192), # Silver
            (255, 20, 147), # Deep Pink
            (50, 205, 50),  # Lime Green
            (255, 140, 0),  # Dark Orange
            (138, 43, 226), # Blue Violet
            (220, 20, 60),  # Crimson
        ]
    
    def create_all_visualizations(self, image_path: str, results: Dict[str, Any], 
                                filename_base: str = None) -> Dict[str, str]:
        """
        Create all visualizations based on config settings
        
        Args:
            image_path: Path to original image
            results: Dictionary containing all detection results
            filename_base: Base filename (auto-detected if None)
            
        Returns:
            Dictionary mapping visualization type to saved file path
        """
        # Check if visualizations are enabled in config
        if not self.config.get("save_visualizations", True):
            debug_print("⏭️  Visualizations disabled in config (save_visualizations: false)")
            return {}
        
        debug_print(f"🎨 Creating beautiful visualizations...")
        
        # Load image
        image = Image.open(image_path).convert('RGB')
        
        # Auto-detect filename if not provided
        if filename_base is None:
            filename_base = os.path.splitext(os.path.basename(image_path))[0]
        
        visualization_paths = {}
        
        # 1. YOLO Results Visualization
        if 'yolo_detections' in results and self.config.get("save_yolo_viz", True):
            yolo_path = self._create_detection_visualization(
                image, results['yolo_detections'], 'yolo', filename_base
            )
            visualization_paths['yolo'] = yolo_path
        
        # 2. OCR Detection Results Visualization  
        if 'ocr_detections' in results and self.config.get("save_ocr_viz", True):
            ocr_path = self._create_detection_visualization(
                image, results['ocr_detections'], 'ocr', filename_base
            )
            visualization_paths['ocr'] = ocr_path
        
        # 3. Merged Results Visualization
        if 'merged_detections' in results and self.config.get("save_merged_viz", True):
            merged_path = self._create_detection_visualization(
                image, results['merged_detections'], 'merged', filename_base
            )
            visualization_paths['merged'] = merged_path
        
        # 4. Complete Results Visualization (final summary - all detections)
        if self.config.get("save_complete_viz", True):
            complete_detections = []
            if 'yolo_detections' in results:
                complete_detections.extend(results['yolo_detections'])
            if 'ocr_detections' in results:
                complete_detections.extend(results['ocr_detections'])
            
            if complete_detections:
                complete_path = self._create_detection_visualization(
                    image, complete_detections, 'complete', filename_base
                )
                visualization_paths['complete'] = complete_path
        
        debug_print(f"✅ Created {len(visualization_paths)} beautiful visualizations")
        return visualization_paths
    
    def create_seraphine_group_visualization(self, image_path: str, seraphine_analysis: Dict, 
                                           filename_base: str = None) -> Optional[str]:
        """
        Create CLEAN seraphine group visualization (same style as YOLO/OCR visualizations)
        """
        # Check if seraphine visualization is enabled in config
        if not self.config.get("save_seraphine_viz", True):
            debug_print("⏭️  Seraphine visualization disabled in config")
            return None
        
        if not seraphine_analysis:
            debug_print("⚠️  No seraphine analysis provided")
            return None
        
        debug_print("🧠 Creating Seraphine group visualization...")
        
        # Load image
        image = Image.open(image_path).convert('RGB')
        
        # Auto-detect filename if not provided
        if filename_base is None:
            filename_base = os.path.splitext(os.path.basename(image_path))[0]
        
        current_time = datetime.now().strftime("%H-%M")
        output_filename = f"{filename_base}_seraphine_groups_{current_time}.jpg"
        output_path = os.path.join(self.output_dir, output_filename)
        
        # Convert PIL to OpenCV for drawing
        img_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        h, w = img_cv.shape[:2]
        
        # Get the bbox processor from seraphine analysis
        bbox_processor = seraphine_analysis.get('bbox_processor')
        if not bbox_processor:
            debug_print("❌ No bbox_processor found in seraphine analysis")
            return None
        
        # USE SAME CLEAN STYLE AS YOLO/OCR VISUALIZATIONS
        font = cv2.FONT_HERSHEY_DUPLEX
        text_scale = 0.35          # Same as other visualizations
        thickness = 1              # THIN borders like YOLO (not 3!)
        text_thickness = 1
        text_padding = 2
        
        color_idx = 0
        
        # Draw each group with CLEAN styling
        for group_id, boxes in bbox_processor.final_groups.items():
            # Get color for this group
            color_rgb = self.seraphine_colors[color_idx % len(self.seraphine_colors)]
            color_bgr = (color_rgb[2], color_rgb[1], color_rgb[0])  # RGB to BGR
            color_idx += 1
            
            # Draw all boxes in this group with THIN borders
            for i, bbox in enumerate(boxes):
                x1, y1, x2, y2 = bbox.x1, bbox.y1, bbox.x2, bbox.y2
                
                # Draw THIN bounding box (same as YOLO style)
                cv2.rectangle(img_cv, (x1, y1), (x2, y2), color_bgr, thickness)
                
                # Create clean label (same format as other visualizations)
                label = f"{group_id}_{i+1}"
                
                # Calculate text size and position (same as other visualizations)
                (text_w, text_h), baseline = cv2.getTextSize(label, font, text_scale, text_thickness)
                
                # Position label above the box, or below if no space above
                label_x = x1
                label_y = y1 - text_padding
                
                if label_y - text_h < 0:
                    label_y = y2 + text_h + text_padding
                
                # Draw CLEAN label background (same style as YOLO)
                bg_x1, bg_y1 = label_x, label_y - text_h - text_padding
                bg_x2, bg_y2 = label_x + text_w + text_padding * 2, label_y + text_padding
                
                cv2.rectangle(img_cv, (bg_x1, bg_y1), (bg_x2, bg_y2), color_bgr, cv2.FILLED)
                
                # Draw clean label text (white text like YOLO)
                text_color = (255, 255, 255)  # White text
                cv2.putText(img_cv, label, (label_x + text_padding, label_y), font, text_scale, 
                           text_color, text_thickness, cv2.LINE_AA)
        
        # Add CLEAN summary overlay (same style as detection count overlay)
        analysis = seraphine_analysis['analysis']
        summary_text = f"SERAPHINE: {analysis['total_groups']} groups ({analysis['horizontal_groups']}H + {analysis['vertical_groups']}V)"
        
        # Draw clean summary background (same as YOLO detection count)
        cv2.rectangle(img_cv, (10, 10), (500, 40), (0, 0, 0), cv2.FILLED)
        cv2.rectangle(img_cv, (10, 10), (500, 40), (255, 255, 255), 2)
        cv2.putText(img_cv, summary_text, (20, 30), font, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
        
        # Convert back to PIL and save
        img_rgb = cv2.cvtColor(img_cv, cv2.COLOR_BGR2RGB)
        result_img = Image.fromarray(img_rgb)
        result_img.save(output_path, quality=95)
        
        debug_print(f"💾 Saved SERAPHINE GROUPS: {analysis['total_groups']} groups → {output_filename}")
        return output_path

    def _create_detection_visualization(self, image: Image.Image, detections: List[Dict], 
                                      viz_type: str, filename_base: str) -> str:
        """Create beautiful visualization for detection results"""
        
        # Get current time for filename
        current_time = datetime.now().strftime("%H-%M")
        output_filename = f"{filename_base}_{viz_type}_result_{current_time}.jpg"
        output_path = os.path.join(self.output_dir, output_filename)
        
        # Convert PIL to OpenCV for drawing
        img_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        h, w = img_cv.shape[:2]
        
        # Get color for this visualization type
        color_rgb = self.colors.get(viz_type, self.colors['complete'])
        color_bgr = (color_rgb[2], color_rgb[1], color_rgb[0])  # RGB to BGR
        
        # Drawing parameters
        font = cv2.FONT_HERSHEY_DUPLEX
        text_scale = 0.35
        thickness = 1
        text_thickness = 1
        text_padding = 2
        
        # Draw each detection
        for i, detection in enumerate(detections):
            # Get bbox coordinates
            if 'bbox' in detection:
                bbox = detection['bbox']
            elif 'box' in detection:
                bbox = detection['box']
            else:
                continue
            
            # Handle different coordinate formats
            if len(bbox) == 4:
                if all(0 <= coord <= 1 for coord in bbox):
                    # Normalized coordinates
                    x1, y1, x2, y2 = int(bbox[0] * w), int(bbox[1] * h), int(bbox[2] * w), int(bbox[3] * h)
                else:
                    # Pixel coordinates
                    x1, y1, x2, y2 = map(int, bbox)
            else:
                continue
            
            # Draw bounding box
            cv2.rectangle(img_cv, (x1, y1), (x2, y2), color_bgr, thickness)
            
            # Prepare label text
            label_parts = []
            
            # Add ID if available (prioritize m_id, y_id, o_id)
            if 'm_id' in detection:
                label_parts.append(detection['m_id'])
            elif 'y_id' in detection:
                label_parts.append(detection['y_id'])
            elif 'o_id' in detection:
                label_parts.append(detection['o_id'])
            else:
                label_parts.append(str(i+1))
            
            # Add confidence if available
            if 'confidence' in detection:
                conf = detection['confidence']
                label_parts.append(f"{conf:.2f}")
            elif 'conf' in detection:
                conf = detection['conf']
                label_parts.append(f"{conf:.2f}")
            
            label = ": ".join(label_parts)
            
            # Calculate text size and position
            (text_w, text_h), baseline = cv2.getTextSize(label, font, text_scale, text_thickness)
            
            # Position label above the box, or below if no space above
            label_x = x1
            label_y = y1 - text_padding
            
            if label_y - text_h < 0:
                label_y = y2 + text_h + text_padding
            
            # Draw label background
            bg_x1, bg_y1 = label_x, label_y - text_h - text_padding
            bg_x2, bg_y2 = label_x + text_w + text_padding * 2, label_y + text_padding
            
            cv2.rectangle(img_cv, (bg_x1, bg_y1), (bg_x2, bg_y2), color_bgr, cv2.FILLED)
            
            # Draw label text
            text_color = (255, 255, 255)  # White text
            cv2.putText(img_cv, label, (label_x + text_padding, label_y), font, text_scale, 
                       text_color, text_thickness, cv2.LINE_AA)
        
        # Add detection count overlay
        count_text = f"{viz_type.upper()}: {len(detections)} detections"
        cv2.rectangle(img_cv, (10, 10), (300, 40), (0, 0, 0), cv2.FILLED)
        cv2.rectangle(img_cv, (10, 10), (300, 40), color_bgr, 2)
        cv2.putText(img_cv, count_text, (20, 30), font, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
        
        # Convert back to PIL and save
        img_rgb = cv2.cvtColor(img_cv, cv2.COLOR_BGR2RGB)
        result_img = Image.fromarray(img_rgb)
        result_img.save(output_path, quality=95)
        
        debug_print(f"💾 Saved {viz_type.upper()}: {len(detections)} detections → {output_filename}")
        return output_path

    
    def _create_gemini_visualization(self, image: Image.Image, gemini_analysis, 
                                   seraphine_analysis: Dict, filename_base: str) -> str:
        """Create beautiful Gemini analysis visualization with Seraphine group mapping"""
        
        # Safety check and type handling
        if not gemini_analysis:
            debug_print("⚠️  Gemini analysis is empty or None, skipping visualization")
            return None
        
        # Handle if gemini_analysis is a JSON string
        if isinstance(gemini_analysis, str):
            try:
                import json
                gemini_analysis = json.loads(gemini_analysis)
                debug_print("📋 Parsed Gemini analysis from JSON string")
            except json.JSONDecodeError as e:
                debug_print(f"❌ Failed to parse Gemini JSON: {e}")
                return None
        
        # Extract icons from the nested structure - COLLECT FROM ALL IMAGES
        if isinstance(gemini_analysis, dict):
            # Get icons from ALL successful image analyses
            if 'images' in gemini_analysis and len(gemini_analysis['images']) > 0:
                all_icons = []
                for image_data in gemini_analysis['images']:
                    if image_data.get('analysis_success', True) and 'icons' in image_data:
                        icons = image_data['icons']
                        all_icons.extend(icons)
                        debug_print(f"📋 Added {len(icons)} icons from {image_data.get('image_name', 'unknown')}")
                
                if all_icons:
                    gemini_analysis = all_icons
                    debug_print(f"✅ Total extracted: {len(gemini_analysis)} icons from {len([img for img in gemini_analysis if img.get('analysis_success', True)])} images")
                else:
                    debug_print("❌ No icons found in any successful image analysis")
                    return None
            else:
                debug_print("❌ No images found in Gemini analysis")
                return None
        
        # Ensure it's a list
        if not isinstance(gemini_analysis, list):
            debug_print(f"❌ Gemini analysis expected list, got {type(gemini_analysis)}")
            return None
            
        if len(gemini_analysis) == 0:
            debug_print("⚠️  Gemini analysis list is empty, skipping visualization")
            return None
        
        debug_print(f"✅ Processing {len(gemini_analysis)} Gemini items for visualization")
        
        current_time = datetime.now().strftime("%H-%M")
        output_filename = f"{filename_base}_gemini_analysis_{current_time}.jpg"
        output_path = os.path.join(self.output_dir, output_filename)
        
        # Convert PIL to OpenCV
        img_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        h, w = img_cv.shape[:2]
        
        font = cv2.FONT_HERSHEY_DUPLEX
        text_scale = 0.25
        thickness = 1
        text_thickness = 1
        
        # Get group details from seraphine analysis
        group_details = seraphine_analysis['analysis']['group_details']
        
        # Create mapping from Gemini analysis
        gemini_labels = {}
        for item in gemini_analysis:
            gemini_labels[item['id']] = {
                'name': item['name'],
                'usage': item['usage'],
                'group_type': item['group_type']
            }
        
        color_idx = 0
        
        # Draw each group with its Gemini labels
        for group_key, group_info in group_details.items():
            # Get color for this group
            color_rgb = self.seraphine_colors[color_idx % len(self.seraphine_colors)]
            color_bgr = (color_rgb[2], color_rgb[1], color_rgb[0])
            color_idx += 1
            
            # Draw all bboxes in this group
            for i, bbox_info in enumerate(group_info['bboxes']):
                bbox = bbox_info['bbox']
                
                if len(bbox) == 4:
                    x1, y1, x2, y2 = map(int, bbox)
                    
                    # Draw thick border for grouped items
                    cv2.rectangle(img_cv, (x1, y1), (x2, y2), color_bgr, thickness)
                    
                    # Get Gemini label for this specific item
                    item_id = f"{group_key}_{i+1}"
                    gemini_info = gemini_labels.get(item_id, {})
                    gemini_name = gemini_info.get('name', 'Unlabeled')
                    
                    # Create label text
                    full_label = f"{item_id}: {gemini_name}"
                    # skipping item_id due to low space
                    # full_label = f"{gemini_name}"
                    
                    # Calculate label dimensions
                    (text_w, text_h), _ = cv2.getTextSize(full_label, font, text_scale, text_thickness)
                    
                    # Position label (try above, fallback to inside)
                    label_x = x1 + 5
                    label_y = y1 - 10
                    bg_x1, bg_y1 = x1, y1 - text_h - 15
                    bg_x2, bg_y2 = x1 + text_w + 10, y1 - 5
                    
                    # Adjust if label goes outside image bounds
                    if bg_y1 < 0:
                        label_y = y1 + text_h + 10
                        bg_y1, bg_y2 = y1 + 5, y1 + text_h + 15
                    
                    if bg_x2 > w:
                        label_x = x2 - text_w - 5
                        bg_x1, bg_x2 = x2 - text_w - 10, x2
                    
                    # Draw label background with group color
                    cv2.rectangle(img_cv, (bg_x1, bg_y1), (bg_x2, bg_y2), color_bgr, cv2.FILLED)
                    cv2.rectangle(img_cv, (bg_x1, bg_y1), (bg_x2, bg_y2), (255, 255, 255), 1)
                    
                    # Draw label text
                    text_color = (255, 255, 255)  # White text
                    cv2.putText(img_cv, full_label, (label_x, label_y), font, text_scale, 
                               text_color, text_thickness, cv2.LINE_AA)
        
        # Add comprehensive legend showing all Gemini labels
        legend_x = w - 350
        legend_y = 20
        legend_height = min(len(gemini_analysis) * 20 + 40, h - 100)  # Limit height
        
        show_gemini_analysis_box = False
        if show_gemini_analysis_box: 
            cv2.rectangle(img_cv, (legend_x, legend_y), (w - 10, legend_y + legend_height), 
                        (0, 0, 0), cv2.FILLED)
            cv2.rectangle(img_cv, (legend_x, legend_y), (w - 10, legend_y + legend_height), 
                        (255, 255, 255), 2)
            
            cv2.putText(img_cv, "Gemini Analysis:", (legend_x + 10, legend_y + 20), 
                    font, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
            
            # Show first 15 items to avoid overcrowding
            visible_items = gemini_analysis[:15]
            for idx, item in enumerate(visible_items):
                y_pos = legend_y + 40 + idx * 20
                if y_pos > legend_y + legend_height - 25:
                    # Add "..." if more items exist
                    cv2.putText(img_cv, "...", (legend_x + 10, y_pos), 
                            font, 0.4, (255, 255, 255), 1, cv2.LINE_AA)
                    break
                    
                legend_text = f"{item['id']}: {item['name']}"
                # Truncate if too long
                if len(legend_text) > 35:
                    legend_text = legend_text[:32] + "..."
                    
                cv2.putText(img_cv, legend_text, (legend_x + 10, y_pos), 
                        font, 0.35, (255, 255, 255), 1, cv2.LINE_AA)
            
            # Add summary at bottom
            summary_lines = [
                f"Total Items: {len(gemini_analysis)}",
                f"Groups: {len(set(item['group_type'] for item in gemini_analysis))} types",
                f"Items per Group: {len(gemini_analysis)/len(group_details):.1f} avg"
            ]
            
            summary_bg_height = len(summary_lines) * 25 + 20
            cv2.rectangle(img_cv, (10, h - summary_bg_height - 10), 
                        (300, h - 10), (0, 0, 0), cv2.FILLED)
            cv2.rectangle(img_cv, (10, h - summary_bg_height - 10), 
                        (300, h - 10), (255, 255, 255), 2)
            
            for i, line in enumerate(summary_lines):
                cv2.putText(img_cv, line, (20, h - summary_bg_height + 15 + i*25), 
                        font, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
        
        # Convert back to PIL and save
        img_rgb = cv2.cvtColor(img_cv, cv2.COLOR_BGR2RGB)
        result_img = Image.fromarray(img_rgb)
        result_img.save(output_path, quality=95)
        
        total_items = len(gemini_analysis)
        debug_print(f"💾 Saved GEMINI: {total_items} labeled items → {output_filename}")
        return output_path