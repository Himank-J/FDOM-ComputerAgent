import sys
import os

# Ensure the utility directory is in the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    # This will import the correct controller based on the OS
    from __init__ import WindowController
except ImportError as e:
    print(f"Error: {e}")
    sys.exit(1)

def main():
    """
    Initializes and runs the appropriate window controller for the current OS.
    """
    try:
        controller = WindowController()
        controller.run_interactive_mode()
    except Exception as e:
        print(f"Failed to start the window controller: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 