"""Data classes and type definitions for element interaction"""
from dataclasses import dataclass
from typing import Optional, List, Tuple, Dict


@dataclass
class ClickResult:
    """Result of clicking an element"""
    success: bool
    state_changed: bool
    new_state_id: Optional[str] = None
    error_message: Optional[str] = None
    screenshot_path: Optional[str] = None
    interaction_type: Optional[str] = None
    wait_time_used: Optional[float] = None
    hash_before: Optional[str] = None
    hash_after: Optional[str] = None
    after_screenshot: Optional[str] = None
    diff_result: Optional[Dict] = None


@dataclass
class BacktrackStrategy:
    """Strategy for returning to previous state"""
    method: str  # "close_icon", "same_location", "esc_key", "human_input"
    coordinates: Optional[Tuple[int, int]] = None
    special_keys: Optional[List[str]] = None
    success: bool = False
    attempts: int = 0
