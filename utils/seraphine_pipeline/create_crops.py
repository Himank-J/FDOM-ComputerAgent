import cv2
import json
import os
import random
import numpy as np
from typing import List, Dict, Tuple
from .helpers import debug_print


class StochasticCropExtractor:
    """
    Extracts crops from an image based on bounding boxes with stochastic variations.
    """
    
    def __init__(self, image_path: str, output_dir: str = "utils/crops"):
        self.image_path = image_path
        self.output_dir = output_dir
        self.image = None
        self.image_height = 0
        self.image_width = 0
        
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        # Load the image
        self._load_image()
    
    def _load_image(self):
        """Load the source image"""
        self.image = cv2.imread(self.image_path)
        if self.image is None:
            raise ValueError(f"Could not load image: {self.image_path}")
        
        self.image_height, self.image_width = self.image.shape[:2]
        debug_print(f"📷 Loaded image: {self.image_width}x{self.image_height}")
    
    def _apply_stochastic_padding(self, bbox: List[int]) -> List[int]:
        """
        Apply random padding to bbox coordinates (3-8px variation)
        
        Args:
            bbox: [x1, y1, x2, y2] coordinates
            
        Returns:
            Modified bbox with stochastic padding
        """
        x1, y1, x2, y2 = bbox
        
        # Random padding between 3-8 pixels
        pad_left = random.randint(1, 3)
        pad_top = random.randint(1, 3)
        pad_right = random.randint(1, 3)
        pad_bottom = random.randint(1, 3)
        
        # Apply padding with random direction (expand or contract)
        # 70% chance to expand, 30% chance to contract
        expand_left = random.random() < 0.5
        expand_top = random.random() < 0.5
        expand_right = random.random() < 0.5
        expand_bottom = random.random() < 0.5
        
        new_x1 = x1 - pad_left if expand_left else x1 + pad_left
        new_y1 = y1 - pad_top if expand_top else y1 + pad_top
        new_x2 = x2 + pad_right if expand_right else x2 - pad_right
        new_y2 = y2 + pad_bottom if expand_bottom else y2 - pad_bottom
        
        # Ensure coordinates stay within image bounds
        new_x1 = max(0, min(new_x1, self.image_width - 1))
        new_y1 = max(0, min(new_y1, self.image_height - 1))
        new_x2 = max(new_x1 + 1, min(new_x2, self.image_width))
        new_y2 = max(new_y1 + 1, min(new_y2, self.image_height))
        
        return [new_x1, new_y1, new_x2, new_y2]
    
    def extract_crop(self, bbox: List[int], merged_id: int, item_info: Dict = None) -> str:
        """
        Extract a single crop with stochastic variations
        
        Args:
            bbox: [x1, y1, x2, y2] coordinates
            merged_id: Unique identifier for the crop
            item_info: Additional info about the item
            
        Returns:
            Path to saved crop image
        """
        # Apply stochastic padding
        stoch_bbox = self._apply_stochastic_padding(bbox)
        x1, y1, x2, y2 = stoch_bbox
        
        # Extract the crop
        crop = self.image[y1:y2, x1:x2]
        
        # Generate filename with additional info
        item_type = item_info.get('type', 'unknown') if item_info else 'unknown'
        source = item_info.get('source', 'unknown') if item_info else 'unknown'
        
        filename = f"crop_{merged_id:03d}_{item_type}_{source}.png"
        output_path = os.path.join(self.output_dir, filename)
        
        # Save the crop
        cv2.imwrite(output_path, crop)
        
        # Log the extraction
        original_size = f"{bbox[2]-bbox[0]}x{bbox[3]-bbox[1]}"
        stoch_size = f"{x2-x1}x{y2-y1}"
        padding_info = f"({x1-bbox[0]:+d},{y1-bbox[1]:+d},{x2-bbox[2]:+d},{y2-bbox[3]:+d})"
        
        debug_print(f"✂️  Crop {merged_id:03d}: {original_size} → {stoch_size} {padding_info} → {filename}")
        
        return output_path
    
    def extract_all_crops(self, json_file_path: str) -> Dict[int, str]:
        """
        Extract all crops from JSON detection results
        
        Args:
            json_file_path: Path to JSON file with detection results
            
        Returns:
            Dictionary mapping merged_id to crop file path
        """
        debug_print(f"📂 Loading detection results from: {json_file_path}")
        
        # Load JSON data
        with open(json_file_path, 'r') as f:
            detections = json.load(f)
        
        debug_print(f"📊 Found {len(detections)} detections to process")
        
        # Track extracted crops
        extracted_crops = {}
        
        # Process each detection
        for detection in detections:
            try:
                bbox = detection['bbox']
                merged_id = detection['merged_id']
                
                # Extract crop with stochastic variations
                crop_path = self.extract_crop(bbox, merged_id, detection)
                extracted_crops[merged_id] = crop_path
                
            except Exception as e:
                debug_print(f"❌ Error processing detection {detection.get('merged_id', 'unknown')}: {e}")
        
        debug_print(f"✅ Successfully extracted {len(extracted_crops)} crops")
        return extracted_crops
    
    def create_summary_report(self, extracted_crops: Dict[int, str], json_file_path: str):
        """Create a summary report of extracted crops"""
        
        # Load original detections for analysis
        with open(json_file_path, 'r') as f:
            detections = json.load(f)
        
        # Group by type and source
        type_counts = {}
        source_counts = {}
        
        for detection in detections:
            item_type = detection.get('type', 'unknown')
            source = detection.get('source', 'unknown')
            
            type_counts[item_type] = type_counts.get(item_type, 0) + 1
            source_counts[source] = source_counts.get(source, 0) + 1
        
        # Create summary
        summary_path = os.path.join(self.output_dir, "crop_extraction_summary.txt")
        
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write("STOCHASTIC CROP EXTRACTION SUMMARY\n")
            f.write("=" * 50 + "\n\n")
            
            f.write(f"Source Image: {self.image_path}\n")
            f.write(f"Image Dimensions: {self.image_width}x{self.image_height}\n")
            f.write(f"Total Detections: {len(detections)}\n")
            f.write(f"Successfully Extracted: {len(extracted_crops)}\n")
            f.write(f"Output Directory: {self.output_dir}\n\n")
            
            f.write("BREAKDOWN BY TYPE:\n")
            for item_type, count in sorted(type_counts.items()):
                f.write(f"  {item_type}: {count}\n")
            
            f.write(f"\nBREAKDOWN BY SOURCE:\n")
            for source, count in sorted(source_counts.items()):
                f.write(f"  {source}: {count}\n")
            
            f.write(f"\nSTOCHASTIC VARIATIONS:\n")
            f.write(f"  Padding Range: 3-8 pixels\n")
            f.write(f"  Expansion Probability: 70%\n")
            f.write(f"  Contraction Probability: 30%\n")
            f.write(f"  Boundary Clamping: Enabled\n")
        
        debug_print(f"Summary report saved: {summary_path}")


def main():
    """Main execution function"""
    debug_print("🚀 Starting Stochastic Crop Extraction")
    debug_print("=" * 50)
    
    # Configuration
    IMAGE_PATH = "word.png"
    JSON_PATH = "utils/word_merged_result_08-35.json"
    OUTPUT_DIR = "utils/crops"
    
    # Verify input files exist
    if not os.path.exists(IMAGE_PATH):
        debug_print(f"❌ Error: Image file not found: {IMAGE_PATH}")
        return
    
    if not os.path.exists(JSON_PATH):
        debug_print(f"❌ Error: JSON file not found: {JSON_PATH}")
        return
    
    try:
        # Initialize the crop extractor
        extractor = StochasticCropExtractor(IMAGE_PATH, OUTPUT_DIR)
        
        # Extract all crops
        extracted_crops = extractor.extract_all_crops(JSON_PATH)
        
        # Create summary report
        extractor.create_summary_report(extracted_crops, JSON_PATH)
        
        debug_print(f"\n🎉 Crop extraction complete!")
        debug_print(f"📁 Crops saved to: {OUTPUT_DIR}/")
        debug_print(f"📊 Total crops: {len(extracted_crops)}")
        
        # Show some examples
        if extracted_crops:
            debug_print(f"\n📸 Sample crops:")
            sample_ids = list(extracted_crops.keys())[:5]
            for crop_id in sample_ids:
                crop_path = extracted_crops[crop_id]
                filename = os.path.basename(crop_path)
                debug_print(f"  ID {crop_id:03d}: {filename}")
            
            if len(extracted_crops) > 5:
                debug_print(f"  ... and {len(extracted_crops) - 5} more crops")
    
    except Exception as e:
        debug_print(f"❌ Fatal error: {e}")


if __name__ == "__main__":
    main()
