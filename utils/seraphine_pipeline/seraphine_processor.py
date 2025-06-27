import json
import logging
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass
from PIL import Image, ImageDraw, ImageFont
import os
import random
import math
import time
import tempfile
from .helpers import debug_print
import numpy as np

@dataclass
class BBox:
    x1: int
    y1: int
    x2: int
    y2: int
    original_id: int
    merged_id: int
    bbox_type: str
    source: str
    confidence: float
    
    @property
    def width(self) -> int:
        return self.x2 - self.x1
    
    @property
    def height(self) -> int:
        return self.y2 - self.y1
    
    @property
    def center_x(self) -> float:
        return (self.x1 + self.x2) / 2
    
    @property
    def center_y(self) -> float:
        return (self.y1 + self.y2) / 2
    
    @property
    def right_edge_center(self) -> float:
        return (self.y1 + self.y2) / 2

class BBoxProcessor:
    def __init__(self, enable_logging: bool = True):
        self.enable_logging = enable_logging
        self.setup_logging()
        
        # Global variables
        self.all_bboxes: List[BBox] = []
        self.sort_x_list: List[BBox] = []
        self.sort_y_list: List[BBox] = []
        self.long_boxes: List[Tuple[BBox, str]] = []  # (bbox, 'H'/'V')
        self.horizontal_groups: Dict[int, List[BBox]] = {}
        self.vertical_groups: Dict[int, List[BBox]] = {}
        self.final_groups: Dict[str, List[BBox]] = {}
        self.bbox_to_group_mapping: Dict[int, str] = {}  # original_id -> group_id
        self.group_colors: Dict[str, Tuple[int, int, int]] = {}  # group_id -> RGB color
        self.original_image: Optional[Image.Image] = None
        self.long_box_ids: set = set()
        
        # Constants
        self.LONG_BOX_THRESHOLD = 600
        self.LONG_BOX_SCALE_MAX = 1100
        self.HORIZONTAL_TOLERANCE_PX = 20
        self.Y_VARIANCE_TOLERANCE = 8
        self.GROUP_GAP = 50
        self.BBOX_GAP = 25  # Base gap between bboxes
        self.MIN_DIMENSION = 40
        self.MAX_HEIGHT = 50
        self.PADDING = 20
        self.IMAGE_WIDTH = 1280
        self.IMAGE_HEIGHT = 1280
        self.BBOX_BORDER_WIDTH = 1
        
        # GLOBAL PARAMETERS FOR FIXES
        self.LABEL_FONT_SIZE = 18  # Doubled from 12
        self.LABEL_TOP_PADDING = 20  # Space above each image for labels
        self.BBOX_LABEL_GAP = 25  # Additional horizontal gap to accommodate wide labels
        self.LABEL_BACKGROUND = False  # Remove box around IDs
        self.EFFICIENT_PACKING_WIDTH = 1250  # If group width < this, try to pack next group on same row
        self.SAME_ROW_GAP = 40  # Gap between groups on same row
        self.INCLUDE_BBOX_COUNT_IN_FILENAME = True  # Whether to include bbox count in filenames
    
    def setup_logging(self):
        if self.enable_logging:
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(levelname)s - %(message)s'
            )
            self.logger = logging.getLogger(__name__)
        else:
            self.logger = logging.getLogger(__name__)
            self.logger.disabled = True
    
    def log(self, message: str, level: str = 'info'):
        if self.enable_logging:
            getattr(self.logger, level)(message)
    
    def generate_group_colors(self):
        """Generate distinct colors for each group"""
        self.log("Generating colors for groups")
        
        # Predefined colors for better distinction
        predefined_colors = [
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
        
        color_index = 0
        for group_id in self.final_groups.keys():
            if color_index < len(predefined_colors):
                self.group_colors[group_id] = predefined_colors[color_index]
            else:
                # Generate random colors if we run out of predefined ones
                self.group_colors[group_id] = (
                    random.randint(50, 255),
                    random.randint(50, 255),
                    random.randint(50, 255)
                )
            color_index += 1
        
        self.log(f"Generated colors for {len(self.group_colors)} groups")
    
    def load_bboxes(self, json_file_path: str):
        """Step 1: Load all bboxes from JSON file"""
        self.log("Step 1: Loading bboxes from JSON file")
        
        with open(json_file_path, 'r') as f:
            data = json.load(f)
        
        for item in data:
            bbox = BBox(
                x1=item['bbox'][0],
                y1=item['bbox'][1],
                x2=item['bbox'][2],
                y2=item['bbox'][3],
                original_id=item['id'],
                merged_id=item['merged_id'],
                bbox_type=item['type'],
                source=item['source'],
                confidence=item['confidence']
            )
            self.all_bboxes.append(bbox)
        
        self.log(f"Loaded {len(self.all_bboxes)} bounding boxes")
    
    def sort_bboxes(self):
        """Step 2: Create two sorted lists"""
        self.log("Step 2: Sorting bboxes")
        
        # SORT_X: x-first, then y
        self.sort_x_list = sorted(self.all_bboxes, key=lambda b: (b.x1, b.y1))
        
        # SORT_Y: y-first, then x
        self.sort_y_list = sorted(self.all_bboxes, key=lambda b: (b.y1, b.x1))
        
        self.log(f"Created SORT_X list with {len(self.sort_x_list)} items")
        self.log(f"Created SORT_Y list with {len(self.sort_y_list)} items")
    
    def assign_sorted_ids(self):
        """Step 3: Assign IDs in sorted lists"""
        self.log("Step 3: Assigning sorted IDs")
        
        for i, bbox in enumerate(self.sort_x_list):
            bbox.sort_x_id = i
        
        for i, bbox in enumerate(self.sort_y_list):
            bbox.sort_y_id = i
        
        self.log("Assigned sorted IDs to all bboxes")
    
    def calculate_dimensions_and_identify_long_boxes(self):
        """Steps 4-5: Calculate dimensions and identify long boxes"""
        self.log("Steps 4-5: Calculating dimensions and identifying long boxes")
        
        remaining_bboxes = []
        
        for bbox in self.all_bboxes:
            width = bbox.width
            height = bbox.height
            
            if width > self.LONG_BOX_THRESHOLD or height > self.LONG_BOX_THRESHOLD:
                # Track this as a long box
                self.long_box_ids.add(bbox.merged_id)
                
                # Scale the long box
                if width > height:
                    # Horizontal long box
                    if width > self.LONG_BOX_SCALE_MAX:
                        scale_factor = self.LONG_BOX_SCALE_MAX / width
                        new_width = self.LONG_BOX_SCALE_MAX
                        new_height = int(height * scale_factor)
                        self.log(f"SCALING: Long box ID {bbox.merged_id} from {width}x{height} to {new_width}x{new_height} (scale: {scale_factor:.3f})")
                        bbox.x2 = bbox.x1 + new_width
                        bbox.y2 = bbox.y1 + new_height
                    self.long_boxes.append((bbox, 'H'))
                    self.log(f"Identified horizontal long box: ID {bbox.merged_id}, size {width}x{height}")
                else:
                    # Vertical long box
                    if height > self.LONG_BOX_SCALE_MAX:
                        scale_factor = self.LONG_BOX_SCALE_MAX / height
                        new_height = self.LONG_BOX_SCALE_MAX
                        new_width = int(width * scale_factor)
                        self.log(f"SCALING: Long box ID {bbox.merged_id} from {width}x{height} to {new_width}x{new_height} (scale: {scale_factor:.3f})")
                        bbox.x2 = bbox.x1 + new_width
                        bbox.y2 = bbox.y1 + new_height
                    self.long_boxes.append((bbox, 'V'))
                    self.log(f"Identified vertical long box: ID {bbox.merged_id}, size {width}x{height}")
            else:
                remaining_bboxes.append(bbox)
        
        # Update the main lists to exclude long boxes
        self.all_bboxes = remaining_bboxes
        self.sort_x_list = [b for b in self.sort_x_list if b in remaining_bboxes]
        self.sort_y_list = [b for b in self.sort_y_list if b in remaining_bboxes]
        
        self.log(f"Identified {len(self.long_boxes)} long boxes")
        self.log(f"Remaining {len(self.all_bboxes)} boxes for grouping")
    
    def calculate_overlap_aware_distance(self, bbox1: BBox, bbox2: BBox, direction: str) -> float:
        """
        Calculate overlap-aware distance between two bboxes
        Returns negative values for overlaps, positive for gaps
        """
        if direction == 'horizontal':
            # Check if boxes overlap horizontally
            if bbox1.x2 > bbox2.x1:  # Overlap
                overlap = bbox1.x2 - bbox2.x1
                return -overlap  # Negative distance = overlap
            else:  # Gap
                gap = bbox2.x1 - bbox1.x2
                return gap  # Positive distance = gap
        
        elif direction == 'vertical':
            # Check if boxes overlap vertically  
            if bbox1.y2 > bbox2.y1:  # Overlap
                overlap = bbox1.y2 - bbox2.y1
                return -overlap  # Negative distance = overlap
            else:  # Gap
                gap = bbox2.y1 - bbox1.y2
                return gap  # Positive distance = gap

    def horizontal_grouping(self):
        """FIXED: Horizontal grouping with overlap support"""
        self.log("Step 6: Performing horizontal grouping (overlap-aware)")
        
        used_boxes = set()
        group_id = 0
        
        for bbox in self.sort_x_list:
            if bbox.merged_id in used_boxes:
                continue
            
            current_group = [bbox]
            used_boxes.add(bbox.merged_id)
            current_bbox = bbox
            
            # Find horizontal neighbors
            for next_bbox in self.sort_x_list:
                if next_bbox.merged_id in used_boxes:
                    continue
                
                # Check if next box is horizontally aligned
                y_diff = abs(next_bbox.center_y - current_bbox.center_y)
                if y_diff <= self.Y_VARIANCE_TOLERANCE:
                    # FIXED: Use overlap-aware distance
                    distance = self.calculate_overlap_aware_distance(current_bbox, next_bbox, 'horizontal')
                    
                    # Allow small overlaps and reasonable gaps
                    max_overlap = min(current_bbox.width, next_bbox.width) * 0.3  # 30% overlap allowed
                    max_gap = min(self.HORIZONTAL_TOLERANCE_PX, current_bbox.width)
                    
                    if -max_overlap <= distance <= max_gap:  # Allows overlaps AND gaps
                        current_group.append(next_bbox)
                        used_boxes.add(next_bbox.merged_id)
                        current_bbox = next_bbox
                        
                        if distance < 0:
                            self.log(f"OVERLAP: Grouped overlapping boxes (overlap: {-distance:.1f}px)")
                        else:
                            self.log(f"GAP: Grouped boxes with gap (gap: {distance:.1f}px)")
            
            if len(current_group) > 0:
                self.horizontal_groups[group_id] = current_group
                self.log(f"Created horizontal group H{group_id} with {len(current_group)} boxes")
                group_id += 1
    
    def vertical_grouping(self):
        """FIXED: Vertical grouping with overlap support"""
        self.log("Step 7: Performing vertical grouping (overlap-aware)")
        
        used_boxes = set()
        group_id = 0
        
        for bbox in self.sort_y_list:
            if bbox.merged_id in used_boxes:
                continue
            
            current_group = [bbox]
            used_boxes.add(bbox.merged_id)
            current_bbox = bbox
            
            # Find vertical neighbors
            for next_bbox in self.sort_y_list:
                if next_bbox.merged_id in used_boxes:
                    continue
                
                # Check if next box is vertically aligned
                x_diff = abs(next_bbox.center_x - current_bbox.center_x)
                if x_diff <= self.HORIZONTAL_TOLERANCE_PX:
                    # FIXED: Use overlap-aware distance
                    distance = self.calculate_overlap_aware_distance(current_bbox, next_bbox, 'vertical')
                    
                    # Allow small overlaps and reasonable gaps
                    max_overlap = min(current_bbox.height, next_bbox.height) * 0.3  # 30% overlap allowed
                    max_gap = self.HORIZONTAL_TOLERANCE_PX
                    
                    if -max_overlap <= distance <= max_gap:  # Allows overlaps AND gaps
                        current_group.append(next_bbox)
                        used_boxes.add(next_bbox.merged_id)
                        current_bbox = next_bbox
                        
                        if distance < 0:
                            self.log(f"OVERLAP: Grouped overlapping boxes (overlap: {-distance:.1f}px)")
                        else:
                            self.log(f"GAP: Grouped boxes with gap (gap: {distance:.1f}px)")
            
            if len(current_group) > 0:
                self.vertical_groups[group_id] = current_group
                self.log(f"Created vertical group V{group_id} with {len(current_group)} boxes")
                group_id += 1
    
    def merge_groups(self):
        """Step 8: Merge groups and resolve conflicts"""
        self.log("Step 8: Merging groups and resolving conflicts")
        
        # Track which boxes appear in both H and V groups
        h_box_to_group = {}
        v_box_to_group = {}
        
        for group_id, boxes in self.horizontal_groups.items():
            for bbox in boxes:
                h_box_to_group[bbox.merged_id] = group_id
        
        for group_id, boxes in self.vertical_groups.items():
            for bbox in boxes:
                v_box_to_group[bbox.merged_id] = group_id
        
        # Find conflicts and resolve by group size
        conflicts = set()
        for box_id in h_box_to_group:
            if box_id in v_box_to_group:
                conflicts.add(box_id)
        
        # Resolve conflicts
        for box_id in conflicts:
            h_group_id = h_box_to_group[box_id]
            v_group_id = v_box_to_group[box_id]
            
            h_group_size = len(self.horizontal_groups[h_group_id])
            v_group_size = len(self.vertical_groups[v_group_id])
            
            if h_group_size >= v_group_size:
                # Keep in horizontal group
                self.vertical_groups[v_group_id] = [b for b in self.vertical_groups[v_group_id] 
                                                  if b.original_id != box_id]
            else:
                # Keep in vertical group
                self.horizontal_groups[h_group_id] = [b for b in self.horizontal_groups[h_group_id] 
                                                    if b.original_id != box_id]
        
        # Create final groups dictionary WITH SEQUENTIAL RENUMBERING
        h_count = 0
        v_count = 0
        
        # Add non-empty horizontal groups with sequential numbering
        for group_id, boxes in self.horizontal_groups.items():
            if boxes:  # Only add non-empty groups
                self.final_groups[f"H{h_count}"] = boxes  # Sequential: H0, H1, H2...
                self.log(f"Renumbered H{group_id} → H{h_count} ({len(boxes)} boxes)")
                h_count += 1
        
        # Add non-empty vertical groups with sequential numbering  
        for group_id, boxes in self.vertical_groups.items():
            if boxes:  # Only add non-empty groups
                self.final_groups[f"V{v_count}"] = boxes  # Sequential: V0, V1, V2...
                self.log(f"Renumbered V{group_id} → V{v_count} ({len(boxes)} boxes)")
                v_count += 1
        
        # Add long boxes as separate groups (sequential)
        for i, (bbox, orientation) in enumerate(self.long_boxes):
            self.final_groups[f"{orientation}L{i}"] = [bbox]
        
        # Generate colors for groups
        self.generate_group_colors()
        
        self.log(f"Created {len(self.final_groups)} final groups with sequential numbering")
        self.log(f"Final: {h_count} H groups (H0-H{h_count-1}), {v_count} V groups (V0-V{v_count-1})")
    
    def scale_bbox_for_display(self, bbox: BBox) -> Tuple[int, int]:
        """Scale bbox for display according to rules - NO UPSCALING, only determine target size"""
        original_width = bbox.width
        original_height = bbox.height
        width = original_width
        height = original_height
        
        is_long_box = bbox.merged_id in self.long_box_ids
        
        if is_long_box:
            self.log(f"SKIP MIN SCALING: BBox ID {bbox.merged_id} is a long box, skipping minimum dimension scaling")
        else:
            # Determine target dimensions (but don't scale up - we'll pad instead)
            if width < self.MIN_DIMENSION:
                target_width = self.MIN_DIMENSION
                target_height = int(height * (self.MIN_DIMENSION / width))
                self.log(f"PADDING TARGET: BBox ID {bbox.merged_id} width will be padded from {original_width} to {target_width}")
                width = target_width
                height = target_height
            
            if height < self.MIN_DIMENSION:
                target_height = self.MIN_DIMENSION  
                target_width = int(width * (self.MIN_DIMENSION / height))
                self.log(f"PADDING TARGET: BBox ID {bbox.merged_id} height will be padded from {original_height} to {target_height}")
                width = target_width
                height = target_height
        
        # Scale down if height too large (apply to all boxes including long boxes)
        if height > self.MAX_HEIGHT:
            scale_factor = self.MAX_HEIGHT / height
            height = self.MAX_HEIGHT
            width = int(width * scale_factor)
            self.log(f"RESIZE: BBox ID {bbox.merged_id} height scaled down from {original_height} to {height} (factor: {scale_factor:.3f})")
        
        if width != original_width or height != original_height:
            self.log(f"TARGET DIMENSIONS: BBox ID {bbox.merged_id}: {original_width}x{original_height} -> {width}x{height}")
        
        return width, height
    
    def pad_image_to_size(self, image: Image.Image, target_width: int, target_height: int, bbox_id: int) -> Image.Image:
        """Pad image to target size using border pixel replication"""
        current_width, current_height = image.size
        
        # If image is already the right size or larger, just resize normally (scale down)
        if current_width >= target_width and current_height >= target_height:
            resized = image.resize((target_width, target_height), Image.Resampling.LANCZOS)
            self.log(f"PAD: BBox ID {bbox_id} - scaled down normally from {current_width}x{current_height} to {target_width}x{target_height}")
            return resized
        
        # Need to pad - preserve original image quality
        self.log(f"PAD: BBox ID {bbox_id} - padding from {current_width}x{current_height} to {target_width}x{target_height}")
        
        # Calculate padding needed
        pad_left = (target_width - current_width) // 2
        pad_right = target_width - current_width - pad_left
        pad_top = (target_height - current_height) // 2  
        pad_bottom = target_height - current_height - pad_top
        
        # Create padded image by extending border pixels
        # Convert to numpy for easier manipulation
        img_array = np.array(image)
        
        # Pad the image array using edge mode (replicate border pixels)
        padded_array = np.pad(
            img_array,
            ((pad_top, pad_bottom), (pad_left, pad_right), (0, 0)) if len(img_array.shape) == 3 else ((pad_top, pad_bottom), (pad_left, pad_right)),
            mode='edge'  # Replicate edge pixels
        )
        
        # Convert back to PIL Image
        padded_image = Image.fromarray(padded_array)
        
        self.log(f"PAD: BBox ID {bbox_id} - successfully padded with border replication (pad: L{pad_left} R{pad_right} T{pad_top} B{pad_bottom})")
        return padded_image
    
    def crop_bbox_from_image(self, bbox: BBox) -> Image.Image:
        """Crop the actual image content from the original image"""
        if self.original_image is None:
            self.log("ERROR: No original image loaded for cropping", "error")
            # Return a placeholder image
            return Image.new('RGB', (bbox.width, bbox.height), 'white')
        
        try:
            # Ensure coordinates are within image bounds
            x1 = max(0, bbox.x1)
            y1 = max(0, bbox.y1)
            x2 = min(self.original_image.width, bbox.x2)
            y2 = min(self.original_image.height, bbox.y2)
            
            if x1 >= x2 or y1 >= y2:
                self.log(f"WARNING: Invalid crop coordinates for BBox ID {bbox.merged_id}: ({x1},{y1},{x2},{y2})", "warning")
                return Image.new('RGB', (bbox.width, bbox.height), 'white')
            
            cropped = self.original_image.crop((x1, y1, x2, y2))
            self.log(f"CROP: Extracted {cropped.size[0]}x{cropped.size[1]} region from BBox ID {bbox.merged_id}")
            return cropped
            
        except Exception as e:
            self.log(f"ERROR: Failed to crop BBox ID {bbox.merged_id}: {e}", "error")
            return Image.new('RGB', (bbox.width, bbox.height), 'white')
    
    def calculate_label_width(self, label: str, font) -> int:
        """Calculate the width of a label text"""
        try:
            # Create a temporary image to measure text
            temp_img = Image.new('RGB', (1, 1))
            temp_draw = ImageDraw.Draw(temp_img)
            bbox = temp_draw.textbbox((0, 0), label, font=font)
            return bbox[2] - bbox[0]  # width
        except:
            # Fallback estimation: roughly 12px per character for size 24 font
            return len(label) * 12

    def calculate_dynamic_gap(self, current_bbox_width: int, current_label_width: int, 
                            next_bbox_width: int, next_label_width: int) -> int:
        """Calculate dynamic gap between two bboxes based on their label widths"""
        
        # Calculate how much each label extends beyond its bbox
        current_label_overhang = max(0, (current_label_width - current_bbox_width) // 2)
        next_label_overhang = max(0, (next_label_width - next_bbox_width) // 2)
        
        # Total gap needed = base gap + label overhangs + additional buffer
        total_gap = self.BBOX_GAP + current_label_overhang + next_label_overhang + self.BBOX_LABEL_GAP
        
        self.log(f"GAP CALC: bbox widths ({current_bbox_width}, {next_bbox_width}), "
                f"label widths ({current_label_width}, {next_label_width}), "
                f"overhangs ({current_label_overhang}, {next_label_overhang}), "
                f"total gap: {total_gap}")
        
        return total_gap

    def _count_bboxes_in_image(self, groups_in_image: List[str]) -> int:
        """Count total bboxes in the groups that will be in this image"""
        total_count = 0
        for group_id in groups_in_image:
            if group_id in self.final_groups:
                total_count += len(self.final_groups[group_id])
        return total_count
    
    def _generate_filename(self, base_name: str, image_count: int, bbox_count: int) -> str:
        """Generate filename with optional bbox count"""
        if self.INCLUDE_BBOX_COUNT_IN_FILENAME:
            return f"{base_name}_{image_count}_{bbox_count}_bboxes.png"
        else:
            return f"{base_name}_{image_count}.png"
    
    def _generate_combined_group_images(self, groups: Dict[str, List[BBox]], base_name: str, 
                             output_dir: str, start_image_count: int) -> int:
        """Generate images combining both horizontal and vertical groups"""
        image_count = start_image_count
        current_y = self.PADDING + self.LABEL_TOP_PADDING
        current_image = Image.new('RGB', (self.IMAGE_WIDTH, self.IMAGE_HEIGHT), 'white')
        
        try:
            font = ImageFont.truetype("arial.ttf", self.LABEL_FONT_SIZE)
        except:
            font = ImageFont.load_default()
        
        # Track current row state for efficient packing
        current_row_x = self.PADDING
        current_row_max_height = 0
        current_row_groups = []
        
        # Track groups in current image for bbox counting
        groups_in_current_image = []
        
        # Process horizontal groups first, then vertical groups
        h_groups = {k: v for k, v in groups.items() if k.startswith('H')}
        v_groups = {k: v for k, v in groups.items() if k.startswith('V')}
        
        self.log(f"PROCESSING: {len(h_groups)} horizontal groups, then {len(v_groups)} vertical groups")
        
        # Combine groups in order: H groups first, then V groups
        ordered_groups = list(h_groups.items()) + list(v_groups.items())
        
        for group_id, boxes in ordered_groups:
            self.log(f"PROCESSING: Starting group {group_id} with {len(boxes)} boxes")
            
            # Prepare scaled boxes with cropped images and calculate label widths
            scaled_boxes = []
            max_height = 0
            
            for i, bbox in enumerate(boxes):
                # Get scaled dimensions
                width, height = self.scale_bbox_for_display(bbox)
                
                # Crop the actual image content
                cropped_image = self.crop_bbox_from_image(bbox)
                
                # Resize the cropped image to match scaled dimensions
                if cropped_image.size != (width, height):
                    original_size = cropped_image.size
                    original_width, original_height = original_size
                    
                    # Check if we need to scale up (pad) or scale down (resize)
                    if original_width < width or original_height < height:
                        # Use padding to preserve image quality for upscaling
                        cropped_image = self.pad_image_to_size(cropped_image, width, height, bbox.merged_id)
                        self.log(f"PAD: Cropped image for BBox ID {bbox.merged_id} padded from {original_size} to {width}x{height}")
                    else:
                        # Use normal resize for downscaling
                        cropped_image = cropped_image.resize((width, height), Image.Resampling.LANCZOS)
                        self.log(f"RESIZE: Cropped image for BBox ID {bbox.merged_id} resized from {original_size} to {width}x{height}")
                
                label = f"{group_id}_{i+1}"
                label_width = self.calculate_label_width(label, font)
                
                scaled_boxes.append((bbox, width, height, label, cropped_image, label_width))
                max_height = max(max_height, height)
            
                self.log(f"LABEL: {label} width={label_width}px, bbox width={width}px")
            
            # Calculate group width with dynamic gaps based on label widths
            group_width = 0
            for i, (_, width, _, _, _, label_width) in enumerate(scaled_boxes):
                group_width += width
                
                # Add gap to next bbox if not the last one
                if i < len(scaled_boxes) - 1:
                    next_bbox = scaled_boxes[i + 1]
                    next_width = next_bbox[1]
                    next_label_width = next_bbox[5]
                    
                    dynamic_gap = self.calculate_dynamic_gap(width, label_width, next_width, next_label_width)
                    group_width += dynamic_gap
            
            # Add height for labels (vertical spacing unchanged)
            total_group_height = max_height + self.LABEL_TOP_PADDING
            
            self.log(f"LAYOUT: Group {group_id} dimensions: {group_width}x{total_group_height} (with dynamic label gaps)")
            
            # Check if we can fit this group on the current row
            can_fit_on_current_row = (
                current_row_x + group_width + self.PADDING <= self.IMAGE_WIDTH and
                current_y + total_group_height <= self.IMAGE_HEIGHT
            )
            
            # Check if we should start a new row
            should_start_new_row = (
                len(current_row_groups) > 0 and  # There are groups in current row
                (not can_fit_on_current_row or  # Can't fit
                 current_row_x > self.EFFICIENT_PACKING_WIDTH)  # Current row is already long enough
            )
            
            if should_start_new_row:
                # Move to next row
                current_y += current_row_max_height + self.GROUP_GAP
                current_row_x = self.PADDING
                current_row_max_height = 0
                current_row_groups = []
                self.log(f"LAYOUT: Starting new row at Y={current_y} for group {group_id}")
                
                # Check if new row fits in current image
                if current_y + total_group_height > self.IMAGE_HEIGHT:
                    # Save current image and start new one
                    if current_y > self.PADDING + self.LABEL_TOP_PADDING:  # Only save if there's content
                        # Count bboxes in current image
                        bbox_count = self._count_bboxes_in_image(groups_in_current_image)
                        filename = self._generate_filename(base_name, image_count, bbox_count)
                        output_path = f"{output_dir}/{filename}"
                        current_image.save(output_path)
                        self.log(f"SAVE: Saved {output_path} (height used: {current_y}, {bbox_count} bboxes)")
                    image_count += 1
                    
                    current_y = self.PADDING + self.LABEL_TOP_PADDING
                    current_row_x = self.PADDING
                    current_row_max_height = 0
                    current_row_groups = []
                    groups_in_current_image = []  # Reset for new image
                    current_image = Image.new('RGB', (self.IMAGE_WIDTH, self.IMAGE_HEIGHT), 'white')
                    self.log(f"NEW IMAGE: Started new image {image_count} for group {group_id}")
            
            # Add this group to current image tracking
            groups_in_current_image.append(group_id)
            
            # Place boxes in the group with dynamic spacing
            group_start_x = current_row_x
            current_x = group_start_x
            
            for i, (bbox, width, height, label, cropped_image, label_width) in enumerate(scaled_boxes):
                # ✅ FIX: Check if this individual icon will exceed image width
                if current_x + width > self.IMAGE_WIDTH - self.PADDING:
                    # Start new row for this icon
                    current_y += max_height + self.GROUP_GAP
                    current_x = self.PADDING
                    self.log(f"WRAP: Icon {label} wrapped to new row at Y={current_y}")
                    
                    # Check if new row fits in current image
                    if current_y + height > self.IMAGE_HEIGHT:
                        # Save current image and start new one
                        bbox_count = self._count_bboxes_in_image(groups_in_current_image)
                        filename = self._generate_filename(base_name, image_count, bbox_count)
                        output_path = f"{output_dir}/{filename}"
                        current_image.save(output_path)
                        self.log(f"SAVE: Saved {output_path} (height used: {current_y}, {bbox_count} bboxes)")
                    
                    image_count += 1
                    current_y = self.PADDING + self.LABEL_TOP_PADDING
                    current_x = self.PADDING
                    current_image = Image.new('RGB', (self.IMAGE_WIDTH, self.IMAGE_HEIGHT), 'white')
                    self.log(f"NEW IMAGE: Started new image {image_count} for icon {label}")
                
                # Calculate positions
                image_y = current_y
                label_y = current_y - self.LABEL_TOP_PADDING + 5
                
                # Paste the actual cropped image
                current_image.paste(cropped_image, (current_x, image_y))
                
                # Draw border around the image
                draw = ImageDraw.Draw(current_image)
                draw.rectangle([current_x, image_y, current_x + width, image_y + height], 
                             outline='lightgrey', width=self.BBOX_BORDER_WIDTH)
                
                # Draw label without background box
                text_x = current_x + width // 2
                
                if self.LABEL_BACKGROUND:
                    # Draw label background (if enabled)
                    text_bbox = draw.textbbox((text_x, label_y), label, font=font, anchor='mm')
                    draw.rectangle(
                        [text_bbox[0]-2, text_bbox[1]-1, text_bbox[2]+2, text_bbox[3]+1],
                        fill='white',
                        outline='black',
                        width=1
                    )
                
                # Draw label text
                draw.text((text_x, label_y), label, fill='black', font=font, anchor='mm')
                
                # Store mapping
                self.bbox_to_group_mapping[bbox.merged_id] = label
                
                self.log(f"PLACE: Placed {label} at ({current_x}, {image_y}) size {width}x{height}")
                
                # Move to next position with dynamic gap
                current_x += width
                
                # Add dynamic gap to next bbox if not the last one
                if i < len(scaled_boxes) - 1:
                    next_bbox = scaled_boxes[i + 1]
                    next_width = next_bbox[1]
                    next_label_width = next_bbox[5]
                    
                    dynamic_gap = self.calculate_dynamic_gap(width, label_width, next_width, next_label_width)
                    current_x += dynamic_gap
                    
                    self.log(f"SPACING: Added {dynamic_gap}px gap after {label} (label_width={label_width}px)")
            
            # Update row tracking
            current_row_x = current_x + self.SAME_ROW_GAP  # Add gap for next group
            current_row_max_height = max(current_row_max_height, total_group_height)
            current_row_groups.append(group_id)
            
            self.log(f"COMPLETE: Group {group_id} placed, next X position: {current_row_x}, row height: {current_row_max_height}")
        
        # Save final image if it has content
        if current_y > self.PADDING + self.LABEL_TOP_PADDING or len(current_row_groups) > 0:
            # Count bboxes in final image
            bbox_count = self._count_bboxes_in_image(groups_in_current_image)
            filename = self._generate_filename(base_name, image_count, bbox_count)
            output_path = f"{output_dir}/{filename}"
            current_image.save(output_path)
            self.log(f"SAVE: Saved final {output_path} (height used: {current_y + current_row_max_height}, {bbox_count} bboxes)")
            image_count += 1
        
        return image_count
    
    def draw_groups_on_original_image(self, original_image_path: str, output_dir: str = "output"):
        """Draw grouped bounding boxes on the original image with color coding"""
        self.log("Drawing groups on original image")
        
        # Load the original image
        try:
            original_image = Image.open(original_image_path)
            self.log(f"Loaded original image: {original_image.size}")
        except Exception as e:
            self.log(f"Error loading original image: {e}", "error")
            return
        
        # Create a copy for drawing
        annotated_image = original_image.copy()
        draw = ImageDraw.Draw(annotated_image)
        
        try:
            font = ImageFont.truetype("arial.ttf", 14)
            small_font = ImageFont.truetype("arial.ttf", 10)
        except:
            font = ImageFont.load_default()
            small_font = ImageFont.load_default()
        
        # Draw each group with its assigned color
        for group_id, boxes in self.final_groups.items():
            color = self.group_colors[group_id]
            self.log(f"Drawing group {group_id} with {len(boxes)} boxes in color {color}")
            
            for i, bbox in enumerate(boxes):
                # Draw the bounding box with group color
                draw.rectangle(
                    [bbox.x1, bbox.y1, bbox.x2, bbox.y2],
                    outline=color,
                    width=3
                )
                
                # Add a semi-transparent fill
                overlay = Image.new('RGBA', original_image.size, (0, 0, 0, 0))
                overlay_draw = ImageDraw.Draw(overlay)
                overlay_draw.rectangle(
                    [bbox.x1, bbox.y1, bbox.x2, bbox.y2],
                    fill=(*color, 50)  # Semi-transparent fill
                )
                annotated_image = Image.alpha_composite(
                    annotated_image.convert('RGBA'), overlay
                ).convert('RGB')
                
                # Draw group label
                label = f"{group_id}_{i+1}"
                
                # Calculate label position (top-left of bbox with some padding)
                label_x = bbox.x1 + 2
                label_y = bbox.y1 - 20 if bbox.y1 > 20 else bbox.y1 + 2
                
                # Draw label background
                text_bbox = draw.textbbox((label_x, label_y), label, font=small_font)
                draw.rectangle(
                    [text_bbox[0]-2, text_bbox[1]-1, text_bbox[2]+2, text_bbox[3]+1],
                    fill='white',
                    outline=color,
                    width=1
                )
                
                # Draw label text
                draw.text((label_x, label_y), label, fill=color, font=small_font)
                
                # Update the mapping
                self.bbox_to_group_mapping[bbox.merged_id] = label
        
        # Save the annotated image
        output_path = os.path.join(output_dir, "annotated_original_image.png")
        annotated_image.save(output_path)
        self.log(f"Saved annotated original image to {output_path}")
        
        # Also create a legend image
        self._create_legend_image(output_dir)
    
    def _create_legend_image(self, output_dir: str):
        """Create a legend showing group colors and IDs"""
        self.log("Creating legend image")
        
        legend_width = 400
        legend_height = max(300, len(self.final_groups) * 25 + 50)
        
        legend_image = Image.new('RGB', (legend_width, legend_height), 'white')
        draw = ImageDraw.Draw(legend_image)
        
        try:
            font = ImageFont.truetype("arial.ttf", 12)
            title_font = ImageFont.truetype("arial.ttf", 16)
        except:
            font = ImageFont.load_default()
            title_font = ImageFont.load_default()
        
        # Draw title
        draw.text((10, 10), "Group Legend", fill='black', font=title_font)
        
        # Draw legend entries
        y_pos = 40
        for group_id, color in self.group_colors.items():
            # Draw color box
            draw.rectangle([10, y_pos, 30, y_pos + 15], fill=color, outline='black')
            
            # Draw group info
            group_size = len(self.final_groups[group_id])
            text = f"{group_id}: {group_size} boxes"
            draw.text((40, y_pos), text, fill='black', font=font)
            
            y_pos += 25
        
        # Save legend
        legend_path = os.path.join(output_dir, "group_legend.png")
        legend_image.save(legend_path)
        self.log(f"Saved legend to {legend_path}")
    
    def save_mapping(self, output_dir: str = "outputs"):
        """Save the mapping of original IDs to group IDs"""
        mapping_file = f"{output_dir}/bbox_mapping.json"
        
        # Enhanced mapping with group colors and coordinates
        enhanced_mapping = {}
        for original_id, group_label in self.bbox_to_group_mapping.items():
            # Find the bbox and its group
            bbox = None
            group_id = None
            
            for gid, boxes in self.final_groups.items():
                for box in boxes:
                    if box.original_id == original_id:
                        bbox = box
                        group_id = gid
                        break
                if bbox:
                    break
            
            if bbox and group_id:
                enhanced_mapping[str(original_id)] = {
                    "group_label": group_label,
                    "group_id": group_id,
                    "group_color": self.group_colors[group_id],
                    "original_coordinates": [bbox.x1, bbox.y1, bbox.x2, bbox.y2],
                    "bbox_type": bbox.bbox_type,
                    "source": bbox.source
                }
        
        with open(mapping_file, 'w') as f:
            json.dump(enhanced_mapping, f, indent=2)
        
        self.log(f"Saved enhanced mapping to {mapping_file}")
    
    def process(self, json_file_path: str, original_image_path: str = None, output_dir: str = "outputs"):
        """Main processing pipeline"""
        self.log("Starting BBox processing pipeline")
        
        # Load original image first if provided
        if original_image_path:
            try:
                self.original_image = Image.open(original_image_path)
                self.log(f"Loaded original image for cropping: {self.original_image.size}")
            except Exception as e:
                self.log(f"Error loading original image: {e}", "error")
                self.original_image = None
        
        self.load_bboxes(json_file_path)
        self.sort_bboxes()
        self.assign_sorted_ids()
        self.calculate_dimensions_and_identify_long_boxes()
        self.horizontal_grouping()
        self.vertical_grouping()
        self.merge_groups()
        self.generate_images(output_dir)
        
        # Draw on original image if provided
        if original_image_path:
            self.draw_groups_on_original_image(original_image_path, output_dir)
        
        self.save_mapping(output_dir)
        
        self.log("BBox processing pipeline completed")

    def generate_images(self, output_dir: str = "outputs", return_images: bool = False):
        """Steps 10-11: Generate images with grouped bboxes - combining H and V groups"""
        self.log("Steps 10-11: Generating images with combined H and V groups")
        
        os.makedirs(output_dir, exist_ok=True)
        all_groups = self.final_groups
        self.log(f"Processing {len(all_groups)} total groups (H and V combined)")
        
        # Use unified function for both modes
        image_count, generated_images = self._generate_combined_group_images(
            all_groups, "combined_groups", output_dir, 0
        )
        
        if return_images:
            self.log(f"Generated {image_count} combined images with direct return")
            return {
                'image_count': image_count,
                'generated_images': generated_images,  # List of (PIL.Image, filename, bbox_count)
                'saved_paths': [f"{output_dir}/{filename}" for _, filename, _ in generated_images]
            }
        else:
            self.log(f"Generated {image_count} combined images")
            return None

    def _generate_combined_group_images(self, groups: Dict[str, List[BBox]], base_name: str, 
                                   output_dir: str, start_image_count: int) -> Tuple[int, List[Tuple]]:
        """Generate images and return them directly along with saving - UNIFIED VERSION"""
        image_count = start_image_count
        current_y = self.PADDING + self.LABEL_TOP_PADDING
        current_image = Image.new('RGB', (self.IMAGE_WIDTH, self.IMAGE_HEIGHT), 'white')
        generated_images = []  # List of (PIL.Image, filename, bbox_count)
        
        try:
            font = ImageFont.truetype("arial.ttf", self.LABEL_FONT_SIZE)
        except:
            font = ImageFont.load_default()
        
        # Track current row state for efficient packing
        current_row_x = self.PADDING
        current_row_max_height = 0
        current_row_groups = []
        
        # Track groups in current image for bbox counting
        groups_in_current_image = []
        
        # Process horizontal groups first, then vertical groups
        h_groups = {k: v for k, v in groups.items() if k.startswith('H')}
        v_groups = {k: v for k, v in groups.items() if k.startswith('V')}
        
        self.log(f"PROCESSING: {len(h_groups)} horizontal groups, then {len(v_groups)} vertical groups")
        
        # Combine groups in order: H groups first, then V groups
        ordered_groups = list(h_groups.items()) + list(v_groups.items())
        
        for group_id, boxes in ordered_groups:
            self.log(f"PROCESSING: Starting group {group_id} with {len(boxes)} boxes")
            
            # Prepare scaled boxes with cropped images and calculate label widths
            scaled_boxes = []
            max_height = 0
            
            for i, bbox in enumerate(boxes):
                width, height = self.scale_bbox_for_display(bbox)
                cropped_image = self.crop_bbox_from_image(bbox)
                
                if cropped_image.size != (width, height):
                    cropped_image = cropped_image.resize((width, height), Image.Resampling.LANCZOS)
                
                label = f"{group_id}_{i+1}"
                label_width = self.calculate_label_width(label, font)
                
                scaled_boxes.append((bbox, width, height, label, cropped_image, label_width))
                max_height = max(max_height, height)
            
            # Calculate group width with dynamic gaps
            group_width = 0
            for i, (_, width, _, _, _, label_width) in enumerate(scaled_boxes):
                group_width += width
                if i < len(scaled_boxes) - 1:
                    next_bbox = scaled_boxes[i + 1]
                    dynamic_gap = self.calculate_dynamic_gap(width, label_width, next_bbox[1], next_bbox[5])
                    group_width += dynamic_gap
            
            total_group_height = max_height + self.LABEL_TOP_PADDING
            
            self.log(f"LAYOUT: Group {group_id} dimensions: {group_width}x{total_group_height} (with dynamic label gaps)")
            
            # Check if we can fit this group on the current row
            can_fit_on_current_row = (
                current_row_x + group_width + self.PADDING <= self.IMAGE_WIDTH and
                current_y + total_group_height <= self.IMAGE_HEIGHT
            )
            
            # Check if we should start a new row
            should_start_new_row = (
                len(current_row_groups) > 0 and  # There are groups in current row
                (not can_fit_on_current_row or  # Can't fit
                 current_row_x > self.EFFICIENT_PACKING_WIDTH)  # Current row is already long enough
            )
            
            if should_start_new_row:
                # Move to next row
                current_y += current_row_max_height + self.GROUP_GAP
                current_row_x = self.PADDING
                current_row_max_height = 0
                current_row_groups = []
                self.log(f"LAYOUT: Starting new row at Y={current_y} for group {group_id}")
                
                # Check if new row fits in current image
                if current_y + total_group_height > self.IMAGE_HEIGHT:
                    # Save current image and start new one
                    if current_y > self.PADDING + self.LABEL_TOP_PADDING:  # Only save if there's content
                        bbox_count = self._count_bboxes_in_image(groups_in_current_image)
                        filename = self._generate_filename(base_name, image_count, bbox_count)
                        output_path = f"{output_dir}/{filename}"
                        
                        # Save to disk (original behavior)
                        current_image.save(output_path)
                        
                        # Add to return list (new behavior)
                        generated_images.append((current_image.copy(), filename, bbox_count))
                        
                        self.log(f"SAVE: Saved {output_path} and added to return list ({bbox_count} bboxes)")
                    
                    image_count += 1
                    current_y = self.PADDING + self.LABEL_TOP_PADDING
                    current_row_x = self.PADDING
                    current_row_max_height = 0
                    current_row_groups = []
                    groups_in_current_image = []  # Reset for new image
                    current_image = Image.new('RGB', (self.IMAGE_WIDTH, self.IMAGE_HEIGHT), 'white')
                    self.log(f"NEW IMAGE: Started new image {image_count} for group {group_id}")
            
            # Add this group to current image tracking
            groups_in_current_image.append(group_id)
            
            # Place boxes in the group with dynamic spacing
            group_start_x = current_row_x
            current_x = group_start_x
            
            for i, (bbox, width, height, label, cropped_image, label_width) in enumerate(scaled_boxes):
                # ✅ FIX: Check if this individual icon will exceed image width
                if current_x + width > self.IMAGE_WIDTH - self.PADDING:
                    # Start new row for this icon
                    current_y += max_height + self.GROUP_GAP
                    current_x = self.PADDING
                    self.log(f"WRAP: Icon {label} wrapped to new row at Y={current_y}")
                    
                    # Check if new row fits in current image
                    if current_y + height > self.IMAGE_HEIGHT:
                        # Save current image and start new one
                        bbox_count = self._count_bboxes_in_image(groups_in_current_image)
                        filename = self._generate_filename(base_name, image_count, bbox_count)
                        output_path = f"{output_dir}/{filename}"
                        current_image.save(output_path)
                        generated_images.append((current_image.copy(), filename, bbox_count))
                        
                        # Start new image
                        image_count += 1
                        current_y = self.PADDING + self.LABEL_TOP_PADDING
                        current_x = self.PADDING
                        current_image = Image.new('RGB', (self.IMAGE_WIDTH, self.IMAGE_HEIGHT), 'white')
                        self.log(f"NEW IMAGE: Started new image {image_count} for icon {label}")
                
                # Calculate positions
                image_y = current_y
                label_y = current_y - self.LABEL_TOP_PADDING + 5
                
                # Paste the actual cropped image
                current_image.paste(cropped_image, (current_x, image_y))
                
                # Draw border around the image
                draw = ImageDraw.Draw(current_image)
                draw.rectangle([current_x, image_y, current_x + width, image_y + height], 
                             outline='lightgrey', width=self.BBOX_BORDER_WIDTH)
                
                # Draw label without background box
                text_x = current_x + width // 2
                
                if self.LABEL_BACKGROUND:
                    # Draw label background (if enabled)
                    text_bbox = draw.textbbox((text_x, label_y), label, font=font, anchor='mm')
                    draw.rectangle(
                        [text_bbox[0]-2, text_bbox[1]-1, text_bbox[2]+2, text_bbox[3]+1],
                        fill='white',
                        outline='black',
                        width=1
                    )
                
                # Draw label text
                draw.text((text_x, label_y), label, fill='black', font=font, anchor='mm')
                
                # Store mapping
                self.bbox_to_group_mapping[bbox.merged_id] = label
                
                self.log(f"PLACE: Placed {label} at ({current_x}, {image_y}) size {width}x{height}")
                
                # Move to next position with dynamic gap
                current_x += width
                
                # Add dynamic gap to next bbox if not the last one
                if i < len(scaled_boxes) - 1:
                    next_bbox = scaled_boxes[i + 1]
                    next_width = next_bbox[1]
                    next_label_width = next_bbox[5]
                    
                    dynamic_gap = self.calculate_dynamic_gap(width, label_width, next_width, next_label_width)
                    current_x += dynamic_gap
                    
                    self.log(f"SPACING: Added {dynamic_gap}px gap after {label} (label_width={label_width}px)")
            
            # Update row tracking
            current_row_x = current_x + self.SAME_ROW_GAP  # Add gap for next group
            current_row_max_height = max(current_row_max_height, total_group_height)
            current_row_groups.append(group_id)
            
            self.log(f"COMPLETE: Group {group_id} placed, next X position: {current_row_x}, row height: {current_row_max_height}")
        
        # Save final image if it has content
        if current_y > self.PADDING + self.LABEL_TOP_PADDING or len(current_row_groups) > 0:
            bbox_count = self._count_bboxes_in_image(groups_in_current_image)
            filename = self._generate_filename(base_name, image_count, bbox_count)
            output_path = f"{output_dir}/{filename}"
            
            # Save to disk
            current_image.save(output_path)
            
            # Add to return list
            generated_images.append((current_image.copy(), filename, bbox_count))
            
            self.log(f"SAVE: Saved final {output_path} and added to return list ({bbox_count} bboxes)")
            image_count += 1
        
        return image_count, generated_images


# INTEGRATION WRAPPER FUNCTIONS FOR MAIN.PY COMPATIBILITY
# These functions provide the same interface as the old seraphine_processor + group_image_generator

class FinalSeraphineProcessor:
    """
    Wrapper class that provides the same interface as the old SeraphineProcessor + GroupImageGenerator
    but uses the new BBoxProcessor internally for both grouping and image generation
    """
    
    def __init__(self, enable_timing: bool = True, enable_debug: bool = False):
        self.enable_timing = enable_timing
        self.enable_debug = enable_debug
        self.bbox_processor = BBoxProcessor(enable_logging=enable_debug)
    
    def process_detections(self, detections: List[Dict]) -> Dict[str, Any]:
        """
        Process detections using the new BBoxProcessor
        Maintains compatibility with old SeraphineProcessor interface
        
        Args:
            detections: List of detection dictionaries with 'bbox' key
            
        Returns:
            Dict containing grouping analysis and structured results (compatible with old format)
        """
        start_time = time.time()
        
        if self.enable_debug:
            debug_print(f"🧠 [FINAL SERAPHINE] Processing {len(detections)} detections...")
        
        # Create temporary JSON file for BBoxProcessor
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
            json.dump(detections, temp_file, indent=2)
            temp_json_path = temp_file.name
        
        try:
            # Load detections into BBoxProcessor
            self.bbox_processor.load_bboxes(temp_json_path)
            self.bbox_processor.sort_bboxes()
            self.bbox_processor.assign_sorted_ids()
            self.bbox_processor.calculate_dimensions_and_identify_long_boxes()
            self.bbox_processor.horizontal_grouping()
            self.bbox_processor.vertical_grouping()
            self.bbox_processor.merge_groups()
            
            # Convert results to old format for compatibility
            analysis = self._create_compatible_analysis(detections)
            
            elapsed = time.time() - start_time
            if self.enable_timing:
                debug_print(f"⏱️  Final Seraphine processing: {elapsed:.3f}s")
            
            return {
                'horizontal_groups': self._convert_to_old_group_format('H'),
                'vertical_groups': self._convert_to_old_group_format('V'),
                'final_groups': self._convert_final_groups_to_old_format(),
                'group_dict': self._create_group_dict(),
                'analysis': analysis,
                'processing_time': elapsed,
                'bbox_processor': self.bbox_processor,  # Store reference for image generation
                'grouped_items': len(detections)
            }
            
        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_json_path)
            except:
                pass
    
    def _bbox_to_dict(self, bbox: BBox) -> Dict:
        """Convert BBox object to dictionary format - SINGLE SOURCE OF TRUTH"""
        return {
            'bbox': [bbox.x1, bbox.y1, bbox.x2, bbox.y2],
            'id': bbox.original_id,
            'merged_id': bbox.merged_id,
            'type': bbox.bbox_type,
            'source': bbox.source,
            'confidence': bbox.confidence
        }

    def _convert_bbox_groups(self, groups_dict: Dict, output_format: str = 'list') -> Any:
        """Universal bbox group converter - eliminates all duplication"""
        if output_format == 'list':
            # For _convert_final_groups_to_old_format and _convert_to_old_group_format
            result = []
            for group_id, bbox_list in groups_dict.items():
                result.append([self._bbox_to_dict(bbox) for bbox in bbox_list])
            return result
        
        elif output_format == 'dict':
            # For _create_group_dict  
            result = {}
            for group_id, bbox_list in groups_dict.items():
                result[group_id] = [self._bbox_to_dict(bbox) for bbox in bbox_list]
            return result

    def _convert_to_old_group_format(self, group_type: str) -> List[List[Dict]]:
        """Convert new group format to old format"""
        if group_type == 'H':
            groups_dict = self.bbox_processor.horizontal_groups
        else:
            groups_dict = self.bbox_processor.vertical_groups
        return self._convert_bbox_groups(groups_dict, 'list')

    def _convert_final_groups_to_old_format(self) -> List[List[Dict]]:
        """Convert final groups to old format"""
        return self._convert_bbox_groups(self.bbox_processor.final_groups, 'list')

    def _create_group_dict(self) -> Dict[str, List[Dict]]:
        """Create group dictionary in old format"""
        return self._convert_bbox_groups(self.bbox_processor.final_groups, 'dict')

    def _create_compatible_analysis(self, detections: List[Dict]) -> Dict[str, Any]:
        """Create analysis compatible with old format"""
        total_detections = len(detections)
        total_groups = len(self.bbox_processor.final_groups)
        
        h_groups = len([g for g in self.bbox_processor.final_groups.keys() if g.startswith('H')])
        v_groups = len([g for g in self.bbox_processor.final_groups.keys() if g.startswith('V')])
        long_groups = len([g for g in self.bbox_processor.final_groups.keys() if 'L' in g])
        
        # Create group_details using helper function
        group_details = {}
        for group_id, bbox_list in self.bbox_processor.final_groups.items():
            group_details[group_id] = {
                'group_id': group_id,
                'size': len(bbox_list),
                'type': 'horizontal' if group_id.startswith('H') else 'vertical' if group_id.startswith('V') else 'long_box',
                'bboxes': [self._bbox_to_dict(bbox) for bbox in bbox_list]  # Use helper
            }
        
        return {
            'total_detections': total_detections,
            'total_groups': total_groups,
            'horizontal_groups': h_groups,
            'vertical_groups': v_groups,
            'long_box_groups': long_groups,
            'grouping_efficiency': total_groups / total_detections if total_detections > 0 else 0,
            'group_details': group_details,
            'ungrouped_detections': [],
            'grouped_items': total_detections,
            'ungrouped_items': 0
        }