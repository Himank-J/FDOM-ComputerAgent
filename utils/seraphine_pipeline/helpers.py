import os
import json
from functools import wraps

def load_configuration():
    """Load and validate configuration from config.json"""
    config_path = "utils/seraphine_pipeline/config.json"
    
    if not os.path.exists(config_path):
        print(f"Error: Configuration file '{config_path}' not found!")
        return None
    
    try:
        with open(config_path, "r") as f:
            config = json.load(f)
        return config
    except Exception as e:
        print(f"Error loading configuration: {e}")
        return None

def debug_only(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        config = load_configuration()
        if config and config.get("mode", "").lower() == "debug":
            return func(*args, **kwargs)
    return wrapper

@debug_only
def debug_print(*args, **kwargs):
    print(*args, **kwargs)