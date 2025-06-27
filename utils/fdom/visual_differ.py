"""
VisualDiffer - Visual comparison and hash-based change detection for fDOM Framework
Handles screenshot comparison using hash and OpenCV-based region extraction
"""
import hashlib
import os
from pathlib import Path
from typing import Dict, Optional, Tuple
import numpy as np
from PIL import Image
from rich.console import Console
from rich.panel import Panel
import time

class VisualDiffer:
    """
    Handles visual comparison and change detection between screenshots
    """
    
    def __init__(self, config_manager):
        self.config = config_manager
        self.console = Console()
    
    def calculate_image_hash(self, image_path: str) -> str:
        """
        Calculate perceptual hash of an image
        
        Args:
            image_path: Path to image file
            
        Returns:
            Hash string for comparison
        """
        try:
            with Image.open(image_path) as img:
                # Convert to grayscale and resize for consistent hashing
                img = img.convert('L').resize((64, 64))
                
                # Calculate hash using pixel data
                pixels = np.array(img)
                hash_obj = hashlib.md5(pixels.tobytes())
                return hash_obj.hexdigest()
                
        except Exception as e:
            self.console.print(f"[red]❌ Error calculating hash for {image_path}: {e}[/red]")
            return ""

    def extract_change_regions(self, before_path: str, after_path: str, 
                              output_diff_path: str, click_coords: Optional[Tuple] = None) -> Dict:
        """
        Extract FULL difference region as single crop (following old.txt approach)
        """
        try:
            import cv2
            import numpy as np
            
            self.console.print(f"[yellow]🔍 EXTRACTING FULL DIFFERENCE REGION...[/yellow]")
            self.console.print(f"Before: {Path(before_path).name}")
            self.console.print(f"After:  {Path(after_path).name}")
            
            # Load both images
            img1 = cv2.imread(before_path)
            img2 = cv2.imread(after_path)
            
            if img1 is None or img2 is None:
                return {"success": False, "error": "Could not load images"}
            
            # Match dimensions if needed
            if img1.shape != img2.shape:
                h = min(img1.shape[0], img2.shape[0])
                w = min(img1.shape[1], img2.shape[1])
                img1 = cv2.resize(img1, (w, h))
                img2 = cv2.resize(img2, (w, h))
                self.console.print(f"[yellow]⚠️ Resized both images to ({w}, {h})[/yellow]")

            # Convert to grayscale and compute absolute difference
            gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
            gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
            diff = cv2.absdiff(gray1, gray2)

            # Threshold and dilate
            _, thresh = cv2.threshold(diff, 15, 255, cv2.THRESH_BINARY)
            dilated = cv2.dilate(thresh, np.ones((5, 5), np.uint8), iterations=2)

            # Find contours
            contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            boxes = [cv2.boundingRect(cnt) for cnt in contours if cv2.contourArea(cnt) > 500]

            if not boxes:
                self.console.print("[red]ℹ️ No significant visual differences found.[/red]")
                return {"success": False, "reason": "No significant differences detected"}

            # Compute bounding box of ALL diffs (unified region)
            x_min = min(x for x, y, w, h in boxes)
            y_min = min(y for x, y, w, h in boxes)
            x_max = max(x + w for x, y, w, h in boxes)
            y_max = max(y + h for x, y, w, h in boxes)

            # Extract the unified changed region from AFTER image
            crop = img2[y_min:y_max, x_min:x_max]
            
            # Save ONLY the cropped popup/menu region
            cv2.imwrite(output_diff_path, crop)
            
            # self.console.print(f"[green]✅ Saved popup/menu region: {Path(output_diff_path).name}[/green]")
            # self.console.print(f"[cyan]📦 Crop region: ({x_min}, {y_min}) to ({x_max}, {y_max})[/cyan]")
            # self.console.print(f"[cyan]📐 Crop size: {x_max-x_min} x {y_max-y_min}[/cyan]")
            
            # Return the unified region as a single tuple (x, y, width, height)
            unified_region = (x_min, y_min, x_max - x_min, y_max - y_min)
            
            return {
                "success": True,
                "regions": [unified_region],  # Single unified region
                "change_percentage": 100,  # Always significant since we found changes
                "detection_method": "opencv_unified_crop",
                "total_regions": 1,
                "diff_image_path": output_diff_path,
                "crop_bounds": (x_min, y_min, x_max, y_max)
            }
            
        except Exception as e:
            self.console.print(f"[red]❌ Full difference extraction failed: {e}[/red]")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}

    def calculate_similarity_percentage(self, image1_path: str, image2_path: str, threshold: int = 15) -> float:
        """
        Calculate similarity percentage between two images using pixel difference analysis
        
        Args:
            image1_path: Path to first image
            image2_path: Path to second image  
            threshold: Pixel difference threshold (lower = more sensitive)
            
        Returns:
            Similarity percentage (0-100, where 100 = identical)
        """
        try:
            import cv2
            import numpy as np
            
            # Load images
            img1 = cv2.imread(image1_path)
            img2 = cv2.imread(image2_path)
            
            if img1 is None or img2 is None:
                self.console.print(f"[red]❌ Could not load images for comparison[/red]")
                return 0.0
            
            # Ensure same dimensions
            if img1.shape != img2.shape:
                h = min(img1.shape[0], img2.shape[0])
                w = min(img1.shape[1], img2.shape[1])
                img1 = cv2.resize(img1, (w, h))
                img2 = cv2.resize(img2, (w, h))
            
            # Convert to grayscale and calculate difference
            gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
            gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
            diff = cv2.absdiff(gray1, gray2)
            
            # Count pixels that differ significantly
            different_pixels = np.sum(diff > threshold)
            total_pixels = diff.shape[0] * diff.shape[1]
            
            # Calculate similarity percentage
            similarity = ((total_pixels - different_pixels) / total_pixels) * 100
            
            return round(similarity, 2)
            
        except Exception as e:
            self.console.print(f"[red]❌ Similarity calculation failed: {e}[/red]")
            return 0.0


# Test function
def test_visual_differ():
    """Test the VisualDiffer functionality"""
    from config_manager import ConfigManager
    
    config = ConfigManager()
    differ = VisualDiffer(config)
    
    print("🧪 Testing VisualDiffer...")
    
    # Test hash calculation
    test_image = "../../apps/notepad/screenshots/S001.png"
    if Path(test_image).exists():
        hash_result = differ.calculate_image_hash(test_image)
        print(f"✅ Hash calculation: {hash_result[:16]}...")
    else:
        print("❌ Test image not found")

if __name__ == "__main__":
    test_visual_differ()
