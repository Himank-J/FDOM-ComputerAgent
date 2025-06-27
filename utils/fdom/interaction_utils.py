"""Utility functions for element interaction"""
import os
from pathlib import Path
from typing import Dict, Optional, Tuple, List


def sanitize_app_name(app_name: str) -> str:
    """Convert app path to clean app name for folder/file operations"""
    if os.path.sep in app_name or app_name.endswith('.exe'):
        clean_name = Path(app_name).stem
    else:
        clean_name = app_name
    
    clean_name = clean_name.lower().replace(' ', '_').replace('-', '_')
    clean_name = clean_name.replace("++", "_plus_plus")
    
    # Remove common suffixes
    suffixes_to_remove = ["_setup", "_installer", "_x64", "_x86", "_win32", "_win64"]
    for suffix in suffixes_to_remove:
        if clean_name.endswith(suffix):
            clean_name = clean_name[:-len(suffix)]
            break
    
    # Remove problematic characters
    clean_name = ''.join(c for c in clean_name if c.isalnum() or c == '_')
    
    return clean_name


def sanitize_node_id_for_files(node_id: str) -> str:
    """Convert node ID to file-safe format"""
    return node_id.replace("::", "__").replace(":", "_").replace("/", "_").replace("\\", "_")
