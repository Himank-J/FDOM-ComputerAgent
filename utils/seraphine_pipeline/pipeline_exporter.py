"""
Pipeline Export Utility
Handles JSON export and data structure creation for the enhanced pipeline
"""
import os
import json
from datetime import datetime
from .helpers import debug_print
from typing import Dict, List

def create_enhanced_seraphine_structure(seraphine_analysis: Dict, merged_detections: List[Dict]) -> Dict:
    """Create enhanced structure with proper ID mapping for fDOM compatibility"""
    
    bbox_processor = seraphine_analysis.get('bbox_processor')
    group_details = seraphine_analysis.get('analysis', {}).get('group_details', {})
    
    if not bbox_processor or not hasattr(bbox_processor, 'final_groups'):
        return {}
    
    seraphine_structure = {}
    
    for group_id, bboxes in bbox_processor.final_groups.items():
        # Get group-level information (including explore flag)
        group_info = group_details.get(group_id, {})
        group_explore = group_info.get('explore', True)  # Get explore from group level
        group_name = group_info.get('groups_name', 'Unknown')
        
        group_elements = {}
        
        for i, bbox in enumerate(bboxes):
            element_id = f"{group_id}_{i+1}"
            
            # Find matching detection for proper ID mapping
            matching_detection = None
            for detection in merged_detections:
                if detection.get('merged_id') == bbox.merged_id:
                    matching_detection = detection
                    break
            
            element_data = {
                'bbox': [bbox.x1, bbox.y1, bbox.x2, bbox.y2],
                'g_icon_name': getattr(bbox, 'g_icon_name', 'Unknown'),
                'g_brief': getattr(bbox, 'g_brief', 'No description'),
                'g_enabled': getattr(bbox, 'g_enabled', True),
                'g_interactive': getattr(bbox, 'g_interactive', True),
                'g_type': getattr(bbox, 'g_type', 'icon'),
                'explore': group_explore,  # NEW: Pass group explore down to element
                'm_id': matching_detection.get('merged_id') if matching_detection else None,
                'y_id': matching_detection.get('id') if matching_detection and matching_detection.get('source') == 'yolo' else None,
                'o_id': matching_detection.get('id') if matching_detection and matching_detection.get('source') == 'ocr_det' else None,
                'type': matching_detection.get('type', 'icon') if matching_detection else 'icon',
                'source': matching_detection.get('source', 'unknown') if matching_detection else 'unknown'
            }
            
            group_elements[element_id] = element_data
        
        if group_elements:  # Only add non-empty groups
            seraphine_structure[group_id] = group_elements
    
    return seraphine_structure

def save_enhanced_pipeline_json(image_path, detection_results, seraphine_analysis, gemini_results, config):
    """
    Save ENHANCED pipeline JSON with Gemini integration
    """
    if not config.get("save_json", False):
        debug_print("\n⏭️  JSON saving disabled in config")
        return None
    
    debug_print("\n💾 Saving Enhanced Pipeline JSON (with Gemini)")
    debug_print("=" * 70)
    
    # Create enhanced seraphine structure with PROPER ID TRACKING!
    enhanced_seraphine_groups = create_enhanced_seraphine_structure(
        seraphine_analysis, 
        detection_results['merged_detections']  # ✅ PASS ORIGINAL MERGED DETECTIONS!
    )
    
    # Choose the right field name based on Gemini success
    seraphine_field_name = "seraphine_gemini_groups" if gemini_results else "seraphine_groups"
    
    # Rest of save_pipeline_json logic but with enhanced structure
    output_dir = config.get("output_dir", "outputs")
    current_time = datetime.now().strftime("%d-%m")
    filename_base = os.path.splitext(os.path.basename(image_path))[0]
    
    analysis = seraphine_analysis['analysis']
    
    pipeline_results = {
        'pipeline_version': 'v1.2_enhanced_with_gemini',
        'timestamp': datetime.now().isoformat(),
        'image_info': {
            'filename': os.path.basename(image_path),
            'path': image_path
        },
        'detection_summary': {
            'yolo_count': len(detection_results['yolo_detections']),
            'ocr_count': len(detection_results['ocr_detections']),
            'merged_count': len(detection_results['merged_detections']),
            'total_input': len(detection_results['yolo_detections']) + len(detection_results['ocr_detections']),
            'merge_efficiency': f"{len(detection_results['yolo_detections']) + len(detection_results['ocr_detections']) - len(detection_results['merged_detections'])} removed"
        },
        'seraphine_summary': {
            'total_groups': analysis['total_groups'],
            'horizontal_groups': analysis['horizontal_groups'],
            'vertical_groups': analysis['vertical_groups'],
            'long_box_groups': analysis['long_box_groups'],
            'grouping_efficiency': analysis['grouping_efficiency']
        },
        'gemini_summary': {
            'enabled': bool(gemini_results),
            'total_icons_analyzed': gemini_results.get('total_icons_found', 0) if gemini_results else 0,
            'successful_analyses': gemini_results.get('successful_analyses', 0) if gemini_results else 0,
            'analysis_time': gemini_results.get('analysis_duration_seconds', 0) if gemini_results else 0
        },
        'timing_breakdown': {
            **detection_results['timing'],
            'seraphine_time': seraphine_analysis.get('seraphine_timing', 0),
            'gemini_time': gemini_results.get('analysis_duration_seconds', 0) if gemini_results else 0
        },
        'detections': {
            'yolo_detections': detection_results['yolo_detections'],
            'ocr_detections': detection_results['ocr_detections'], 
            'merged_detections': detection_results['merged_detections']
        },
        seraphine_field_name: enhanced_seraphine_groups  # DYNAMIC FIELD NAME!
    }
    
    # Add Gemini analysis metadata only if successful (avoid duplication)
    if gemini_results:
        pipeline_results['gemini_analysis_metadata'] = {
            'total_images_analyzed': gemini_results.get('total_images_analyzed', 0),
            'analysis_mode': gemini_results.get('analysis_mode', 'unknown'),
            'timestamp': gemini_results.get('analysis_timestamp')
        }
    
    # Save JSON file
    json_filename = f"{filename_base}_enhanced_v1_{current_time}.json"
    json_path = os.path.join(output_dir, json_filename)
    
    os.makedirs(output_dir, exist_ok=True)
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(pipeline_results, f, indent=2, ensure_ascii=False)
    
    debug_print(f"✅ Enhanced Pipeline JSON saved: {json_filename}")
    debug_print(f"   📊 Complete pipeline with Gemini integration")
    debug_print(f"   🔗 Perfect ID mapping: Y/O → M → Seraphine Groups → Gemini Analysis")
    debug_print(f"   🎯 Field name: '{seraphine_field_name}' (dynamic based on Gemini success)")
    
    return json_path
