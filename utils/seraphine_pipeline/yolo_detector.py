"""
Clean YOLO detection utility - extracted from yolo_onnx.py
No imports from original files allowed.
"""
import time
import math
import numpy as np
import cv2
import onnxruntime as ort
from PIL import Image
from dataclasses import dataclass
from typing import Tuple, List, Dict, Any
import argparse
import json
import os
import sys
from .helpers import debug_print

@dataclass
class YOLOConfig:
    """Configuration for YOLO inference pipeline"""
    conf_threshold: float = 0.1
    iou_threshold: float = 0.1
    max_resolution: Tuple[int, int] = (2560, 2560)
    enable_timing: bool = True
    enable_debug: bool = False
    model_path: str = "models/model_dynamic.onnx"
    # 🚀 Simple content filtering
    enable_content_filtering: bool = True
    min_content_pixels: int = 5  # Minimum content pixels to keep box

def filter_sparse_boxes_ultra_fast(image_np, detections, min_content_pixels=50):
    """
    Ultra-fast sparse content filtering using simple pixel counting
    
    Strategy: Count pixels that deviate significantly from local mean
    Args:
        image_np: numpy array image (BGR or RGB format)
        detections: list of detection dictionaries
        min_content_pixels: minimum content pixels to keep box
    """
    if len(detections) == 0:
        return detections, 0
    
    filtered_detections = []
    filtered_count = 0
    
    for detection in detections:
        x1, y1, x2, y2 = map(int, detection['bbox'])
        
        # Quick bounds check
        h, w = image_np.shape[:2]
        if x1 >= w or y1 >= h or x2 <= x1 or y2 <= y1:
            filtered_count += 1
            continue
            
        # Clamp coordinates
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        
        # Extract box region
        box_crop = image_np[y1:y2, x1:x2]
        if box_crop.size == 0:
            filtered_count += 1
            continue
        
        # Convert to grayscale if needed
        if len(box_crop.shape) == 3:
            # Fast grayscale conversion
            gray = np.dot(box_crop[...,:3], [0.299, 0.587, 0.114]).astype(np.uint8)
        else:
            gray = box_crop
        
        # Ultra-fast content detection
        mean_val = np.mean(gray)
        
        # Count pixels that deviate from mean (content pixels)
        content_pixels = np.sum(np.abs(gray.astype(np.float32) - mean_val) > 15)
        
        # Keep box if it has enough content pixels
        if content_pixels >= min_content_pixels:
            filtered_detections.append(detection)
        else:
            filtered_count += 1
    
    return filtered_detections, filtered_count

class CPUModelCache:
    """Singleton cache for ONNX models with CPU optimization"""
    _instance = None
    _session = None
    _model_path = None
    _input_name = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def get_session(self, model_path):
        if self._session is None or self._model_path != model_path:
            if self._session is None:
                debug_print("  Loading CPU-optimized YOLO model...")
            else:
                debug_print("  Reloading YOLO model...")
            load_start = time.time()
            
            so = ort.SessionOptions()
            so.log_severity_level = 3
            so.enable_mem_pattern = True
            so.enable_mem_reuse = True
            so.enable_cpu_mem_arena = True
            so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            
            providers = [("CPUExecutionProvider", {
                "enable_cpu_mem_arena": True,
                "arena_extend_strategy": "kSameAsRequested",
                "initial_chunk_size_bytes": 1024 * 1024 * 32,
                "max_mem": 1024 * 1024 * 512
            })]
            
            self._session = ort.InferenceSession(model_path, sess_options=so, providers=providers)
            self._model_path = model_path
            self._input_name = self._session.get_inputs()[0].name
            
            load_time = time.time() - load_start
            debug_print(f"  YOLO model loading: {load_time:.3f}s")
        
        return self._session, self._input_name
    
    def reset(self):
        """Reset the model cache to force reload"""
        self._session = None
        self._model_path = None
        self._input_name = None
        debug_print("  🔄 YOLO model cache cleared")

# Global instance
model_cache = CPUModelCache()

def round_to_multiple(x, base):
    return int(base * math.ceil(x / base))

def load_and_prepare_image_ultra_fast(img_path, max_resolution, enable_timing=True):
    """🚀 ULTRA-FAST: Optimized preprocessing pipeline with minimal memory allocations"""
    start_time = time.time()
    if enable_timing:
        debug_print(f"📸 YOLO: Loading and preparing image: {img_path}")
    
    load_start = time.time()
    # Load directly as BGR (OpenCV native format)
    img_bgr = cv2.imread(img_path, cv2.IMREAD_COLOR)
    load_time = time.time() - load_start
    
    orig_h, orig_w = img_bgr.shape[:2]
    target_w = min(round_to_multiple(orig_w, 32), max_resolution[0])
    target_h = min(round_to_multiple(orig_h, 32), max_resolution[1])
    
    resize_start = time.time()
    # 🚀 OPTIMIZATION 1: Resize in BGR first (avoid extra conversion)
    # 🚀 OPTIMIZATION 2: Use INTER_AREA for downscaling (faster + better quality)
    if target_w < orig_w or target_h < orig_h:
        interpolation = cv2.INTER_AREA  # Faster for downscaling
    else:
        interpolation = cv2.INTER_LINEAR  # Better for upscaling
    
    img_resized_bgr = cv2.resize(img_bgr, (target_w, target_h), interpolation=interpolation)
    resize_time = time.time() - resize_start
    
    convert_start = time.time()
    # 🚀 OPTIMIZATION 3: Direct BGR->RGB conversion + normalization in one step
    img_rgb = cv2.cvtColor(img_resized_bgr, cv2.COLOR_BGR2RGB)
    
    # 🚀 OPTIMIZATION 4: In-place operations with copy=False + faster multiply
    img_np = img_rgb.astype(np.float32, copy=False) * np.float32(1.0/255.0)  # Faster than division
    
    # 🚀 OPTIMIZATION 5: Direct transpose (no intermediate variable)
    input_tensor = img_np.transpose(2, 0, 1)[None, ...]
    convert_time = time.time() - convert_start
    
    scaling_factors = (orig_w / target_w, orig_h / target_h)
    
    if enable_timing:
        total_time = time.time() - start_time
        debug_print(f"  YOLO image preparation: {total_time:.3f}s")
        debug_print(f"   - Loading: {load_time:.3f}s")
        debug_print(f"   - Resizing ({orig_w}x{orig_h} → {target_w}x{target_h}): {resize_time:.3f}s")
        debug_print(f"   - Array conversion: {convert_time:.3f}s")
    
    # Return original BGR for content filtering (no extra conversion needed)
    return input_tensor, (target_w, target_h), (orig_w, orig_h), scaling_factors, img_bgr

def run_inference_optimized(model_path, input_tensor, enable_timing=True):
    start_time = time.time()
    if enable_timing:
        debug_print(f"🧠 YOLO: Running CPU-optimized inference...")
    
    cache_start = time.time()
    session, input_name = model_cache.get_session(model_path)
    cache_time = time.time() - cache_start
    
    prep_start = time.time()
    input_dict = {input_name: input_tensor}
    prep_time = time.time() - prep_start
    
    inference_start = time.time()
    output = session.run(None, input_dict)
    inference_time = time.time() - inference_start
    
    if enable_timing:
        total_time = time.time() - start_time
        debug_print(f"  YOLO CPU timing breakdown:")
        debug_print(f"   - Cache/session access: {cache_time:.3f}s")
        debug_print(f"   - Data preparation: {prep_time:.3f}s")
        debug_print(f"   - CPU inference: {inference_time:.3f}s")
        debug_print(f"   - Total: {total_time:.3f}s")
    
    return output

def fast_nms_opencv(boxes, scores, iou_threshold):
    if len(boxes) == 0:
        return []
    
    boxes_cv = []
    for box in boxes:
        x1, y1, x2, y2 = box
        boxes_cv.append([float(x1), float(y1), float(x2 - x1), float(y2 - y1)])
    
    indices = cv2.dnn.NMSBoxes(
        boxes_cv, scores.tolist(), 
        score_threshold=0.0, nms_threshold=float(iou_threshold)
    )
    
    return indices.flatten() if len(indices) > 0 else []

def xywh2xyxy_vectorized(boxes, scaling_factors):
    xy = boxes[:, :2]
    wh = boxes[:, 2:]
    xy1 = xy - wh * 0.5
    xy2 = xy + wh * 0.5
    xyxy = np.concatenate([xy1, xy2], axis=1)
    xyxy[:, [0, 2]] *= scaling_factors[0]
    xyxy[:, [1, 3]] *= scaling_factors[1]
    return xyxy

def postprocess_optimized(output, input_size, orig_size, scaling_factors, 
                         conf_thres=0.1, iou_thres=0.1, enable_timing=True, enable_debug=False, 
                         batch_idx=0):
    """
    🚀 OPTIMIZED: Removed memory pool, cleaner postprocessing
    """
    start_time = time.time()
    if enable_timing:
        debug_print(f"🔧 YOLO: Postprocessing detections (VECTORIZED)...")
    
    # Handle batch output
    if len(output[0].shape) == 3:  # Batch output
        predictions = np.squeeze(output[0][batch_idx])
    else:  # Single image output
        predictions = np.squeeze(output[0])
        
    if predictions.shape[0] not in [5, 84]:
        debug_print(f"⚠️  YOLO: Unexpected shape: {predictions.shape}")
        return []

    predictions = predictions.transpose()
    
    if enable_debug:
        debug_print(f"  YOLO Debug: Processing {len(predictions)} predictions")
    
    if predictions.shape[1] == 5:
        confs = predictions[:, 4]
        class_ids = np.zeros(len(confs), dtype=np.int32)
    else:
        obj_conf = predictions[:, 4]
        class_confs = predictions[:, 5:]
        class_ids = np.argmax(class_confs, axis=1)
        class_scores = class_confs[np.arange(len(class_confs)), class_ids]
        confs = obj_conf * class_scores

    keep_mask = confs > conf_thres
    if not np.any(keep_mask):
        if enable_timing:
            debug_print("⚠️  YOLO: No detections above confidence threshold.")
        return []

    valid_predictions = predictions[keep_mask]
    valid_confs = confs[keep_mask]
    
    if enable_debug:
        debug_print(f"  YOLO Debug: {len(valid_predictions)} detections after confidence filtering")

    boxes = xywh2xyxy_vectorized(valid_predictions[:, :4], scaling_factors)
    keep_indices = fast_nms_opencv(boxes, valid_confs, iou_threshold=iou_thres)
    
    if len(keep_indices) == 0:
        if enable_timing:
            debug_print("⚠️  YOLO: No detections after NMS.")
        return []
    
    final_boxes = boxes[keep_indices]
    
    if enable_timing:
        total_time = time.time() - start_time
        debug_print(f"  YOLO Postprocessing (VECTORIZED): {total_time:.3f}s")
        debug_print(f"  YOLO Found {len(final_boxes)} detections after filtering")
    
    return final_boxes.astype(int).tolist()

def load_and_prepare_image_from_pil(pil_image, max_resolution, enable_timing=True):
    """🚀 Load and prepare from PIL Image (no file I/O)"""
    start_time = time.time()
    if enable_timing:
        debug_print(f"📸 YOLO: Preparing PIL image")
    
    # Convert PIL to BGR numpy array directly
    img_rgb = np.array(pil_image.convert('RGB'))
    img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
    
    orig_h, orig_w = img_bgr.shape[:2]
    target_w = min(round_to_multiple(orig_w, 32), max_resolution[0])
    target_h = min(round_to_multiple(orig_h, 32), max_resolution[1])
    
    resize_start = time.time()
    # 🚀 OPTIMIZATION 1: Use cv2 resize instead of PIL (faster)
    img_resized_bgr = cv2.resize(img_bgr, (target_w, target_h), interpolation=cv2.INTER_AREA)
    resize_time = time.time() - resize_start
    
    convert_start = time.time()
    # 🚀 OPTIMIZATION 2: Direct normalization in one step
    norm_img = img_resized_bgr.astype(np.float32, copy=False) * np.float32(1.0/255.0)
    norm_img -= np.array([0.485, 0.456, 0.406], dtype=np.float32)
    norm_img /= np.array([0.229, 0.224, 0.225], dtype=np.float32)
    
    # 🚀 OPTIMIZATION 3: Direct transpose
    norm_img = norm_img.transpose(2, 0, 1)[np.newaxis, :]
    
    convert_time = time.time() - convert_start
    
    scaling_factors = (orig_w / target_w, orig_h / target_h)
    
    if enable_timing:
        total_time = time.time() - start_time
        debug_print(f"  YOLO image preparation: {total_time:.3f}s")
        debug_print(f"   - Loading: {resize_time:.3f}s")
        debug_print(f"   - Array conversion: {convert_time:.3f}s")
    
    return norm_img, (target_w, target_h), (orig_w, orig_h), scaling_factors, img_resized_bgr

class YOLODetector:
    """🚀 OPTIMIZED YOLO detector class with ultra-fast content filtering"""
    
    def __init__(self, config: YOLOConfig = None):
        self.config = config or YOLOConfig()
    
    def detect(self, image_input) -> List[Dict[str, Any]]:
        """
        Run YOLO detection on image
        Args:
            image_input: str (file path) or PIL.Image
        """
        if isinstance(image_input, str):
            # File path - use existing fast loading
            input_tensor, input_size, orig_size, scaling_factors, content_image = load_and_prepare_image_ultra_fast(
                image_input, self.config.max_resolution, self.config.enable_timing
            )
        else:
            # PIL Image - use new PIL loading
            input_tensor, input_size, orig_size, scaling_factors, content_image = load_and_prepare_image_from_pil(
                image_input, self.config.max_resolution, self.config.enable_timing
            )
        
        total_start = time.time()
        
        if self.config.enable_timing:
            debug_print(f"\n🎯 Starting YOLO detection pipeline...")
            debug_print(f"🤖 Model: {self.config.model_path}")
            if self.config.enable_content_filtering:
                debug_print(f"🚀 Content filtering: ENABLED (min pixels: {self.config.min_content_pixels})")
            debug_print("=" * 60)
        
        output = run_inference_optimized(self.config.model_path, input_tensor, self.config.enable_timing)
        
        boxes_raw = postprocess_optimized(
            output, input_size, orig_size, scaling_factors,
            self.config.conf_threshold, self.config.iou_threshold, 
            self.config.enable_timing, self.config.enable_debug
        )
        
        # Convert to standardized format
        detections = []
        for i, box in enumerate(boxes_raw):
            x1, y1, x2, y2 = box
            clipped_bbox = self.clip_bbox_to_image_bounds([x1, y1, x2, y2], orig_size[0], orig_size[1])
            if clipped_bbox:
                detections.append({
                    "bbox": clipped_bbox,
                    "type": "icon",
                    "source": "yolo",
                    "confidence": 1.0,
                    "id": i
                })
        
        # 🚀 Ultra-fast content filtering (using already loaded image)
        if self.config.enable_content_filtering and len(detections) > 0:
            filter_start = time.time()
            detections, filtered_count = filter_sparse_boxes_ultra_fast(
                content_image, detections, self.config.min_content_pixels
            )
            filter_time = time.time() - filter_start
            
            if self.config.enable_timing and filtered_count > 0:
                debug_print(f"  🚀 Content filtering: {filter_time:.3f}s")
                debug_print(f"    Filtered out {filtered_count} sparse boxes ({len(detections)} kept)")
        
        if self.config.enable_timing:
            total_time = time.time() - total_start
            debug_print("=" * 60)
            debug_print(f"  🎯 YOLO Pipeline completed in {total_time:.3f}s")
            debug_print(f"  Final result: {len(detections)} quality YOLO detections")
        
        return detections
    
    def clip_bbox_to_image_bounds(self, bbox, image_width, image_height):
        """Clip bounding box coordinates to image boundaries"""
        x1, y1, x2, y2 = bbox
        
        # Clip to image bounds
        x1 = max(0, min(x1, image_width))
        y1 = max(0, min(y1, image_height))
        x2 = max(0, min(x2, image_width))
        y2 = max(0, min(y2, image_height))
        
        # Ensure valid box (x2 > x1, y2 > y1)
        if x2 <= x1 or y2 <= y1:
            return None  # Invalid box
        
        return [x1, y1, x2, y2]

def main():
    """CLI interface for YOLO detector"""
    parser = argparse.ArgumentParser(
        description="YOLO Object Detection with Content Filtering",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python yolo_detector.py image.jpg
  python yolo_detector.py image.jpg --model custom_model.onnx --conf 0.25
  python yolo_detector.py image.jpg --output results.json --format json
  python yolo_detector.py image.jpg --no-timing --no-content-filter
  python yolo_detector.py *.jpg --batch --output-dir results/
        """
    )
    
    # Input arguments
    parser.add_argument(
        "images", 
        nargs="+", 
        help="Input image path(s). Supports glob patterns for batch processing."
    )
    
    # Model configuration
    parser.add_argument(
        "--model", "-m",
        default="models/model_dynamic.onnx",
        help="Path to ONNX model file (default: models/model_dynamic.onnx)"
    )
    
    # Detection thresholds
    parser.add_argument(
        "--conf", "-c",
        type=float,
        default=0.1,
        help="Confidence threshold for detections (default: 0.1)"
    )
    
    parser.add_argument(
        "--iou", "-i",
        type=float,
        default=0.1,
        help="IoU threshold for Non-Maximum Suppression (default: 0.1)"
    )
    
    # Resolution settings
    parser.add_argument(
        "--max-width",
        type=int,
        default=2560,
        help="Maximum width for input images (default: 2560)"
    )
    
    parser.add_argument(
        "--max-height",
        type=int,
        default=2560,
        help="Maximum height for input images (default: 2560)"
    )
    
    # Content filtering
    parser.add_argument(
        "--no-content-filter",
        action="store_true",
        help="Disable content filtering for sparse boxes"
    )
    
    parser.add_argument(
        "--min-content-pixels",
        type=int,
        default=5,
        help="Minimum content pixels to keep a detection (default: 5)"
    )
    
    # Output options
    parser.add_argument(
        "--output", "-o",
        help="Output file path. If not specified, prints to stdout."
    )
    
    parser.add_argument(
        "--format", "-f",
        choices=["json", "csv", "txt", "simple"],
        default="simple",
        help="Output format (default: simple)"
    )
    
    parser.add_argument(
        "--output-dir",
        help="Output directory for batch processing. Creates files with same name + '_detections.json'"
    )
    
    # Display options
    parser.add_argument(
        "--no-timing",
        action="store_true",
        help="Disable timing information"
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug output"
    )
    
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Minimal output (only results)"
    )
    
    # Batch processing
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Enable batch processing mode"
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if not os.path.exists(args.model):
        debug_print(f"❌ Error: Model file not found: {args.model}", file=sys.stderr)
        sys.exit(1)
    
    if args.output_dir and not args.batch:
        debug_print("⚠️  Warning: --output-dir only used in batch mode", file=sys.stderr)
    
    # Create YOLO configuration
    config = YOLOConfig(
        conf_threshold=args.conf,
        iou_threshold=args.iou,
        max_resolution=(args.max_width, args.max_height),
        enable_timing=not args.no_timing and not args.quiet,
        enable_debug=args.debug,
        model_path=args.model,
        enable_content_filtering=not args.no_content_filter,
        min_content_pixels=args.min_content_pixels
    )
    
    # Initialize detector
    detector = YOLODetector(config)
    
    # Process images
    if args.batch or len(args.images) > 1:
        process_batch(detector, args)
    else:
        process_single(detector, args.images[0], args)

def process_single(detector, image_path, args):
    """Process a single image"""
    if not os.path.exists(image_path):
        debug_print(f"❌ Error: Image file not found: {image_path}", file=sys.stderr)
        sys.exit(1)
    
    try:
        detections = detector.detect(image_path)
        output_results(detections, image_path, args)
        
    except Exception as e:
        debug_print(f"❌ Error processing {image_path}: {e}", file=sys.stderr)
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)

def process_batch(detector, args):
    """Process multiple images in batch mode"""
    import glob
    
    # Expand glob patterns
    all_images = []
    for pattern in args.images:
        matches = glob.glob(pattern)
        if matches:
            all_images.extend(matches)
        else:
            if os.path.exists(pattern):
                all_images.append(pattern)
            else:
                debug_print(f"⚠️  Warning: No matches for pattern: {pattern}", file=sys.stderr)
    
    if not all_images:
        debug_print("❌ Error: No valid images found", file=sys.stderr)
        sys.exit(1)
    
    # Create output directory if specified
    if args.output_dir:
        os.makedirs(args.output_dir, exist_ok=True)
    
    results = {}
    successful = 0
    failed = 0
    
    if not args.quiet:
        debug_print(f"🚀 Processing {len(all_images)} images in batch mode...")
        debug_print("=" * 60)
    
    for i, image_path in enumerate(all_images, 1):
        if not args.quiet:
            debug_print(f"\n[{i}/{len(all_images)}] Processing: {image_path}")
        
        try:
            detections = detector.detect(image_path)
            results[image_path] = detections
            successful += 1
            
            # Save individual results if output directory specified
            if args.output_dir:
                base_name = os.path.splitext(os.path.basename(image_path))[0]
                output_file = os.path.join(args.output_dir, f"{base_name}_detections.json")
                with open(output_file, 'w') as f:
                    json.dump({
                        "image": image_path,
                        "detections": detections,
                        "count": len(detections)
                    }, f, indent=2)
                if not args.quiet:
                    debug_print(f"  💾 Saved results to: {output_file}")
            
        except Exception as e:
            debug_print(f"❌ Error processing {image_path}: {e}", file=sys.stderr)
            results[image_path] = {"error": str(e)}
            failed += 1
    
    # Output batch summary
    if not args.quiet:
        debug_print("\n" + "=" * 60)
        debug_print(f"📊 Batch processing complete:")
        debug_print(f"  ✅ Successful: {successful}")
        debug_print(f"  ❌ Failed: {failed}")
        debug_print(f"  📁 Total images: {len(all_images)}")
    
    # Output combined results
    if not args.output_dir:
        output_batch_results(results, args)

def output_results(detections, image_path, args):
    """Output detection results in specified format"""
    if args.format == "json":
        result = {
            "image": image_path,
            "detections": detections,
            "count": len(detections)
        }
        output_text = json.dumps(result, indent=2)
        
    elif args.format == "csv":
        lines = ["image,x1,y1,x2,y2,type,confidence,source"]
        for det in detections:
            bbox = det["bbox"]
            lines.append(f"{image_path},{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]},{det['type']},{det['confidence']},{det['source']}")
        output_text = "\n".join(lines)
        
    elif args.format == "txt":
        lines = [f"Image: {image_path}", f"Detections: {len(detections)}", ""]
        for i, det in enumerate(detections):
            bbox = det["bbox"]
            lines.append(f"Detection {i+1}: [{bbox[0]}, {bbox[1]}, {bbox[2]}, {bbox[3]}] ({det['type']}, conf: {det['confidence']:.3f})")
        output_text = "\n".join(lines)
        
    else:  # simple format
        if args.quiet:
            output_text = str(len(detections))
        else:
            lines = [f"📷 {image_path}: {len(detections)} detections"]
            for i, det in enumerate(detections):
                bbox = det["bbox"]
                w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
                lines.append(f"  {i+1:2d}. [{bbox[0]:4d},{bbox[1]:4d}] {w:3d}x{h:3d} ({det['confidence']:.3f})")
            output_text = "\n".join(lines)
    
    # Output to file or stdout
    if args.output:
        with open(args.output, 'w') as f:
            f.write(output_text)
        if not args.quiet:
            debug_print(f"💾 Results saved to: {args.output}")
    else:
        debug_print(output_text)

def output_batch_results(results, args):
    """Output batch results in specified format"""
    if args.format == "json":
        output_text = json.dumps(results, indent=2)
    else:
        # Summary format for other types
        lines = []
        total_detections = 0
        for image_path, detections in results.items():
            if isinstance(detections, list):
                count = len(detections)
                total_detections += count
                lines.append(f"{image_path}: {count} detections")
            else:
                lines.append(f"{image_path}: ERROR - {detections.get('error', 'Unknown error')}")
        
        lines.append(f"\nTotal detections across all images: {total_detections}")
        output_text = "\n".join(lines)
    
    if args.output:
        with open(args.output, 'w') as f:
            f.write(output_text)
        if not args.quiet:
            debug_print(f"💾 Batch results saved to: {args.output}")
    else:
        debug_print(output_text)

if __name__ == "__main__":
    main()



