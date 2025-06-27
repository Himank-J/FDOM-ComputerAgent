"""
Parallel processor for running YOLO and OCR detection simultaneously
No imports from original files allowed.
"""
import time
import threading
import json
import os
from typing import List, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from .helpers import debug_print

from .yolo_detector import YOLODetector, YOLOConfig
from .ocr_detector import OCRDetector, OCRDetConfig
from .bbox_merger import BBoxMerger
try:
    from .yolo_visualizer import DetectionVisualizer
except ImportError:
    DetectionVisualizer = None  # We'll handle this in __init__

class ParallelProcessor:
    """
    Coordinates parallel execution of YOLO and OCR detection,
    then merges the results according to specified rules.
    """
    
    def __init__(self, 
                 yolo_config: YOLOConfig = None,
                 ocr_config: OCRDetConfig = None,
                 merger_iou_threshold: float = 0.1,
                 enable_timing: bool = True,
                 create_visualizations: bool = True,
                 save_intermediate_results: bool = True):
        """
        Initialize parallel processor
        
        Args:
            yolo_config: Configuration for YOLO detector
            ocr_config: Configuration for OCR detector
            merger_iou_threshold: IoU threshold for bbox merging
            enable_timing: Whether to print timing information
            create_visualizations: Whether to create visualization images
            save_intermediate_results: Whether to save intermediate JSON files
        """
        self.yolo_config = yolo_config or YOLOConfig()
        self.ocr_config = ocr_config or OCRDetConfig()
        self.enable_timing = enable_timing
        self.create_visualizations = create_visualizations
        self.save_intermediate_results = save_intermediate_results
        
        # Initialize detectors
        self.yolo_detector = YOLODetector(self.yolo_config)
        self.ocr_detector = OCRDetector(self.ocr_config)
        self.merger = BBoxMerger(iou_threshold=merger_iou_threshold, enable_timing=enable_timing)
        
        # Initialize visualizer if needed
        if self.create_visualizations and DetectionVisualizer is not None:
            self.visualizer = DetectionVisualizer()
        elif self.create_visualizations:
            debug_print("⚠️  DetectionVisualizer not available, skipping visualizations")
            self.create_visualizations = False
    
    def process_image(self, image_path: str, output_dir: str = "outputs") -> Dict[str, Any]:
        """
        Process image with parallel YOLO and OCR detection, then merge results
        
        Args:
            image_path: Path to input image
            output_dir: Directory to save results
            
        Returns:
            Dictionary containing all results and timing information
        """
        total_start = time.time()
        
        if self.enable_timing:
            debug_print(f"\n🚀 Starting parallel detection pipeline...")
            debug_print(f"📁 Image: {image_path}")
            debug_print(f"📁 Output directory: {output_dir}")
            debug_print("=" * 80)
        
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)
        
        # Prepare result containers
        results = {
            'image_path': image_path,
            'yolo_detections': [],
            'ocr_detections': [],
            'merged_detections': [],
            'timing': {},
            'merge_stats': {},
            'visualization_paths': {}
        }
        
        # Run YOLO and OCR detection in parallel
        parallel_start = time.time()
        
        def run_yolo():
            if self.enable_timing:
                debug_print(f"🎯 Thread: Starting YOLO detection...")
            return self.yolo_detector.detect(image_path)
        
        def run_ocr():
            if self.enable_timing:
                debug_print(f"📝 Thread: Starting OCR detection...")
            return self.ocr_detector.detect(image_path)
        
        # Execute in parallel using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as executor:
            # Submit both tasks
            yolo_future = executor.submit(run_yolo)
            ocr_future = executor.submit(run_ocr)
            
            # Wait for both to complete
            yolo_detections = yolo_future.result()
            ocr_detections = ocr_future.result()
        
        # 🎯 FIX: Assign intelligent IDs BEFORE merging!
        yolo_detections, ocr_detections = self.assign_intelligent_ids(yolo_detections, ocr_detections)
        
        parallel_time = time.time() - parallel_start
        
        if self.enable_timing:
            debug_print(f"\n⚡ Parallel detection completed in {parallel_time:.3f}s")
            debug_print(f"  YOLO found: {len(yolo_detections)} detections")
            debug_print(f"  OCR found: {len(ocr_detections)} detections")
        
        # Store individual results
        results['yolo_detections'] = yolo_detections
        results['ocr_detections'] = ocr_detections
        
        # Merge detections
        merge_start = time.time()
        merged_detections, merge_stats = self.merger.merge_detections(yolo_detections, ocr_detections)
        merge_time = time.time() - merge_start
        
        results['merged_detections'] = merged_detections
        results['merge_stats'] = merge_stats
        
        # Create visualizations if enabled
        viz_time = 0
        if self.create_visualizations:
            viz_start = time.time()
            if self.enable_timing:
                debug_print(f"\n🎨 Creating beautiful visualizations...")
            
            visualization_paths = self.visualizer.create_all_visualizations(image_path, results)
            results['visualization_paths'] = visualization_paths
            viz_time = time.time() - viz_start
            
            if self.enable_timing:
                debug_print(f"  Visualization creation: {viz_time:.3f}s")
        
        # Compile timing information
        total_time = time.time() - total_start
        results['timing'] = {
            'total_time': total_time,
            'parallel_detection_time': parallel_time,
            'merge_time': merge_time,
            'visualization_time': viz_time,
            'yolo_count': len(yolo_detections),
            'ocr_count': len(ocr_detections),
            'merged_count': len(merged_detections)
        }
        
        # Save results to files
        self._save_results(results, output_dir, image_path)
        
        if self.enable_timing:
            debug_print(f"\n🎉 Pipeline completed successfully!")
            debug_print(f"  Total time: {total_time:.3f}s")
            debug_print(f"  Parallel detection: {parallel_time:.3f}s ({parallel_time/total_time*100:.1f}%)")
            debug_print(f"  Merging: {merge_time:.3f}s ({merge_time/total_time*100:.1f}%)")
            if viz_time > 0:
                debug_print(f"  Visualizations: {viz_time:.3f}s ({viz_time/total_time*100:.1f}%)")
            debug_print(f"  Final result: {len(merged_detections)} detections")
            debug_print("=" * 80)
        
        return results
    
    def _save_results(self, results: Dict[str, Any], output_dir: str, image_path: str):
        """Save all results to JSON files"""
        if self.enable_timing:
            debug_print(f"\n💾 Saving results to {output_dir}...")

        if not self.save_intermediate_results:
            return
        
        # Extract base name for file naming
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        
        # Save YOLO results
        yolo_file = os.path.join(output_dir, f"{base_name}_yolo_result.json")
        with open(yolo_file, 'w') as f:
            json.dump({
                'image_path': image_path,
                'detections': results['yolo_detections'],
                'count': len(results['yolo_detections']),
                'source': 'yolo'
            }, f, indent=2)
        
        # Save OCR results
        ocr_file = os.path.join(output_dir, f"{base_name}_ocr_det_result.json")
        with open(ocr_file, 'w') as f:
            json.dump({
                'image_path': image_path,
                'detections': results['ocr_detections'],
                'count': len(results['ocr_detections']),
                'source': 'ocr_det'
            }, f, indent=2)
        
        # Save merged results
        merged_file = os.path.join(output_dir, f"{base_name}_merged_result.json")
        with open(merged_file, 'w') as f:
            json.dump({
                'image_path': image_path,
                'detections': results['merged_detections'],
                'count': len(results['merged_detections']),
                'source': 'merged',
                'merge_stats': results['merge_stats'],
                'timing': results['timing']
            }, f, indent=2)
        
        # Save complete results
        complete_file = os.path.join(output_dir, f"{base_name}_complete_results.json")
        with open(complete_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        if self.enable_timing:
            debug_print(f"  ✅ YOLO results: {yolo_file}")
            debug_print(f"  ✅ OCR results: {ocr_file}")
            debug_print(f"  ✅ Merged results: {merged_file}")
            debug_print(f"  ✅ Complete results: {complete_file}")

    def assign_intelligent_ids(self, yolo_detections, ocr_detections):
        """Assign simple, clean IDs for pipeline tracking"""
        debug_print("🔖 Assigning simple, clean IDs for pipeline tracking...")
        
        # Assign YOLO IDs
        for i, detection in enumerate(yolo_detections):
            detection['y_id'] = f"Y{i+1:03d}"
        
        # Assign OCR IDs  
        for i, detection in enumerate(ocr_detections):
            detection['o_id'] = f"O{i+1:03d}"
        
        debug_print(f"  ✅ Assigned {len(yolo_detections)} YOLO IDs (Y001-Y{len(yolo_detections):03d})")
        debug_print(f"  ✅ Assigned {len(ocr_detections)} OCR IDs (O001-O{len(ocr_detections):03d})")
        
        return yolo_detections, ocr_detections