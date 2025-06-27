import os
import time
import glob
from typing import List, Dict, Any
from PIL import Image
from .helpers import debug_print

class FinalGroupImageGenerator:
    """
    Wrapper class that provides the same interface as the old GroupImageGenerator
    but uses the BBoxProcessor internally for image generation
    """
    
    def __init__(self, output_dir: str = "outputs", enable_timing: bool = True, enable_debug: bool = False, save_mapping: bool = True):
        self.output_dir = output_dir
        self.enable_timing = enable_timing
        self.enable_debug = enable_debug
        self.save_mapping = save_mapping
        os.makedirs(self.output_dir, exist_ok=True)
    
    def create_grouped_images(self, image_path: str, seraphine_analysis: Dict[str, Any], 
                            filename_base: str, return_direct_images: bool = False) -> List[str] | Dict[str, Any]:
        """
        Generate group images using the BBoxProcessor, filtering to only explore=True groups
        
        Args:
            image_path: Path to original image
            seraphine_analysis: Result from FinalSeraphineProcessor.process_detections()
            filename_base: Base filename for outputs
            return_direct_images: If True, returns PIL images directly for Gemini
            
        Returns:
            If return_direct_images=False: List of generated image file paths (original behavior)
            If return_direct_images=True: Dict with 'file_paths' and 'direct_images'
        """
        start_time = time.time()
        
        if self.enable_debug:
            debug_print(f"🖼️  [FINAL GROUP GENERATOR] Generating images (direct_images={return_direct_images})...")
        
        # Get the BBoxProcessor from seraphine result
        bbox_processor = seraphine_analysis.get('bbox_processor')
        if not bbox_processor:
            raise ValueError("No bbox_processor found in seraphine_analysis")
        
        # ✅ FILTER GROUPS TO ONLY EXPLORE=TRUE GROUPS
        original_final_groups = bbox_processor.final_groups.copy()
        group_details = seraphine_analysis.get('analysis', {}).get('group_details', {})
        
        # Filter to only groups where explore=True
        filtered_groups = {}
        explore_count = 0
        total_count = len(original_final_groups)
        
        # ✅ ALWAYS SHOW FILTERING RESULTS (NOT JUST IN DEBUG MODE)
        print(f"[GENERATOR] 🔍 Filtering {total_count} groups based on explore=True...")
        
        for group_id, group_bboxes in original_final_groups.items():
            group_info = group_details.get(group_id, {})
            explore = group_info.get('explore', False)
            
            if explore:
                filtered_groups[group_id] = group_bboxes
                explore_count += 1
                group_name = group_info.get('groups_name', 'unnamed')
                print(f"[GENERATOR] ✅ Including {group_id} ('{group_name}') - explore=True")
            # Only show skipped groups if in debug mode to avoid spam
            elif self.enable_debug:
                group_name = group_info.get('groups_name', 'unnamed')
                print(f"[GENERATOR] ⏭️  Skipping {group_id} ('{group_name}') - explore=False")
        
        print(f"[GENERATOR] 🔍 Final result: {total_count} total groups → {explore_count} explore=True groups")
        
        # Temporarily replace final_groups with filtered version
        bbox_processor.final_groups = filtered_groups
        
        # Load original image into processor
        try:
            bbox_processor.original_image = Image.open(image_path)
            if self.enable_debug:
                debug_print(f"📷 Loaded original image: {bbox_processor.original_image.size}")
        except Exception as e:
            debug_print(f"❌ Error loading original image: {e}")
            bbox_processor.original_image = None
        
        # Generate images
        os.makedirs(self.output_dir, exist_ok=True)
        
        try:
            if return_direct_images:
                # Generate with direct image return
                result = bbox_processor.generate_images(self.output_dir, return_images=True)
                
                # Create file path list for compatibility
                generated_files = result['saved_paths']
                
                # Save mapping only if enabled
                if self.save_mapping:
                    bbox_processor.save_mapping(self.output_dir)
                
                elapsed = time.time() - start_time
                if self.enable_timing:
                    debug_print(f"⏱️  Image generation (with direct return, {explore_count} groups): {elapsed:.3f}s")
                
                return {
                    'file_paths': generated_files,
                    'direct_images': [(img, filename) for img, filename, _ in result['generated_images']],
                    'image_count': result['image_count'],
                    'filtered_group_count': explore_count,
                    'total_group_count': total_count
                }
            else:
                # Original behavior - just save files
                bbox_processor.generate_images(self.output_dir)
                if self.save_mapping:
                    bbox_processor.save_mapping(self.output_dir)
                
                # Return list of generated image paths (compatible with old interface)
                generated_files = []
                pattern = os.path.join(self.output_dir, "combined_groups_*.png")
                generated_files.extend(glob.glob(pattern))
                
                # Add annotated image if it exists
                annotated_path = os.path.join(self.output_dir, "annotated_original_image.png")
                if os.path.exists(annotated_path):
                    generated_files.append(annotated_path)
                
                elapsed = time.time() - start_time
                if self.enable_timing:
                    debug_print(f"⏱️  Image generation ({explore_count} groups): {elapsed:.3f}s")
                
                return generated_files
        
        finally:
            # ✅ RESTORE ORIGINAL GROUPS (important for other parts of pipeline)
            bbox_processor.final_groups = original_final_groups
