"""
Clean OCR detection utility - extracted from ocr_onnx.py
Only detection, no text recognition.
No imports from original files allowed.
"""
import time
import numpy as np
import cv2
import onnxruntime as ort
from PIL import Image
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple
import requests
import os
from .helpers import debug_print

@dataclass
class OCRDetConfig:
    """Configuration for OCR detection pipeline"""
    det_threshold: float = 0.3
    max_side_len: int = 960
    enable_timing: bool = True
    enable_debug: bool = False
    model_path: str = "models/ch_PP-OCRv3_det_infer.onnx"
    min_box_size: int = 3
    use_dilation: bool = True
    padding_x: int = 5  # Fixed horizontal padding
    padding_y_percent: float = 0.30  # Vertical padding percentage
    min_padding_y: int = 5

class OCRDetMemoryPool:
    """Memory pool for OCR detection"""
    def __init__(self, max_boxes=200):
        self.box_pool = [np.empty((4, 2), dtype=np.float32) for _ in range(max_boxes)]
        self.used_boxes = 0
        self.max_boxes = max_boxes
    
    def get_box_array(self):
        if self.used_boxes < self.max_boxes:
            arr = self.box_pool[self.used_boxes]
            self.used_boxes += 1
            return arr
        return np.empty((4, 2), dtype=np.float32)
    
    def reset(self):
        self.used_boxes = 0

class OCRModelCache:
    """Singleton cache for OCR detection model"""
    _instance = None
    _session = None
    _model_path = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def get_session(self, model_path):
        if self._session is None or self._model_path != model_path:
            if self._session is None:
                debug_print("  Loading CPU-optimized OCR detection model...")
            else:
                debug_print("  Reloading OCR detection model...")
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
            
            load_time = time.time() - load_start
            debug_print(f"  OCR detection model loading: {load_time:.3f}s")
        
        return self._session

# Global instances
ocr_memory_pool = OCRDetMemoryPool()
ocr_model_cache = OCRModelCache()

def preprocess_det(image, max_side_len, enable_timing=True):
    """Detection preprocessing"""
    preprocess_start = time.time()
    
    img = np.array(image)
    height, width, _ = img.shape
    
    ratio = min(max_side_len / float(width), max_side_len / float(height))
    resize_w = int(width * ratio)
    resize_h = int(height * ratio)

    resize_w = resize_w if resize_w % 32 == 0 else (resize_w // 32) * 32
    resize_h = resize_h if resize_h % 32 == 0 else (resize_h // 32) * 32

    resized_img = image.resize((resize_w, resize_h), resample=Image.BILINEAR)
    
    norm_img = np.array(resized_img).astype(np.float32) / 255.0
    norm_img -= np.array([0.485, 0.456, 0.406])
    norm_img /= np.array([0.229, 0.224, 0.225])
    norm_img = norm_img.transpose(2, 0, 1)[np.newaxis, :]

    ratio_h = height / float(resize_h)
    ratio_w = width / float(resize_w)
    
    if enable_timing:
        preprocess_time = time.time() - preprocess_start
        debug_print(f"  OCR image scaled: {width}x{height} -> {resize_w}x{resize_h} (ratio: {ratio:.3f}) in {preprocess_time:.3f}s")
    
    return norm_img, ratio_h, ratio_w, time.time() - preprocess_start

def extract_boxes_opencv(score_map, ratio_w, ratio_h, det_threshold, min_box_size, use_dilation, enable_timing=True):
    """Extract boxes using OpenCV with dilation"""
    extraction_start = time.time()
    
    binary = (score_map > det_threshold).astype(np.uint8) * 255

    # Apply dilation to improve text detection
    if use_dilation:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        binary = cv2.dilate(binary, kernel, iterations=1)

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    boxes = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        
        if w >= min_box_size and h >= min_box_size:
            box = np.array([
                [x * ratio_w, y * ratio_h],
                [(x + w) * ratio_w, y * ratio_h],
                [(x + w) * ratio_w, (y + h) * ratio_h],
                [x * ratio_w, (y + h) * ratio_h]
            ], dtype=np.float32)
            boxes.append(box)
    
    if enable_timing:
        extraction_time = time.time() - extraction_start
        debug_print(f"  OCR box extraction: {extraction_time:.3f}s -> {len(boxes)} boxes")
    
    return boxes, time.time() - extraction_start

class OCRDetector:
    """Clean OCR detector class - detection only, no recognition"""
    
    def __init__(self, config: OCRDetConfig = None):
        self.config = config or OCRDetConfig()
        self.memory_pool = OCRDetMemoryPool()
    
    def detect(self, image_input):
        """
        Run OCR detection on image (no text recognition)
        
        Args:
            image_input: Path to image file or numpy array
            
        Returns:
            List of detection dictionaries with 'bbox' and metadata
        """
        total_start = time.time()
        
        if self.config.enable_timing:
            debug_print(f"\n📝 Starting OCR detection pipeline...")
            debug_print(f"🤖 Model: {self.config.model_path}")
            debug_print("=" * 60)
        
        # Load image
        if isinstance(image_input, np.ndarray):
            # Convert BGR numpy to PIL RGB
            img_rgb = cv2.cvtColor(image_input, cv2.COLOR_BGR2RGB) 
            image = Image.fromarray(img_rgb)
        elif isinstance(image_input, str):
            image = Image.open(image_input).convert("RGB")
        else:
            image = image_input.convert("RGB")
        
        # Image setup
        setup_start = time.time()
        np_img = np.array(image)
        img_height, img_width = np_img.shape[:2]
        setup_time = time.time() - setup_start
        
        # Detection preprocessing
        det_input, ratio_h, ratio_w, det_preprocess_time = preprocess_det(
            image, self.config.max_side_len, self.config.enable_timing
        )
        
        # Detection inference
        det_inference_start = time.time()
        session = ocr_model_cache.get_session(self.config.model_path)
        det_output = session.run(None, {"x": det_input})[0]
        det_inference_time = time.time() - det_inference_start
        
        if self.config.enable_timing:
            debug_print(f"  OCR detection inference: {det_inference_time:.3f}s")
        
        # Extract boxes
        score_map = det_output[0][0]
        boxes, box_extraction_time = extract_boxes_opencv(
            score_map, ratio_w, ratio_h, 
            self.config.det_threshold, self.config.min_box_size, 
            self.config.use_dilation, self.config.enable_timing
        )
        
        if not boxes:
            if self.config.enable_timing:
                debug_print("⚠️  OCR: No text regions detected")
            return []
        
        # Convert to standardized format with padding (same as ocr_onnx.py)
        detections = []
        for i, box in enumerate(boxes):
            x1, y1 = int(np.min(box[:, 0])), int(np.min(box[:, 1]))
            x2, y2 = int(np.max(box[:, 0])), int(np.max(box[:, 1]))
            
            # Apply padding (same logic as ocr_onnx.py)
            box_height = y2 - y1
            padding_x = self.config.padding_x
            padding_y = max(int(box_height * self.config.padding_y_percent), self.config.min_padding_y)
            
            x1_padded = max(0, x1 - padding_x)
            y1_padded = max(0, y1 - padding_y)
            x2_padded = min(img_width, x2 + padding_x)
            y2_padded = min(img_height, y2 + padding_y)
            
            detections.append({
                "bbox": [x1_padded, y1_padded, x2_padded, y2_padded],
                "type": "text",
                "source": "ocr_det",
                "confidence": 1.0,  # We don't have individual confidences
                "id": i
            })
        
        if self.config.enable_timing:
            total_time = time.time() - total_start
            debug_print("=" * 60)
            debug_print(f"  📝 OCR Detection Pipeline completed in {total_time:.3f}s")
            debug_print(f"  Found {len(detections)} OCR detections")
            debug_print(f"  Timing breakdown:")
            debug_print(f"   - Setup: {setup_time:.3f}s")
            debug_print(f"   - Preprocessing: {det_preprocess_time:.3f}s")
            debug_print(f"   - Inference: {det_inference_time:.3f}s")
            debug_print(f"   - Box extraction: {box_extraction_time:.3f}s")
        
        return detections