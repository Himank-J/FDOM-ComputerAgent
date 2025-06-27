"""
Intelligent bounding box merger utility
Implements overlap rules for YOLO and OCR detection results.
No imports from original files allowed.
"""
import numpy as np
from typing import List, Dict, Any, Tuple
from .helpers import debug_print

def calculate_iou(box1: List[int], box2: List[int]) -> float:
    """Calculate IoU between two boxes in [x1, y1, x2, y2] format"""
    x1_1, y1_1, x2_1, y2_1 = box1
    x1_2, y1_2, x2_2, y2_2 = box2
    
    # Calculate intersection
    x1_i = max(x1_1, x1_2)
    y1_i = max(y1_1, y1_2)
    x2_i = min(x2_1, x2_2)
    y2_i = min(y2_1, y2_2)
    
    if x2_i <= x1_i or y2_i <= y1_i:
        return 0.0
    
    intersection = (x2_i - x1_i) * (y2_i - y1_i)
    area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
    area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
    union = area1 + area2 - intersection
    
    return intersection / union if union > 0 else 0.0

def is_box_inside(inner_box: List[int], outer_box: List[int], threshold: float = 0.8) -> bool:
    """Check if inner_box is inside outer_box with given threshold"""
    x1_i, y1_i, x2_i, y2_i = inner_box
    x1_o, y1_o, x2_o, y2_o = outer_box
    
    # Calculate intersection
    x1_int = max(x1_i, x1_o)
    y1_int = max(y1_i, y1_o)
    x2_int = min(x2_i, x2_o)
    y2_int = min(y2_i, y2_o)
    
    if x2_int <= x1_int or y2_int <= y1_int:
        return False
    
    intersection = (x2_int - x1_int) * (y2_int - y1_int)
    inner_area = (x2_i - x1_i) * (y2_i - y1_i)
    
    # Check if most of the inner box is contained in outer box
    return (intersection / inner_area) >= threshold if inner_area > 0 else False

def calculate_box_area(box: List[int]) -> float:
    """Calculate the area of a bounding box in [x1, y1, x2, y2] format"""
    x1, y1, x2, y2 = box
    width = x2 - x1
    height = y2 - y1
    
    # Return 0 for invalid boxes
    if width <= 0 or height <= 0:
        return 0.0
    
    return width * height

def filter_valid_boxes(detections: List[Dict[str, Any]], min_area: float = 1.0) -> List[Dict[str, Any]]:
    """
    Filter out boxes with zero or very small areas
    
    Args:
        detections: List of detection dictionaries with 'bbox' key
        min_area: Minimum area threshold (default: 1.0 pixel)
        
    Returns:
        List of valid detections with area > min_area
    """
    valid_detections = []
    
    for detection in detections:
        bbox = detection['bbox']
        area = calculate_box_area(bbox)
        
        if area > min_area:
            valid_detections.append(detection)
    
    return valid_detections

class BBoxMerger:
    """
    Intelligent bounding box merger that combines YOLO and OCR detections
    according to specified overlap rules.
    """
    
    def __init__(self, iou_threshold: float = 0.9, containment_threshold: float = 0.8, 
                 min_area: float = 1.0, enable_timing: bool = True):
        """
        Initialize merger with thresholds
        
        Args:
            iou_threshold: IoU threshold for considering boxes as overlapping (default: 0.9, matching OmniParser)
            containment_threshold: Threshold for considering one box inside another
            min_area: Minimum box area in pixels (default: 1.0)
            enable_timing: Whether to print timing information
        """
        self.iou_threshold = iou_threshold
        self.containment_threshold = containment_threshold
        self.min_area = min_area
        self.enable_timing = enable_timing
    
    def _remove_yolo_self_overlaps(self, yolo_detections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Stage 1: Remove overlapping YOLO boxes among themselves
        Keep the smaller box when there's significant overlap (following OmniParser logic)
        
        Args:
            yolo_detections: List of YOLO detection dictionaries
            
        Returns:
            List of non-overlapping YOLO detections
        """
        if self.enable_timing:
            debug_print(f"  🔄 Stage 1: Removing YOLO self-overlaps...")
        
        filtered_yolo = []
        
        for i, yolo1 in enumerate(yolo_detections):
            bbox1 = yolo1['bbox']
            area1 = calculate_box_area(bbox1)
            is_valid_box = True
            
            # Check against all other YOLO boxes
            for j, yolo2 in enumerate(yolo_detections):
                if i == j:
                    continue
                    
                bbox2 = yolo2['bbox']
                area2 = calculate_box_area(bbox2)
                
                iou = calculate_iou(bbox1, bbox2)
                
                # If significant overlap and current box is larger, discard it (keep smaller box)
                if iou > self.iou_threshold and area1 > area2:
                    is_valid_box = False
                    if self.enable_timing:
                        debug_print(f"    🗑️ Discarding larger YOLO box (area: {area1:.1f}) in favor of smaller (area: {area2:.1f}), IoU: {iou:.3f}")
                    break
            
            if is_valid_box:
                filtered_yolo.append(yolo1)
        
        if self.enable_timing:
            debug_print(f"    ✅ YOLO self-overlap removal: {len(yolo_detections)} -> {len(filtered_yolo)} boxes")
        
        return filtered_yolo
    
    def _filter_yolo_with_many_ocr(self, yolo_detections: List[Dict[str, Any]], 
                                   ocr_detections: List[Dict[str, Any]], 
                                   max_ocr_inside: int = 2) -> List[Dict[str, Any]]:
        """
        Stage 1.5: Filter out YOLO boxes containing more than max_ocr_inside OCR boxes
        This prevents false positive YOLO detections that encompass large text regions
        
        Args:
            yolo_detections: YOLO detections after self-overlap removal
            ocr_detections: OCR detections
            max_ocr_inside: Maximum number of OCR boxes allowed inside a YOLO box (default: 2)
            
        Returns:
            Filtered YOLO detections
        """
        if self.enable_timing:
            debug_print(f"  🔄 Stage 1.5: Filtering YOLO boxes with >{max_ocr_inside} OCR inside...")
        
        filtered_yolo = []
        
        for yolo_det in yolo_detections:
            yolo_bbox = yolo_det['bbox']
            ocr_inside_count = 0
            
            # Count how many OCR boxes are inside this YOLO box
            for ocr_det in ocr_detections:
                ocr_bbox = ocr_det['bbox']
                
                # Check if OCR box is inside YOLO box
                if is_box_inside(ocr_bbox, yolo_bbox, self.containment_threshold):
                    ocr_inside_count += 1
                    
                    # Early exit if we exceed the threshold
                    if ocr_inside_count > max_ocr_inside:
                        break
            
            if ocr_inside_count <= max_ocr_inside:
                filtered_yolo.append(yolo_det)
                if self.enable_timing and ocr_inside_count > 0:
                    debug_print(f"    ✅ Keeping YOLO box with {ocr_inside_count} OCR inside")
            else:
                if self.enable_timing:
                    debug_print(f"    🗑️ Discarding YOLO box with {ocr_inside_count} OCR inside (>{max_ocr_inside})")
        
        if self.enable_timing:
            removed_count = len(yolo_detections) - len(filtered_yolo)
            debug_print(f"    ✅ YOLO OCR-density filter: {len(yolo_detections)} -> {len(filtered_yolo)} boxes ({removed_count} removed)")
        
        return filtered_yolo
    
    def _merge_yolo_ocr_relationships(self, yolo_detections: List[Dict[str, Any]], 
                                    ocr_detections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Stage 2: Handle YOLO-OCR relationships
        Apply containment rules and content aggregation
        
        Args:
            yolo_detections: Filtered YOLO detections from stage 1
            ocr_detections: OCR detections
            
        Returns:
            Final merged detections
        """
        if self.enable_timing:
            debug_print(f"  🔄 Stage 2: Merging YOLO-OCR relationships...")
        
        merged_detections = []
        ocr_used = [False] * len(ocr_detections)
        
        # Process each YOLO box
        for yolo_det in yolo_detections:
            yolo_bbox = yolo_det['bbox']
            box_added = False
            
            # Check relationships with all OCR boxes
            for j, ocr_det in enumerate(ocr_detections):
                if ocr_used[j]:
                    continue
                    
                ocr_bbox = ocr_det['bbox']
                iou = calculate_iou(yolo_bbox, ocr_bbox)
                
                if iou > self.iou_threshold:
                    # Check containment relationships
                    yolo_inside_ocr = is_box_inside(yolo_bbox, ocr_bbox, self.containment_threshold)
                    ocr_inside_yolo = is_box_inside(ocr_bbox, yolo_bbox, self.containment_threshold)
                    
                    if yolo_inside_ocr:
                        # YOLO inside OCR -> Keep OCR, discard YOLO
                        if not box_added:  # Only add once
                            merged_detections.append(ocr_det.copy())
                            box_added = True
                            if self.enable_timing:
                                debug_print(f"    🔄 YOLO inside OCR -> Keeping OCR (IoU: {iou:.3f})")
                        ocr_used[j] = True
                        break  # YOLO can only be inside one OCR box
                        
                    elif ocr_inside_yolo:
                        # OCR inside YOLO -> Keep YOLO, mark OCR as used
                        yolo_det['type'] = 'text'  # ← ONLY CHANGE: Set type to text
                        # Note: We'll add the YOLO box after checking all OCR boxes
                        ocr_used[j] = True
                        if self.enable_timing:
                            debug_print(f"    🔄 OCR inside YOLO -> Will keep YOLO as TEXT (IoU: {iou:.3f})")
            
            # If YOLO wasn't absorbed into an OCR box, add it
            if not box_added:
                merged_detections.append(yolo_det.copy())
        
        # Add remaining unused OCR detections
        for j, ocr_det in enumerate(ocr_detections):
            if not ocr_used[j]:
                merged_detections.append(ocr_det.copy())
        
        if self.enable_timing:
            debug_print(f"    ✅ YOLO-OCR relationship merge: {len(yolo_detections)} YOLO + {len(ocr_detections)} OCR -> {len(merged_detections)} final")
        
        return merged_detections
    
    def merge_detections(self, yolo_detections: List[Dict[str, Any]], 
                        ocr_detections: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Merge YOLO and OCR detections using enhanced three-stage processing:
        Stage 1: Remove YOLO self-overlaps (keep smaller boxes)
        Stage 1.5: Filter YOLO boxes containing too many OCR boxes
        Stage 2: Handle YOLO-OCR relationships with containment rules
        
        Args:
            yolo_detections: List of YOLO detection dictionaries
            ocr_detections: List of OCR detection dictionaries
            
        Returns:
            Tuple of (merged_detections, merge_stats)
        """
        import time
        start_time = time.time()
        
        # Pre-filtering: Remove zero-area boxes
        original_yolo_count = len(yolo_detections)
        original_ocr_count = len(ocr_detections)
        
        yolo_detections = filter_valid_boxes(yolo_detections, self.min_area)
        ocr_detections = filter_valid_boxes(ocr_detections, self.min_area)
        
        filtered_yolo_count = len(yolo_detections)
        filtered_ocr_count = len(ocr_detections)
        
        if self.enable_timing:
            debug_print(f"\n🔗 Starting enhanced three-stage bbox merging...")
            debug_print(f"  📏 Pre-filtering (zero-area removal):")
            debug_print(f"    YOLO: {original_yolo_count} -> {filtered_yolo_count} ({original_yolo_count - filtered_yolo_count} removed)")
            debug_print(f"    OCR: {original_ocr_count} -> {filtered_ocr_count} ({original_ocr_count - filtered_ocr_count} removed)")
            debug_print(f"  ⚙️ Thresholds: IoU={self.iou_threshold}, Containment={self.containment_threshold}, MinArea={self.min_area}")
        
        # 🔧 STAGE 1: Remove YOLO self-overlaps
        stage1_start = time.time()
        yolo_after_stage1 = self._remove_yolo_self_overlaps(yolo_detections)
        stage1_time = time.time() - stage1_start
        
        # 🔧 STAGE 1.5: Filter YOLO boxes with too many OCR inside (NEW!)
        stage1_5_start = time.time()
        yolo_after_stage1_5 = self._filter_yolo_with_many_ocr(yolo_after_stage1, ocr_detections, max_ocr_inside=2)
        stage1_5_time = time.time() - stage1_5_start
        
        # 🔧 STAGE 2: Handle YOLO-OCR relationships  
        stage2_start = time.time()
        final_detections = self._merge_yolo_ocr_relationships(yolo_after_stage1_5, ocr_detections)
        stage2_time = time.time() - stage2_start
        
        # Reassign IDs to final detections
        for i, det in enumerate(final_detections):
            det['merged_id'] = i
        
        # Compile comprehensive statistics
        merge_stats = {
            'total_input': original_yolo_count + original_ocr_count,
            'total_filtered_input': filtered_yolo_count + filtered_ocr_count,
            'total_output': len(final_detections),
            'yolo_input': original_yolo_count,
            'yolo_filtered_input': filtered_yolo_count,
            'yolo_after_stage1': len(yolo_after_stage1),
            'yolo_after_stage1_5': len(yolo_after_stage1_5),
            'ocr_input': original_ocr_count,
            'ocr_filtered_input': filtered_ocr_count,
            'zero_area_removed': (original_yolo_count - filtered_yolo_count) + (original_ocr_count - filtered_ocr_count),
            'yolo_self_overlaps_removed': filtered_yolo_count - len(yolo_after_stage1),
            'yolo_ocr_density_removed': len(yolo_after_stage1) - len(yolo_after_stage1_5),
            'stage1_time': stage1_time,
            'stage1_5_time': stage1_5_time,
            'stage2_time': stage2_time,
            'total_merge_time': time.time() - start_time
        }
        
        if self.enable_timing:
            debug_print(f"\n🎯 Enhanced three-stage merge completed in {merge_stats['total_merge_time']:.3f}s")
            debug_print(f"  📊 Processing pipeline:")
            debug_print(f"    Input: {merge_stats['total_input']} boxes")
            debug_print(f"    After area filtering: {merge_stats['total_filtered_input']} boxes")
            debug_print(f"    After Stage 1 (YOLO self-overlap): {merge_stats['yolo_after_stage1']} YOLO + {merge_stats['ocr_filtered_input']} OCR")
            debug_print(f"    After Stage 1.5 (YOLO OCR-density filter): {merge_stats['yolo_after_stage1_5']} YOLO + {merge_stats['ocr_filtered_input']} OCR")
            debug_print(f"    Final output: {merge_stats['total_output']} boxes")
            debug_print(f"  ⏱️ Timing: Stage1={stage1_time:.3f}s, Stage1.5={stage1_5_time:.3f}s, Stage2={stage2_time:.3f}s")
            debug_print(f"  🗑️ Removed: {merge_stats['zero_area_removed']} zero-area, {merge_stats['yolo_self_overlaps_removed']} YOLO self-overlaps, {merge_stats['yolo_ocr_density_removed']} YOLO with >2 OCR")
        
        return final_detections, merge_stats