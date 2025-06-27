"""
Seraphine Pre-Processor
Creates group visualization overlay on original screenshots
Integrates with seraphine_processor.py to visualize detected groups
Calls Gemini for supergroup analysis
"""

import os
import asyncio
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import cv2
import numpy as np
from PIL import Image
import argparse

# Gemini imports
try:
    from google import genai
    from google.genai.errors import ServerError
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("⚠️  Warning: google-genai not installed. Gemini analysis will be skipped.")

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("⚠️  Warning: python-dotenv not installed. Make sure GEMINI_API_KEY is set manually.")


def create_group_visualization(final_groups: Dict, original_image_path: str, 
                             output_dir: str = "outputs", app_name: str = "app") -> str:
    """
    Create group visualization overlay on original screenshot using EXACT labeling from postprocessor
    
    Args:
        final_groups: Dictionary of groups from seraphine_processor (e.g., {'H0': [bbox1, bbox2], 'V1': [bbox3]})
        original_image_path: Path to S001.png screenshot  
        output_dir: Output directory for saving result
        app_name: App name for filename
        
    Returns:
        Path to saved visualization image
    """    
    # Load original image using cv2 (same as postprocessor)
    try:
        image = cv2.imread(original_image_path)
        if image is None:
            raise ValueError(f"Could not load image: {original_image_path}")
        
        img_height, img_width = image.shape[:2]
        # print(f"[PREPROCESSOR] Loaded image: {img_width}x{img_height}")
    except Exception as e:
        print(f"[PREPROCESSOR ERROR] Failed to load image: {e}")
        return ""
    
    # ✅ PRE-CALCULATE ALL GROUP BOUNDS to avoid label conflicts
    all_group_bounds = {}
    for group_id, bboxes in final_groups.items():
        if bboxes:
            all_group_bounds[group_id] = _calculate_group_bounds(bboxes)
    
    # ✅ EXACT SAME COLOR PALETTE as postprocessor
    group_colors = [
        (255, 0, 0),      # Red
        (0, 255, 0),      # Green
        (0, 0, 255),      # Blue
        (255, 0, 255),    # Magenta
        (0, 255, 255),    # Cyan
        (255, 165, 0),    # Orange
        (128, 0, 128),    # Purple
        (255, 192, 203),  # Pink
        (0, 128, 0),      # Dark Green
        (128, 128, 0),    # Olive
        (0, 0, 128),      # Navy
        (128, 0, 0),      # Maroon
        (0, 128, 128),    # Teal
        (220, 220, 220),  # Silver 
        (255, 20, 147),   # Deep Pink
        (50, 205, 50),    # Lime Green
        (255, 140, 0),    # Dark Orange
        (138, 43, 226),   # Blue Violet
        (220, 20, 60),    # Crimson
        (55, 55, 0),      # Yellow
        (0, 0, 0),        # Black
        (139, 69, 19),    # Saddle Brown
        (255, 69, 0),     # Orange Red
        (75, 0, 130),     # Indigo
        (0, 100, 0),      # Forest Green
        (233, 150, 122),  # Dark Salmon
        (255, 215, 0),    # Gold
        (0, 191, 255),    # Deep Sky Blue
        (34, 139, 34),    # Forest Green (darker)
        (218, 112, 214),  # Orchid
        (255, 105, 180),  # Hot Pink
        (47, 79, 79),     # Dark Slate Gray
        (255, 99, 71),    # Tomato
        (72, 61, 139),    # Dark Slate Blue
        (154, 205, 50),   # Yellow Green
        (128, 0, 255),    # Violet
        (255, 0, 127),    # Rose
        (0, 255, 127),    # Spring Green
        (64, 224, 208),   # Turquoise
        (184, 134, 11),   # Dark Goldenrod
    ]
    
    # ✅ EXACT SAME DRAWING PARAMETERS as postprocessor
    font = cv2.FONT_HERSHEY_DUPLEX
    text_scale = 0.4
    thickness = 2  # Thin 1px lines
    text_thickness = 1
    
    # Track label positions to avoid overlaps (same as postprocessor)
    existing_labels = []
    color_idx = 0
    processed_groups = 0
    
    # ✅ PHASE 1: DRAW ALL RECTANGLES FIRST
    for group_id, bboxes in final_groups.items():
        if not bboxes:  # Skip empty groups
            continue
            
        # Get color (RGB to BGR conversion same as postprocessor)
        color_rgb = group_colors[color_idx % len(group_colors)]
        color_bgr = (color_rgb[2], color_rgb[1], color_rgb[0])  # RGB to BGR
        color_idx += 1
                
        # ✅ EXACT SAME GROUP BOUNDS CALCULATION as postprocessor
        group_bbox = _calculate_group_bounds(bboxes)
        x1, y1, x2, y2 = group_bbox
        
        if x1 == x2 or y1 == y2:  # Invalid bbox
            continue
        
        # ✅ DRAW RECTANGLE ONLY
        cv2.rectangle(image, (x1, y1), (x2, y2), color_bgr, thickness)
    
    # ✅ PHASE 2: DRAW ALL LABELS ON TOP
    color_idx = 0  # Reset color index
    existing_labels = []  # Reset label tracking
    
    for group_id, bboxes in final_groups.items():
        if not bboxes:  # Skip empty groups
            continue
            
        # Get same color as rectangle
        color_rgb = group_colors[color_idx % len(group_colors)]
        color_bgr = (color_rgb[2], color_rgb[1], color_rgb[0])  # RGB to BGR
        color_idx += 1
                
        # ✅ EXACT SAME GROUP BOUNDS CALCULATION as postprocessor
        group_bbox = _calculate_group_bounds(bboxes)
        x1, y1, x2, y2 = group_bbox
        
        if x1 == x2 or y1 == y2:  # Invalid bbox
            continue
        
        # ✅ GET OTHER GROUP BOUNDS (exclude current group)
        other_group_bounds = [bounds for gid, bounds in all_group_bounds.items() if gid != group_id]
        
        # ✅ FIND OPTIMAL LABEL POSITION
        label_x, label_y = _find_optimal_label_position(
            group_bbox, group_id, font, text_scale, 
            img_width, img_height, existing_labels, other_group_bounds
        )
        
        # ✅ DRAW LABEL BACKGROUND AND TEXT
        (text_w, text_h), _ = cv2.getTextSize(group_id, font, text_scale, text_thickness)
        
        bg_padding = 3
        bg_x1 = label_x - bg_padding
        bg_y1 = label_y - text_h - bg_padding
        bg_x2 = label_x + text_w + bg_padding
        bg_y2 = label_y + bg_padding
        
        # Draw colored background
        cv2.rectangle(image, (bg_x1, bg_y1), (bg_x2, bg_y2), color_bgr, cv2.FILLED)
        # Draw white border
        # cv2.rectangle(image, (bg_x1, bg_y1), (bg_x2, bg_y2), (220, 220, 220), 1)
        
        # ✅ DRAW TEXT ON TOP
        cv2.putText(image, group_id, (label_x, label_y), font, text_scale, 
                   (255, 255, 255), text_thickness, cv2.LINE_AA)
        
        # Track this label position
        label_rect = (bg_x1, bg_y1, bg_x2, bg_y2)
        existing_labels.append(label_rect)
        
        processed_groups += 1
    
    # Save the result
    os.makedirs(output_dir, exist_ok=True)
    output_filename = f"{app_name}_seraphine_groups.png"
    output_path = os.path.join(output_dir, output_filename)
    
    cv2.imwrite(output_path, image)
    # print(f"[PREPROCESSOR] Saved group visualization: {output_path} ({processed_groups} groups)")
    
    # Return path for later Gemini analysis by the main pipeline
    return output_path


def _load_preprocessor_prompt() -> str:
    """Load the supergroup analysis prompt from preprocessor_prompt.txt"""
    module_dir = os.path.dirname(os.path.abspath(__file__))
    prompt_path = os.path.join(module_dir, "preprocessor_prompt.txt")
    
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            prompt_content = f.read().strip()
        # print(f"[PREPROCESSOR] ✅ Loaded prompt ({len(prompt_content)} characters)")
        return prompt_content
    except FileNotFoundError:
        print(f"[PREPROCESSOR ERROR] Prompt file not found: {prompt_path}")
        return ""


# Add a separate async function for the pipeline to call
async def analyze_supergroups_with_gemini(image_path: str) -> Optional[str]:
    """Analyze the group visualization image with Gemini (to be called by async pipeline)"""
    
    if not GEMINI_AVAILABLE:
        print(f"[PREPROCESSOR] ⚠️  Skipping Gemini analysis (not available)")
        return None
        
    # Load prompt
    prompt = _load_preprocessor_prompt()
    if not prompt:
        return None
    
    # Initialize Gemini client
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print(f"[PREPROCESSOR ERROR] GEMINI_API_KEY not found in environment variables")
        return None
    
    client = genai.Client(api_key=api_key)
    
    try:
        # Load image with debugging
        image = Image.open(image_path)
        # ✅ SCALE SMALL IMAGES FOR BETTER GEMINI ANALYSIS
        width, height = image.size
        if width < 200 and height < 200:
            # Scale maintaining aspect ratio - make larger dimension 400px
            scale_factor = 400 / max(width, height)
            new_width = int(width * scale_factor)
            new_height = int(height * scale_factor)
            
            # Resize using high-quality resampling
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            print(f"[PREPROCESSOR DEBUG] ✅ Scaled small image: {width}x{height} → {new_width}x{new_height}")
        else:
            print(f"[PREPROCESSOR DEBUG] Image size OK: {width}x{height}, no scaling needed")
        
        # Call Gemini API
        response = await client.aio.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents=[prompt, image],
        )
        
        # # Print raw results on console
        # print(f"\n{'='*80}")
        # print(f"🤖 GEMINI SUPERGROUP ANALYSIS RESULTS")
        # print(f"{'='*80}")
        # print(response.text)
        # print(f"{'='*80}\n")
        
        return response.text
        
    except ServerError as e:
        print(f"[PREPROCESSOR ERROR] Gemini server error: {e}")
        return None
    except Exception as e:
        print(f"[PREPROCESSOR ERROR] Gemini analysis error: {e}")
        return None


def _calculate_group_bounds(bboxes) -> Tuple[int, int, int, int]:
    """Calculate bounding box that encompasses all bboxes in a group (same as postprocessor)"""
    if not bboxes:
        return 0, 0, 0, 0
    
    # Collect all coordinates
    x1_coords, y1_coords, x2_coords, y2_coords = [], [], [], []
    
    for bbox in bboxes:
        x1, y1, x2, y2 = bbox.x1, bbox.y1, bbox.x2, bbox.y2
        x1_coords.append(x1)
        y1_coords.append(y1)
        x2_coords.append(x2)
        y2_coords.append(y2)
    
    if not x1_coords:
        return 0, 0, 0, 0
    
    # Calculate extreme coordinates
    min_x = min(x1_coords)
    min_y = min(y1_coords)
    max_x = max(x2_coords)
    max_y = max(y2_coords)
    
    return min_x, min_y, max_x, max_y


def _find_optimal_label_position(group_bbox: Tuple[int, int, int, int], 
                               label: str, font, text_scale: float,
                               img_width: int, img_height: int,
                               existing_labels: List[Tuple],
                               other_group_bounds: List[Tuple]) -> Tuple[int, int]:
    """Find optimal position for group label to avoid overlaps AND other group boundaries"""
    x1, y1, x2, y2 = group_bbox
    
    # Calculate text dimensions
    (text_w, text_h), _ = cv2.getTextSize(label, font, text_scale, 1)
    
    # ✅ EXACT SAME CANDIDATE POSITIONS as postprocessor
    candidate_positions = [
        (x1, y1 - 0),                    # Above top-left
        (x1, y2 + text_h + 0),           # Below bottom-left
        (x2 - text_w, y1 - 0),           # Above top-right
        (x2 - text_w, y2 + text_h + 0),  # Below bottom-right
        (x1 + 0, y1 + text_h + 0),        # Inside top-left
        (x2 - text_w - 0, y1 + text_h + 0), # Inside top-right
    ]
    
    for text_x, text_y in candidate_positions:
        # Check bounds
        if (text_x >= 0 and text_y >= text_h and 
            text_x + text_w <= img_width and text_y <= img_height):
            
            # Check overlap with existing labels
            label_rect = (text_x, text_y - text_h, text_x + text_w, text_y)
            overlap = False
            
            for existing_rect in existing_labels:
                if _rectangles_overlap(label_rect, existing_rect):
                    overlap = True
                    break
            
            if not overlap:
                return text_x, text_y
    
    # Fallback: use first position even if it overlaps
    return candidate_positions[0]


def _rectangles_overlap(rect1: Tuple, rect2: Tuple) -> bool:
    """Check if two rectangles overlap (EXACT COPY from postprocessor)"""
    x1_1, y1_1, x2_1, y2_1 = rect1
    x1_2, y1_2, x2_2, y2_2 = rect2
    
    return not (x2_1 < x1_2 or x2_2 < x1_1 or y2_1 < y1_2 or y2_2 < y1_1)


def integrate_supergroup_analysis(seraphine_analysis: Dict, supergroup_analysis_text: str) -> Dict:
    """
    Integrate supergroup analysis results into the existing seraphine analysis structure
    Updates group_details with explore, navigation, state_change, file_loader, metadata, and groups_name fields
    Then processes merge suggestions as the final step
    
    Args:
        seraphine_analysis: Original seraphine analysis with 'analysis' section
        supergroup_analysis_text: Raw Gemini JSON response text
        
    Returns:
        Updated seraphine_analysis with integrated supergroup information and merges applied
    """
    print(f"[PREPROCESSOR] 🔄 Integrating enriched supergroup analysis into seraphine structure...")
    
    try:
        import json
        import re
        
        # Extract JSON from the response (handle ```json wrapper)
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', supergroup_analysis_text, re.DOTALL)
        if json_match:
            json_text = json_match.group(1)
        else:
            # Try to find JSON without wrapper
            json_text = supergroup_analysis_text.strip()
        
        supergroup_data = json.loads(json_text)
        print(f"[PREPROCESSOR] ✅ Parsed supergroup JSON successfully")
        
        # ✅ EXTRACT ALL CATEGORIES WITH GROUP NAMES
        groups_to_explore = {item.get('group_id'): item.get('group_name', 'explore') 
                           for item in supergroup_data.get('groups_to_explore', [])}
        
        groups_causing_navigation = {item.get('group_id'): item.get('group_name', 'navigation') 
                                   for item in supergroup_data.get('groups_causing_navigation', [])}
        
        groups_causing_state_change = {item.get('group_id'): item.get('group_name', 'state_change') 
                                     for item in supergroup_data.get('groups_causing_state_change', [])}
        
        file_loader_zones = {item.get('group_id'): item.get('group_name', 'file_loader') 
                           for item in supergroup_data.get('file_loader_zones', [])}
        
        file_metadata_zones = {item.get('group_id'): item.get('group_name', 'metadata') 
                             for item in supergroup_data.get('file_metadata_zones', [])}
        
        # Handle primary_interaction_zone (single object, not list)
        primary_interaction_zone = {}
        primary_zone = supergroup_data.get('primary_interaction_zone', {})
        if primary_zone and 'id' in primary_zone:
            primary_interaction_zone[primary_zone['id']] = "primary_interaction"
        
        # Handle groups_to_ignore (can have group_ids list or single group_id)
        groups_to_ignore_list = supergroup_data.get('groups_to_ignore', [])
        groups_to_ignore = set()
        for item in groups_to_ignore_list:
            if 'group_ids' in item:
                groups_to_ignore.update(item['group_ids'])
            elif 'group_id' in item:
                groups_to_ignore.add(item['group_id'])
        
        # ✅ EXTRACT MERGE SUGGESTIONS (FIXED - look in correct location)
        merge_suggestions = []
        merge_suggestions_data = supergroup_data.get('merge_suggestions', [])
        for item in merge_suggestions_data:
            if 'merge_ids' in item:
                merge_suggestions.append({
                    'merge_ids': item['merge_ids'],
                    'group_name': item.get('group_name', 'merged_group'),
                    'reason': item.get('reason', 'Merge suggested by Gemini')
                })
        
        # ✅ CREATE SETS FOR BOOLEAN LOGIC (FIXED - ensure variables are created)
        navigation_groups = set(groups_causing_navigation.keys()) if groups_causing_navigation else set()
        state_change_groups = set(groups_causing_state_change.keys()) if groups_causing_state_change else set()
        file_loader_groups = set(file_loader_zones.keys()) if file_loader_zones else set()
        metadata_groups = set(file_metadata_zones.keys()) if file_metadata_zones else set()
        primary_groups = set(primary_interaction_zone.keys()) if primary_interaction_zone else set()
        explore_groups = set(groups_to_explore.keys()) if groups_to_explore else set()
        
        # Action categories that make explore = true (unless overridden)
        action_groups = (explore_groups | navigation_groups | state_change_groups | 
                        file_loader_groups | primary_groups)
        
        # Override groups that NEVER get explore = true
        override_groups = groups_to_ignore | metadata_groups
        
        # Create a deep copy of seraphine_analysis to avoid modifying original
        updated_analysis = seraphine_analysis.copy()
        updated_analysis['analysis'] = seraphine_analysis['analysis'].copy()
        updated_analysis['analysis']['group_details'] = seraphine_analysis['analysis']['group_details'].copy()
        
        # ✅ STEP 1: UPDATE EACH GROUP WITH BOOLEAN FIELDS
        groups_updated = 0
        explore_true_count = 0
        explore_false_count = 0
        
        for group_id, group_info in updated_analysis['analysis']['group_details'].items():
            # Create a copy of group_info to avoid modifying original
            updated_group_info = group_info.copy()
            
            # ✅ EXPLORE LOGIC WITH OVERRIDE RULE
            if group_id in override_groups:
                # OVERRIDE: Never explore if in ignore or metadata zones
                updated_group_info['explore'] = False
                explore_false_count += 1
            elif group_id in action_groups:
                # Action categories get explore = true
                updated_group_info['explore'] = True
                explore_true_count += 1
            else:
                # Unclassified groups
                updated_group_info['explore'] = False
                explore_false_count += 1
            
            # ✅ INDIVIDUAL BOOLEAN FIELDS
            updated_group_info['navigation'] = group_id in navigation_groups
            updated_group_info['state_change'] = group_id in state_change_groups
            updated_group_info['file_loader'] = group_id in file_loader_groups
            updated_group_info['metadata'] = group_id in metadata_groups
            
            # ✅ GROUP NAME WITH PRIORITY LOGIC
            if group_id in groups_to_explore:
                updated_group_info['groups_name'] = groups_to_explore[group_id]
            elif group_id in groups_causing_navigation:
                updated_group_info['groups_name'] = groups_causing_navigation[group_id]
            elif group_id in groups_causing_state_change:
                updated_group_info['groups_name'] = groups_causing_state_change[group_id]
            elif group_id in file_loader_zones:
                updated_group_info['groups_name'] = file_loader_zones[group_id]
            elif group_id in file_metadata_zones:
                updated_group_info['groups_name'] = file_metadata_zones[group_id]
            elif group_id in primary_interaction_zone:
                updated_group_info['groups_name'] = primary_interaction_zone[group_id]
            elif group_id in groups_to_ignore:
                updated_group_info['groups_name'] = "ignore"
            else:
                updated_group_info['groups_name'] = "unclassified"
            
            # Update the group_details
            updated_analysis['analysis']['group_details'][group_id] = updated_group_info
            groups_updated += 1
        
        # ✅ STEP 2: PROCESS MERGE SUGGESTIONS (FINAL STEP)
        merges_processed = 0
        groups_merged = 0
        
        # ✅ GET BBOX_PROCESSOR REFERENCE FOR SYNCHRONIZATION
        bbox_processor = updated_analysis.get('bbox_processor')
        
        for merge_suggestion in merge_suggestions:
            merge_ids_str = merge_suggestion['merge_ids']
            suggested_name = merge_suggestion['group_name']
            
            # Parse merge_ids (e.g., "H45, V0" → ["H45", "V0"])
            group_ids_to_merge = [gid.strip() for gid in merge_ids_str.split(',')]
            
            # Find groups that exist in our analysis
            groups_to_merge = {}
            for gid in group_ids_to_merge:
                if gid in updated_analysis['analysis']['group_details']:
                    groups_to_merge[gid] = updated_analysis['analysis']['group_details'][gid]
            
            if len(groups_to_merge) < 2:
                print(f"[PREPROCESSOR] ⚠️  Merge {merge_ids_str}: Only {len(groups_to_merge)} groups found, skipping")
                continue
            
            # ✅ FIND LARGEST GROUP (by bbox area)
            largest_group_id = None
            largest_area = 0
            
            for gid, group_info in groups_to_merge.items():
                bboxes = group_info.get('bboxes', [])
                if bboxes:
                    # Calculate total area of all bboxes in this group
                    total_area = 0
                    for bbox in bboxes:
                        bbox_coords = bbox.get('bbox', [0, 0, 0, 0])
                        if len(bbox_coords) >= 4:
                            width = bbox_coords[2] - bbox_coords[0]
                            height = bbox_coords[3] - bbox_coords[1]
                            total_area += width * height
                    
                    if total_area > largest_area:
                        largest_area = total_area
                        largest_group_id = gid
            
            if not largest_group_id:
                print(f"[PREPROCESSOR] ⚠️  Merge {merge_ids_str}: No valid bboxes found, skipping")
                continue
            
            # ✅ CREATE MERGED GROUP
            merged_group = groups_to_merge[largest_group_id].copy()
            
            # Collect all bboxes and calculate union bbox
            all_bboxes = []
            min_x1, min_y1 = float('inf'), float('inf')
            max_x2, max_y2 = float('-inf'), float('-inf')
            
            for gid, group_info in groups_to_merge.items():
                group_bboxes = group_info.get('bboxes', [])
                all_bboxes.extend(group_bboxes)
                
                for bbox in group_bboxes:
                    bbox_coords = bbox.get('bbox', [0, 0, 0, 0])
                    if len(bbox_coords) >= 4:
                        x1, y1, x2, y2 = bbox_coords
                        min_x1 = min(min_x1, x1)
                        min_y1 = min(min_y1, y1)
                        max_x2 = max(max_x2, x2)
                        max_y2 = max(max_y2, y2)
            
            # ✅ OR ALL BOOLEAN FIELDS
            merged_explore = any(groups_to_merge[gid].get('explore', False) for gid in groups_to_merge)
            merged_navigation = any(groups_to_merge[gid].get('navigation', False) for gid in groups_to_merge)
            merged_state_change = any(groups_to_merge[gid].get('state_change', False) for gid in groups_to_merge)
            merged_file_loader = any(groups_to_merge[gid].get('file_loader', False) for gid in groups_to_merge)
            merged_metadata = any(groups_to_merge[gid].get('metadata', False) for gid in groups_to_merge)
            
            # ✅ UPDATE MERGED GROUP
            merged_group.update({
                'group_id': largest_group_id,  # Keep largest group's ID
                'size': len(all_bboxes),
                'bboxes': all_bboxes,
                'groups_name': suggested_name,  # Use Gemini's suggestion
                'explore': merged_explore,
                'navigation': merged_navigation,
                'state_change': merged_state_change,
                'file_loader': merged_file_loader,
                'metadata': merged_metadata,
                'merged_from': list(groups_to_merge.keys()),  # Track original groups
                'merge_reason': merge_suggestion.get('reason', '')
            })
            
            # ✅ UPDATE bbox_processor.final_groups TO MATCH
            if bbox_processor and hasattr(bbox_processor, 'final_groups'):
                # Collect all bboxes from groups to merge
                merged_bboxes = []
                for gid in groups_to_merge:
                    if gid in bbox_processor.final_groups:
                        merged_bboxes.extend(bbox_processor.final_groups[gid])
                
                # Update the largest group with merged bboxes
                if merged_bboxes:  # Only update if we have bboxes
                    bbox_processor.final_groups[largest_group_id] = merged_bboxes
                    print(f"[PREPROCESSOR] 🔗 Updated bbox_processor.final_groups[{largest_group_id}] with {len(merged_bboxes)} bboxes")
                else:
                    print(f"[PREPROCESSOR] ⚠️  No bboxes found to merge for {largest_group_id}")
                
                # Delete the other groups from final_groups
                for gid in groups_to_merge:
                    if gid != largest_group_id and gid in bbox_processor.final_groups:
                        del bbox_processor.final_groups[gid]
                        print(f"[PREPROCESSOR] 🗑️  Deleted group {gid} from bbox_processor.final_groups")
            else:
                print(f"[PREPROCESSOR] ⚠️  bbox_processor or final_groups not available for synchronization")
            
            for gid in groups_to_merge:
                if gid != largest_group_id:
                    del updated_analysis['analysis']['group_details'][gid]
                    groups_merged += 1
            
            merges_processed += 1
            print(f"[PREPROCESSOR] ✅ Merged {merge_ids_str} → {largest_group_id} ('{suggested_name}')")
        
        # ✅ EXTRACT SPLASH SCREEN AND STARTUP INTERACTION DATA
        splash_screen_data = supergroup_data.get('splash_screen', {})
        startup_interaction_data = supergroup_data.get('startup_interaction', {})
        
        # ✅ ADD SPLASH SCREEN DATA TO ANALYSIS
        updated_analysis['analysis']['splash_screen'] = splash_screen_data
        updated_analysis['analysis']['startup_interaction'] = startup_interaction_data
        
        print(f"[PREPROCESSOR] ✅ Updated {groups_updated} groups with enriched supergroup analysis")
        print(f"[PREPROCESSOR]    📊 Groups to explore: {len(explore_groups)} → Final explore=true: {explore_true_count}")
        print(f"[PREPROCESSOR]    🚫 Groups to ignore: {len(groups_to_ignore)} → Final explore=false: {explore_false_count}")
        print(f"[PREPROCESSOR]    🎯 Primary interaction groups: {len(primary_groups)}")
        print(f"[PREPROCESSOR]    🖱️ Splash screen present: {splash_screen_data.get('present', False)}")
        print(f"[PREPROCESSOR]    🔄 Startup interaction required: {startup_interaction_data.get('required', False)}")
        print(f"[PREPROCESSOR]    🔗 Merges processed: {merges_processed}, Groups merged: {groups_merged}")
        
        return updated_analysis
        
    except json.JSONDecodeError as e:
        print(f"[PREPROCESSOR ERROR] Failed to parse supergroup JSON: {e}")
        print(f"[PREPROCESSOR ERROR] Raw response: {supergroup_analysis_text[:200]}...")
        return seraphine_analysis
    except Exception as e:
        print(f"[PREPROCESSOR ERROR] Failed to integrate supergroup analysis: {e}")
        import traceback
        traceback.print_exc()
        return seraphine_analysis


def main():
    """Command-line interface for testing"""
    parser = argparse.ArgumentParser(description='Seraphine Group Visualizer')
    parser.add_argument('--app-name', required=True, help='App name (e.g., notepad)')
    args = parser.parse_args()
    
    app_name = args.app_name
    app_dir = Path("apps") / app_name
    fdom_path = app_dir / "fdom.json"
    screenshot_path = app_dir / "S001.png"
    
    print(f"[PREPROCESSOR] Testing with app: {app_name}")
    print(f"[PREPROCESSOR] fDOM path: {fdom_path}")
    print(f"[PREPROCESSOR] Screenshot path: {screenshot_path}")
    
    if not fdom_path.exists():
        print(f"[PREPROCESSOR ERROR] fDOM file not found: {fdom_path}")
        return
        
    if not screenshot_path.exists():
        print(f"[PREPROCESSOR ERROR] Screenshot not found: {screenshot_path}")
        return
    
    # For testing, we'd need to parse fDOM and create mock groups
    # This is just a placeholder for the command-line interface
    print(f"[PREPROCESSOR] Command-line testing not implemented yet")
    print(f"[PREPROCESSOR] This function will be called from seraphine_processor.py")


if __name__ == "__main__":
    main()
