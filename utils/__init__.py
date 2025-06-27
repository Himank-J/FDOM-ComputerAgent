import sys

# Expose the correct controller and manager based on the OS
if sys.platform == "win32":
    from .windowManager.window_manager import WindowManager
    from .windowManager.window_functions import WindowController
elif sys.platform == "darwin":
    from .macManager.mac_window_manager import MacWindowManager as WindowManager
    from .macManager.mac_window_functions import MacWindowController as WindowController
else:
    raise ImportError("Unsupported operating system")

__all__ = ['WindowManager', 'WindowController']
