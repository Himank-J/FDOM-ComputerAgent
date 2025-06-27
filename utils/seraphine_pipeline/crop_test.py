import cv2
import numpy as np
import time
from typing import Tuple, List
import concurrent.futures
import os
import glob
from .helpers import debug_print


class UltraFastTemplateMatcher:
    """
    Ultra-optimized template matching for finding small crop images in larger images.
    Uses coarse-to-fine search and grayscale processing for maximum speed.
    """
    
    def __init__(self, save_results: bool = True):
        self.cached_templates = {}
        self.cached_grayscale_templates = {}
        self.cached_small_templates = {}
        self.save_results = save_results  # Global toggle for saving files
        
        # Beautiful color scheme inspired by beautiful_visualizer.py
        self.colors = {
            'match': (46, 125, 50),      # Green - Successful match
            'no_match': (244, 67, 54),   # Red - No match found
            'border': (255, 255, 255),   # White - Border
            'text_bg': (33, 33, 33),     # Dark gray - Text background
            'text': (255, 255, 255)      # White - Text
        }
        
    def preprocess_template(self, template_path: str) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Preprocess and cache multiple versions of template for ultra-fast matching.
        """
        if template_path in self.cached_templates:
            return (self.cached_templates[template_path], 
                   self.cached_grayscale_templates[template_path],
                   self.cached_small_templates[template_path])
        
        template = cv2.imread(template_path, cv2.IMREAD_COLOR)
        if template is None:
            raise ValueError(f"Could not load template image: {template_path}")
        
        # Create grayscale version (much faster)
        gray_template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        
        # Create small version for initial coarse search - handle tiny images
        h, w = gray_template.shape
        if h >= 4 and w >= 4:  # Only resize if template is big enough
            small_template = cv2.resize(gray_template, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
        else:
            # For tiny templates, use original size
            small_template = gray_template.copy()
        
        # Cache all versions
        self.cached_templates[template_path] = template
        self.cached_grayscale_templates[template_path] = gray_template
        self.cached_small_templates[template_path] = small_template
        
        return template, gray_template, small_template
    
    def ultra_fast_match(self, 
                        screenshot: np.ndarray, 
                        template_path: str,
                        threshold: float = 0.99) -> Tuple[bool, float, Tuple[int, int]]:
        """
        Ultra-fast single template matching with coarse-to-fine optimization.
        """
        # Get preprocessed templates
        _, gray_template, small_template = self.preprocess_template(template_path)
        
        # Convert screenshot to grayscale once
        gray_screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
        
        # Method 1: Coarse search at half resolution (4x faster)
        small_screenshot = cv2.resize(gray_screenshot, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
        
        # Quick coarse match
        res_small = cv2.matchTemplate(small_screenshot, small_template, cv2.TM_CCOEFF_NORMED)
        _, max_val_small, _, max_loc_small = cv2.minMaxLoc(res_small)
        
        if max_val_small < threshold * 0.99:  # Lower threshold for coarse search
            return False, max_val_small, (0, 0)
        
        # Method 2: Refined search in ROI around coarse match
        scale = 2  # We downscaled by 0.5
        roi_size = max(gray_template.shape) * 2  # Search area around coarse match
        
        center_x = max_loc_small[0] * scale
        center_y = max_loc_small[1] * scale
        
        x1 = max(0, center_x - roi_size // 2)
        y1 = max(0, center_y - roi_size // 2)
        x2 = min(gray_screenshot.shape[1], center_x + roi_size // 2)
        y2 = min(gray_screenshot.shape[0], center_y + roi_size // 2)
        
        roi_screenshot = gray_screenshot[y1:y2, x1:x2]
        
        if roi_screenshot.size == 0:
            return False, 0.0, (0, 0)
        
        # Fine match in ROI
        res = cv2.matchTemplate(roi_screenshot, gray_template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        
        found = max_val >= threshold
        if found:
            # Convert ROI coordinates back to full image coordinates
            abs_x = max_loc[0] + x1
            abs_y = max_loc[1] + y1
            return found, max_val, (abs_x, abs_y)
        
        return found, max_val, max_loc
    
    def parallel_batch_match(self, 
                           screenshot: np.ndarray, 
                           template_paths: List[str],
                           threshold: float = 0.99,
                           max_workers: int = 8) -> List[Tuple[str, bool, float, Tuple[int, int]]]:
        """
        Process multiple templates in parallel for maximum speed.
        """
        def match_single(template_path):
            found, confidence, location = self.ultra_fast_match(screenshot, template_path, threshold)
            return template_path, found, confidence, location
        
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_template = {executor.submit(match_single, path): path for path in template_paths}
            
            for future in concurrent.futures.as_completed(future_to_template):
                results.append(future.result())
        
        return results

    def create_beautiful_visualization(self, 
                                     screenshot: np.ndarray, 
                                     template_path: str, 
                                     found: bool,
                                     confidence: float,
                                     location: Tuple[int, int], 
                                     output_path: str = "utils/ultra_fast_result.jpg"):
        """
        Create beautiful box visualization - simple and clean
        """
        if not self.save_results:
            return
            
        template = cv2.imread(template_path)
        if template is None:
            debug_print(f"Could not load template for visualization: {template_path}")
            return
        
        img_cv = screenshot.copy()
        
        if found:
            # Get template dimensions
            template_h, template_w = template.shape[:2]
            x1, y1 = location
            x2, y2 = x1 + template_w, y1 + template_h
            
            # Beautiful double border box only
            main_color = self.colors['match']  # Green
            border_color = self.colors['border']  # White
            
            # Draw beautiful bounding box with double border effect
            cv2.rectangle(img_cv, (x1-1, y1-1), (x2+1, y2+1), border_color, 2)  # White outer border
            cv2.rectangle(img_cv, (x1, y1), (x2, y2), main_color, 2)            # Green inner border
            
            # # Add subtle corner markers
            # corner_size = 2
            # cv2.line(img_cv, (x1, y1), (x1 + corner_size, y1), main_color, 2)
            # cv2.line(img_cv, (x1, y1), (x1, y1 + corner_size), main_color, 2)
            # cv2.line(img_cv, (x2, y2), (x2 - corner_size, y2), main_color, 2)
            # cv2.line(img_cv, (x2, y2), (x2, y2 - corner_size), main_color, 2)
        
        # Save with high quality
        cv2.imwrite(output_path, img_cv, [cv2.IMWRITE_JPEG_QUALITY, 95])
        debug_print(f"🎨 Beautiful box saved: {output_path}")


if __name__ == "__main__":
    # Ultra-fast template matching example with beautiful visualization
    debug_print("🚀 Ultra-Fast Template Matching with Beautiful Visualization")
    debug_print("=" * 60)
    
    # Load images
    screenshot = cv2.imread("word.png")
    template_path = "utils\crops\crop_004_icon_yolo.png"
    
    if screenshot is None:
        debug_print("❌ Error: Could not load word.png")
        exit(1)
    
    # Initialize matcher with save toggle (set to True for saving, False to disable)
    SAVE_RESULTS = True  # 🎛️ Global toggle for saving files
    matcher = UltraFastTemplateMatcher(save_results=SAVE_RESULTS)
    
    # Single ultra-fast match
    start_time = time.perf_counter()
    found, confidence, location = matcher.ultra_fast_match(screenshot, template_path, threshold=0.99)
    end_time = time.perf_counter()
    
    match_time = (end_time - start_time) * 1000
    
    debug_print(f"📊 Single Match Results:")
    debug_print(f"   ⏱️  Time: {match_time:.2f}ms")
    debug_print(f"   ✅ Found: {found}")
    debug_print(f"   🎯 Confidence: {confidence:.3f}")
    debug_print(f"   📍 Location: {location}")
    
    # Create beautiful visualization
    if SAVE_RESULTS:
        matcher.create_beautiful_visualization(
            screenshot, template_path, found, confidence, location
        )
    else:
        debug_print("💾 File saving disabled (SAVE_RESULTS = False)")
    
    # Batch processing example (100 icons)
    debug_print(f"\n🔄 Batch Processing (100 icons):")
    template_paths = [template_path] * 100
    
    start_time = time.perf_counter()
    batch_results = matcher.parallel_batch_match(screenshot, template_paths, max_workers=8)
    end_time = time.perf_counter()
    
    batch_time = (end_time - start_time) * 1000
    matches_found = sum(1 for _, found, _, _ in batch_results if found)
    throughput = 100 / (batch_time / 1000)
    
    debug_print(f"   ⏱️  Total time: {batch_time:.2f}ms")
    debug_print(f"   ✅ Matches found: {matches_found}/100")
    debug_print(f"   🚄 Throughput: {throughput:.1f} matches/second")
    debug_print(f"   📊 Average per match: {batch_time/100:.2f}ms")
    
    debug_print(f"\n✨ Ultra-fast template matching complete!")
    if SAVE_RESULTS:
        debug_print(f"📁 Results saved to: utils/ultra_fast_result.jpg")

    # NEW: Ultra-fast batch crop detection 
    debug_print(f"\n" + "=" * 60)
    debug_print("🔍 ULTRA-FAST BATCH CROP DETECTION")
    debug_print("=" * 60)
    
    # Get all crop files
    crops_dir = "utils/crops"
    crop_files = glob.glob(os.path.join(crops_dir, "crop_*.png"))
    crop_files.sort()
    
    total_crops = len(crop_files)
    debug_print(f"📁 Found {total_crops} crops in {crops_dir}/")
    
    if total_crops > 0:
        # PURE COMPUTATION TIMING - No I/O or visualization
        debug_print(f"🚀 Starting pure computation timing...")
        start_pure = time.perf_counter()
        
        # Use existing parallel batch processing for maximum speed
        batch_results = matcher.parallel_batch_match(
            screenshot, crop_files, threshold=0.7, max_workers=8
        )
        
        end_pure = time.perf_counter()
        pure_computation_time = (end_pure - start_pure) * 1000
        
        # Count successful matches
        successful_matches = sum(1 for _, found, _, _ in batch_results if found)
        
        # Pure computation stats
        debug_print(f"\n⚡ PURE COMPUTATION PERFORMANCE:")
        debug_print(f"   ⏱️  Pure computation: {pure_computation_time:.1f}ms ({pure_computation_time/1000:.2f}s)")
        debug_print(f"   🚄 Pure throughput: {total_crops/(pure_computation_time/1000):.1f} crops/second")
        debug_print(f"   📊 Average per crop: {pure_computation_time/total_crops:.2f}ms")
        debug_print(f"   ✅ Found: {successful_matches}/{total_crops} ({(successful_matches/total_crops)*100:.1f}%)")
        
        # Now do visualization separately (if needed)
        if successful_matches > 0:
            debug_print(f"\n🎨 Creating visualization overlay...")
            start_viz = time.perf_counter()
            
            final_overlay = screenshot.copy()
            
            for template_path, found, confidence, location in batch_results:
                if found:
                    # Extract crop ID from filename
                    crop_name = os.path.basename(template_path)
                    crop_id = "?"
                    try:
                        parts = crop_name.replace('.png', '').split('_')
                        if len(parts) >= 2:
                            crop_id = parts[1]
                    except:
                        pass
                    
                    # Get template size from cache (fast!)
                    if template_path in matcher.cached_templates:
                        template = matcher.cached_templates[template_path]
                        template_h, template_w = template.shape[:2]
                        
                        x1, y1 = location
                        x2, y2 = x1 + template_w, y1 + template_h
                        
                        # Same beautiful box style
                        main_color = matcher.colors['match']
                        border_color = matcher.colors['border']
                        
                        # Beautiful double border box
                        cv2.rectangle(final_overlay, (x1-2, y1-2), (x2+2, y2+2), border_color, 4)
                        cv2.rectangle(final_overlay, (x1, y1), (x2, y2), main_color, 2)
                        
                        # Corner markers
                        corner_size = 15
                        cv2.line(final_overlay, (x1, y1), (x1 + corner_size, y1), main_color, 4)
                        cv2.line(final_overlay, (x1, y1), (x1, y1 + corner_size), main_color, 4)
                        cv2.line(final_overlay, (x2, y2), (x2 - corner_size, y2), main_color, 4)
                        cv2.line(final_overlay, (x2, y2), (x2, y2 - corner_size), main_color, 4)
                        
                        # Add crop ID label
                        label_x = x1 + 2
                        label_y = y1 - 5
                        if label_y < 15:
                            label_y = y1 + 15
                        
                        cv2.putText(final_overlay, crop_id, (label_x, label_y), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, main_color, 1, cv2.LINE_AA)
            
            end_viz = time.perf_counter()
            viz_time = (end_viz - start_viz) * 1000
            
            # Save overlay
            overlay_path = "utils/all_crops_detected.jpg"
            cv2.imwrite(overlay_path, final_overlay, [cv2.IMWRITE_JPEG_QUALITY, 95])
            
            debug_print(f"   🎨 Visualization time: {viz_time:.1f}ms")
            debug_print(f"   💾 Overlay saved: {overlay_path}")
        
        # Total timing breakdown
        total_time = pure_computation_time + (viz_time if successful_matches > 0 else 0)
        debug_print(f"\n📊 TIMING BREAKDOWN:")
        debug_print(f"   ⚡ Pure computation: {pure_computation_time:.1f}ms ({pure_computation_time/total_time*100:.1f}%)")
        if successful_matches > 0:
            debug_print(f"   🎨 Visualization: {viz_time:.1f}ms ({viz_time/total_time*100:.1f}%)")
        debug_print(f"   📈 Total: {total_time:.1f}ms")
        
    else:
        debug_print("❌ No crop files found in utils/crops/")
