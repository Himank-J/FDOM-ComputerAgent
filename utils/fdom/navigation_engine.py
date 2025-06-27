"""Navigation and backtracking strategies - Natural approach"""
import time
from typing import Dict, Optional, List, Tuple
from rich.console import Console
from pathlib import Path

from .interaction_types import BacktrackStrategy


class NavigationEngine:
    """Handles state navigation and natural backtracking strategies"""
    
    def __init__(self, app_controller, visual_differ, state_manager, element_interactor):
        self.app_controller = app_controller
        self.visual_differ = visual_differ
        self.state_manager = state_manager
        self.element_interactor = element_interactor
        self.console = Console()
        # ✅ Track navigation chain for backtracking
        self.navigation_chain = []  # [C1, C2, C3] in order of clicking
    
    def navigate_to_state(self, target_state: str, current_state: str) -> bool:
        """Enhanced navigation with MULTI-HOP support"""
        
        self.console.print(f"[cyan]🧭 NAVIGATION: {current_state} → {target_state}[/cyan]")
        
        # ✅ FIND NAVIGATION PATH using breadth-first search
        navigation_path = self._find_navigation_path(current_state, target_state)
        
        if not navigation_path:
            self.console.print(f"[red]❌ No navigation path found from {current_state} to {target_state}[/red]")
            return False
        
        self.console.print(f"[cyan]🗺️ Navigation path: {' → '.join(navigation_path)}[/cyan]")
        
        # ✅ EXECUTE MULTI-HOP NAVIGATION
        current = current_state
        for i in range(1, len(navigation_path)):
            next_state = navigation_path[i]
            
            self.console.print(f"[cyan]🚀 Step {i}: {current} → {next_state}[/cyan]")
            
            if not self._execute_single_hop(current, next_state):
                self.console.print(f"[red]❌ Failed at step {i}: {current} → {next_state}[/red]")
                return False
            
            current = next_state
            self.element_interactor.current_state_id = current
            
            # Wait for UI transition
            time.sleep(1)
        
        self.console.print(f"[green]✅ Multi-hop navigation successful: {current_state} → {target_state}[/green]")
        return True
    
    def _find_navigation_path(self, start_state: str, target_state: str) -> List[str]:
        """Find shortest path between states using BFS"""
        if start_state == target_state:
            return [start_state]
        
        # Build graph from edges
        graph = {}
        edges = self.state_manager.fdom_data.get("edges", [])
        
        for edge in edges:
            from_state = edge.get("from")
            to_state = edge.get("to")
            if from_state and to_state:
                if from_state not in graph:
                    graph[from_state] = []
                graph[from_state].append(to_state)
        
        # BFS to find shortest path
        from collections import deque
        
        queue = deque([(start_state, [start_state])])
        visited = {start_state}
        
        while queue:
            current_state, path = queue.popleft()
            
            if current_state == target_state:
                return path
            
            for neighbor in graph.get(current_state, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))
        
        return []  # No path found
    
    def _execute_single_hop(self, from_state: str, to_state: str) -> bool:
        """Execute single navigation hop (original logic)"""
        # Find the edge that leads to to_state
        edges = self.state_manager.fdom_data.get("edges", [])
        target_edge = None
        
        for edge in edges:
            if edge.get("from") == from_state and edge.get("to") == to_state:
                target_edge = edge
                break
        
        if not target_edge:
            self.console.print(f"[red]❌ No edge found: {from_state} → {to_state}[/red]")
            return False
        
        # Extract and execute trigger node (existing logic)
        action = target_edge.get("action", "")
        if not action.startswith("click:"):
            self.console.print(f"[red]❌ Invalid action format: {action}[/red]")
            return False
        
        trigger_node_id = action.split(":", 1)[1]
        if "::" in trigger_node_id:
            clean_trigger_id = trigger_node_id.split("::", 1)[1]
        else:
            clean_trigger_id = trigger_node_id
        
        # Find trigger node in from_state
        from_state_data = self.state_manager.fdom_data["states"].get(from_state, {})
        trigger_node = from_state_data.get("nodes", {}).get(clean_trigger_id)
        
        if not trigger_node:
            self.console.print(f"[red]❌ Trigger node {clean_trigger_id} not found in {from_state}[/red]")
            return False
        
        # Execute click
        window_pos = self.element_interactor._get_current_window_position()
        if not window_pos:
            return False
        
        source_element_name = trigger_node.get('g_icon_name', 'unknown')
        
        # Track navigation
        nav_info = {
            'node_id': clean_trigger_id,
            'node_data': trigger_node,
            'element_name': source_element_name,
            'from_state': from_state,
            'to_state': to_state
        }
        self.navigation_chain.append(nav_info)
        
        click_result = self.element_interactor.click_engine.execute_click_with_centroids(
            trigger_node, window_pos, source_element_name
        )
        
        if click_result.success:
            self.console.print(f"[green]✅ Single hop successful: {from_state} → {to_state}[/green]")
            return True
        else:
            self.navigation_chain.pop()
            self.console.print(f"[red]❌ Single hop failed: {click_result.error_message}[/red]")
            return False
    
    def navigate_back_to_state(self, target_state_id: str, failure_reference_screenshot: str = None) -> bool:
        """NATURAL BACKTRACKING: 4-step strategy based on visual cues"""
        
        self.console.print(f"[bold blue]🔄 NATURAL BACKTRACKING to {target_state_id}[/bold blue]")
        self.console.print(f"[cyan]🔗 Navigation chain: {len(self.navigation_chain)} steps[/cyan]")
        
        # ✅ STRATEGY 1: Look for close buttons in current state
        if self._try_close_button_strategy():
            if self._verify_reached_target(target_state_id):
                return True
        
        # ✅ STRATEGY 2: Try ESC key
        if self._try_esc_key_strategy():
            if self._verify_reached_target(target_state_id):
                return True
        
        # ✅ STRATEGY 3: Try clicking previous navigation elements (C2, C1...)
        if self._try_reverse_navigation_chain():
            if self._verify_reached_target(target_state_id):
                return True
        
        # ✅ STRATEGY 4: Ask human
        return self._try_human_input_strategy(target_state_id)
    
    def _try_close_button_strategy(self) -> bool:
        """STRATEGY 1: Look for close/cancel/x buttons in current state"""
        self.console.print(f"[yellow]🔧 Strategy 1: Looking for close buttons...[/yellow]")
        
        current_state_data = self.state_manager.fdom_data["states"].get(self.element_interactor.current_state_id, {})
        current_nodes = current_state_data.get("nodes", {})
        
        # Look for close-related elements
        close_keywords = ["close", "cancel", "x", "✕", "×", "ok", "done", "finish"]
        
        for node_id, node_data in current_nodes.items():
            element_name = node_data.get('g_icon_name', '').lower()
            
            for keyword in close_keywords:
                if keyword in element_name:
                    self.console.print(f"[green]✅ Found close button: {element_name}[/green]")
                    
                    # Try clicking it
                    window_pos = self.element_interactor._get_current_window_position()
                    if window_pos:
                        click_result = self.element_interactor.click_engine.execute_click_with_centroids(
                            node_data, window_pos, element_name
                        )
                        
                        if click_result.success:
                            self.console.print(f"[green]🎉 Close button clicked successfully![/green]")
                            time.sleep(1)  # Wait for close animation
                            return True
        
        self.console.print(f"[yellow]⚠️ No close buttons found[/yellow]")
        return False
    
    def _try_esc_key_strategy(self) -> bool:
        """STRATEGY 2: Try ESC key"""
        self.console.print(f"[yellow]🔧 Strategy 2: Trying ESC key...[/yellow]")
        
        try:
            success = self.app_controller.gui_api.send_esc_enhanced()
            
            if success:
                self.console.print(f"[green]✅ ESC key sent successfully[/green]")
                time.sleep(1)
                return True
            else:
                self.console.print(f"[yellow]⚠️ ESC key failed[/yellow]")
                return False
                
        except Exception as e:
            self.console.print(f"[red]❌ ESC strategy failed: {e}[/red]")
            return False
    
    def _try_reverse_navigation_chain(self) -> bool:
        """STRATEGY 3: Try clicking previous navigation elements in reverse order"""
        self.console.print(f"[yellow]🔧 Strategy 3: Trying reverse navigation chain...[/yellow]")
        
        if not self.navigation_chain:
            self.console.print(f"[yellow]⚠️ No navigation chain to reverse[/yellow]")
            return False
        
        # Try in reverse order: C3 → C2 → C1
        for i in range(len(self.navigation_chain) - 1, -1, -1):
            nav_step = self.navigation_chain[i]
            
            self.console.print(f"[cyan]🔄 Trying to click: {nav_step['element_name']} (step {i+1})[/cyan]")
            
            # Check if this element is still visible in current state
            current_state_data = self.state_manager.fdom_data["states"].get(self.element_interactor.current_state_id, {})
            current_nodes = current_state_data.get("nodes", {})
            
            if nav_step['node_id'] in current_nodes:
                # Element still visible, try clicking it
                window_pos = self.element_interactor._get_current_window_position()
                if window_pos:
                    click_result = self.element_interactor.click_engine.execute_click_with_centroids(
                        nav_step['node_data'], window_pos, nav_step['element_name']
                    )
                    
                    if click_result.success:
                        self.console.print(f"[green]✅ Reverse navigation successful: {nav_step['element_name']}[/green]")
                        time.sleep(1)
                        # Remove this and subsequent steps from chain
                        self.navigation_chain = self.navigation_chain[:i]
                        return True
            else:
                self.console.print(f"[dim]⚠️ Element {nav_step['element_name']} no longer visible[/dim]")
        
        self.console.print(f"[yellow]⚠️ Reverse navigation chain failed[/yellow]")
        return False
    
    def _try_human_input_strategy(self, target_state_id: str) -> bool:
        """STRATEGY 6: Ask human for assistance with timeout and auto-restart fallback"""
        self.console.print(f"[bold red]🤝 Strategy 6: Human assistance needed[/bold red]")
        
        from rich.prompt import Prompt
        import threading
        import signal
        
        current_state = self.element_interactor.current_state_id
        self.console.print(f"[yellow]Current state: {current_state}[/yellow]")
        self.console.print(f"[yellow]Target state: {target_state_id}[/yellow]")
        
        # Check for learned strategy first
        learned_strategy = self._get_learned_exit_strategy(current_state, target_state_id)
        if learned_strategy:
            self.console.print(f"[cyan]🧠 Found learned exit strategy for {current_state} → {target_state_id}[/cyan]")
            if self._execute_learned_exit_strategy(learned_strategy):
                return True
            else:
                self.console.print(f"[yellow]⚠️ Learned strategy failed, falling back to human help[/yellow]")
        
        self.console.print(f"[bold yellow]📍 CLICK RECORDING ACTIVE - Your clicks will be learned for future automation[/bold yellow]")
        
        before_screenshot = self.element_interactor.screenshot_manager.take_screenshot("before_human_help")
        
        # ✅ FIX: Add fallback learning when click monitoring fails
        click_monitor = self._start_click_monitoring()
        if not click_monitor:
            self.console.print(f"[yellow]⚠️ Click monitoring failed - will use manual learning fallback[/yellow]")
        
        # ✅ NEW: Add timeout mechanism
        self.console.print(f"[bold yellow]⏰ Please help navigate back manually within 10 seconds, then press Enter[/bold yellow]")
        self.console.print(f"[dim]If no response in 10 seconds, will auto-restart with default file[/dim]")
        
        try:
            # ✅ TIMEOUT: 10-second timeout using threading
            user_response = None
            response_received = threading.Event()
            
            def get_user_input():
                nonlocal user_response
                try:
                    user_response = input("Press Enter when you've navigated back (or 'skip' to abort): ")
                    response_received.set()
                except:
                    pass
            
            input_thread = threading.Thread(target=get_user_input, daemon=True)
            input_thread.start()
            
            # Wait for user input or timeout
            if response_received.wait(timeout=10.0):
                # User responded within 10 seconds
                if user_response and user_response.lower() == 'skip':
                    return False
                
                # ✅ EXISTING: Continue with click learning logic
                recorded_clicks = self._stop_click_monitoring(click_monitor) if click_monitor else []
                
                if recorded_clicks:
                    self._learn_exit_strategy_from_clicks(current_state, target_state_id, recorded_clicks, before_screenshot)
                else:
                    self._save_learned_exit_strategy(current_state, target_state_id, {
                        "method": "manual_navigation",
                        "learned_from": "human_assistance_fallback",
                        "success_rate": 1.0,
                        "last_used": time.time(),
                        "note": "Click monitoring failed, but human successfully navigated"
                    })
                    self.console.print(f"[green]✅ Saved manual navigation strategy as fallback[/green]")
                
                self.navigation_chain.clear()
                return True
            
            else:
                # ✅ TIMEOUT: No response within 10 seconds - auto-restart
                self.console.print(f"[red]⏰ No human response within 10 seconds - auto-restarting application[/red]")
                
                # Stop click monitoring
                if click_monitor:
                    self._stop_click_monitoring(click_monitor)
                
                # ✅ CALL: The auto-restart function
                restart_success = self._auto_restart_with_default_file()
                
                if restart_success:
                    self.console.print(f"[green]✅ Application restarted successfully - continuing exploration[/green]")
                    return True
                else:
                    self.console.print(f"[red]❌ Auto-restart failed - manual intervention required[/red]")
                    return False
                    
        except Exception as e:
            self.console.print(f"[red]❌ Error in human input strategy: {e}[/red]")
            return False

    def _get_learned_exit_strategy(self, from_state: str, to_state: str) -> Optional[Dict]:
        """Get previously learned exit strategy for this state transition"""
        try:
            current_state_data = self.state_manager.fdom_data["states"].get(from_state, {})
            exit_strategies = current_state_data.get("exit_strategies", {})
            
            # Look for exact target match first
            if to_state in exit_strategies:
                strategy = exit_strategies[to_state]
                self.console.print(f"[cyan]🎯 Found exact exit strategy: {from_state} → {to_state}[/cyan]")
                return strategy
            
            # Look for generic "root" strategy if target is root
            if to_state == "root" and "root" in exit_strategies:
                strategy = exit_strategies["root"]
                self.console.print(f"[cyan]🏠 Found root exit strategy: {from_state} → root[/cyan]")
                return strategy
            
            return None
            
        except Exception as e:
            self.console.print(f"[yellow]⚠️ Error getting learned strategy: {e}[/yellow]")
            return None

    def _execute_learned_exit_strategy(self, strategy: Dict) -> bool:
        """Execute a previously learned exit strategy"""
        try:
            method = strategy.get("method")
            
            if method == "click_element":
                # Execute click on learned element
                node_id = strategy.get("node_id")
                element_name = strategy.get("element_name", "learned_element")
                
                self.console.print(f"[cyan]🤖 Executing learned strategy: clicking {element_name} ({node_id})[/cyan]")
                
                # Find the element in current state
                current_state_data = self.state_manager.fdom_data["states"].get(
                    self.element_interactor.current_state_id, {}
                )
                current_nodes = current_state_data.get("nodes", {})
                
                if node_id in current_nodes:
                    window_pos = self.element_interactor._get_current_window_position()
                    if window_pos:
                        click_result = self.element_interactor.click_engine.execute_click_with_centroids(
                            current_nodes[node_id], window_pos, element_name
                        )
                        
                        if click_result.success:
                            self.console.print(f"[green]✅ Learned strategy executed successfully[/green]")
                            time.sleep(1)
                            return True
                        else:
                            self.console.print(f"[yellow]⚠️ Learned click failed: {click_result.error_message}[/yellow]")
                else:
                    self.console.print(f"[yellow]⚠️ Learned element {node_id} not found in current state[/yellow]")
            
            elif method == "key_sequence":
                # Execute learned key sequence (like ESC)
                keys = strategy.get("keys", [])
                self.console.print(f"[cyan]🤖 Executing learned key sequence: {keys}[/cyan]")
                
                for key in keys:
                    if key == "ESC":
                        self.app_controller.gui_api.send_key("ESCAPE")
                        time.sleep(0.5)
                
                return True
            
            return False
            
        except Exception as e:
            self.console.print(f"[red]❌ Error executing learned strategy: {e}[/red]")
            return False

    def _start_click_monitoring(self):
        """Start monitoring mouse clicks using Windows API"""
        try:
            import threading
            from ctypes import wintypes
            import ctypes
            
            # Storage for recorded clicks
            self.recorded_clicks = []
            self.monitoring_active = True
            
            # Windows hook setup
            WH_MOUSE_LL = 14
            WM_LBUTTONDOWN = 0x0201
            
            class POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
            
            class MSLLHOOKSTRUCT(ctypes.Structure):
                _fields_ = [("pt", POINT), ("mouseData", wintypes.DWORD),
                           ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                           ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))]
            
            def low_level_mouse_proc(nCode, wParam, lParam):
                if nCode >= 0 and self.monitoring_active:
                    if wParam == WM_LBUTTONDOWN:
                        # Record the click
                        info = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                        click_x = info.pt.x
                        click_y = info.pt.y
                        
                        self.recorded_clicks.append({
                            'x': click_x,
                            'y': click_y,
                            'timestamp': time.time()
                        })
                        
                        self.console.print(f"[dim]📍 Recorded click at ({click_x}, {click_y})[/dim]")
                
                return ctypes.windll.user32.CallNextHookExW(None, nCode, wParam, lParam)
            
            # Set up the hook
            HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
            self.hook_proc = HOOKPROC(low_level_mouse_proc)
            
            self.hook_id = ctypes.windll.user32.SetWindowsHookExW(
                WH_MOUSE_LL, self.hook_proc, 
                ctypes.windll.kernel32.GetModuleHandleW(None), 0
            )
            
            if not self.hook_id:
                self.console.print(f"[yellow]⚠️ Failed to set up click monitoring[/yellow]")
                return None
            
            return self.hook_id
            
        except Exception as e:
            self.console.print(f"[yellow]⚠️ Click monitoring setup failed: {e}[/yellow]")
            return None

    def _stop_click_monitoring(self, hook_id):
        """Stop click monitoring and return recorded clicks"""
        try:
            self.monitoring_active = False
            
            if hook_id:
                import ctypes
                ctypes.windll.user32.UnhookWindowsHookEx(hook_id)
            
            recorded_clicks = getattr(self, 'recorded_clicks', [])
            self.console.print(f"[cyan]📊 Recorded {len(recorded_clicks)} clicks during human assistance[/cyan]")
            
            return recorded_clicks
            
        except Exception as e:
            self.console.print(f"[yellow]⚠️ Error stopping click monitoring: {e}[/yellow]")
            return []

    def _learn_exit_strategy_from_clicks(self, from_state: str, to_state: str, 
                                       recorded_clicks: List[Dict], before_screenshot: str):
        """Analyze recorded clicks and learn exit strategy"""
        try:
            if not recorded_clicks:
                self.console.print(f"[yellow]⚠️ No clicks recorded - cannot learn strategy[/yellow]")
                return
            
            # Take "after" screenshot to verify the transition worked
            after_screenshot = self.element_interactor.screenshot_manager.take_screenshot("after_human_help")
            
            # Get window position for coordinate conversion
            window_pos = self.element_interactor._get_current_window_position()
            if not window_pos:
                self.console.print(f"[yellow]⚠️ Cannot get window position for learning[/yellow]")
                return
            
            self.console.print(f"[cyan]🧠 Learning exit strategy from {len(recorded_clicks)} clicks...[/cyan]")
            
            # Process the most significant click (usually the last one that caused the transition)
            significant_click = recorded_clicks[-1]  # Last click is usually the important one
            
            # Convert absolute coordinates to window-relative coordinates
            window_rel_x = significant_click['x'] - window_pos['left']
            window_rel_y = significant_click['y'] - window_pos['top']
            
            # Find matching FDOM element at these coordinates
            matching_element = self._find_element_at_coordinates(from_state, window_rel_x, window_rel_y)
            
            if matching_element:
                # Save as learned click strategy
                self._save_learned_exit_strategy(from_state, to_state, {
                    "method": "click_element",
                    "node_id": matching_element['node_id'],
                    "element_name": matching_element['element_name'],
                    "coordinates": [window_rel_x, window_rel_y],
                    "learned_from": "human_assistance",
                    "success_rate": 1.0,
                    "last_used": time.time()
                })
                
                self.console.print(f"[green]✅ Learned exit strategy: {from_state} → {to_state} via '{matching_element['element_name']}'[/green]")
            else:
                # Could be a key press or gesture - save coordinates as fallback
                self._save_learned_exit_strategy(from_state, to_state, {
                    "method": "click_coordinates",
                    "coordinates": [window_rel_x, window_rel_y],
                    "learned_from": "human_assistance",
                    "success_rate": 1.0,
                    "last_used": time.time()
                })
                
                self.console.print(f"[green]✅ Learned coordinate-based exit strategy: {from_state} → {to_state} at ({window_rel_x}, {window_rel_y})[/green]")
            
        except Exception as e:
            self.console.print(f"[red]❌ Error learning from clicks: {e}[/red]")

    def _find_element_at_coordinates(self, state_id: str, rel_x: int, rel_y: int) -> Optional[Dict]:
        """Find FDOM element that contains the given coordinates"""
        try:
            state_data = self.state_manager.fdom_data["states"].get(state_id, {})
            nodes = state_data.get("nodes", {})
            
            # Search for element containing these coordinates
            for node_id, node_data in nodes.items():
                bbox = node_data.get("bbox", [])
                if len(bbox) == 4:
                    x1, y1, x2, y2 = bbox
                    
                    # Check if coordinates are within this element (with small tolerance)
                    if (x1 - 5 <= rel_x <= x2 + 5 and 
                        y1 - 5 <= rel_y <= y2 + 5):
                        
                        element_name = node_data.get('g_icon_name', 'unknown')
                        return {
                            'node_id': node_id,
                            'element_name': element_name,
                            'bbox': bbox
                        }
            
            return None
            
        except Exception as e:
            self.console.print(f"[yellow]⚠️ Error finding element at coordinates: {e}[/yellow]")
            return None

    def _save_learned_exit_strategy(self, from_state: str, to_state: str, strategy: Dict):
        """Save learned exit strategy to FDOM data"""
        try:
            # Get current FDOM data
            fdom_data = self.state_manager.fdom_data
            
            # Ensure the from_state exists
            if from_state not in fdom_data.get("states", {}):
                self.console.print(f"[yellow]⚠️ State {from_state} not found in FDOM[/yellow]")
                return
            
            # Initialize exit_strategies if not exists
            state_data = fdom_data["states"][from_state]
            if "exit_strategies" not in state_data:
                state_data["exit_strategies"] = {}
            
            # Save the strategy
            state_data["exit_strategies"][to_state] = strategy
            
            # Save to file
            self.state_manager.save_fdom_to_file()
            
            self.console.print(f"[green]✅ Exit strategy saved to FDOM: {from_state} → {to_state}[/green]")
            
        except Exception as e:
            self.console.print(f"[red]❌ Error saving learned strategy: {e}[/red]")
    
    def _verify_reached_target(self, target_state_id: str) -> bool:
        """Verify if we've reached the target state with PROPER comparison"""
        # Take screenshot and compare with known state
        verification_screenshot = self.element_interactor.screenshot_manager.take_screenshot("verification")
        
        if target_state_id == "root":
            # Compare with root state screenshot
            root_state_data = self.state_manager.fdom_data["states"].get("root", {})
            root_image = root_state_data.get("image")
            
            if root_image and Path(root_image).exists():
                hash1 = self.visual_differ.calculate_image_hash(verification_screenshot)
                hash2 = self.visual_differ.calculate_image_hash(root_image)
                
                if hash1 == hash2:
                    self.console.print(f"[green]✅ Backtrack verification: Successfully reached {target_state_id}[/green]")
                    self.element_interactor.current_state_id = target_state_id
                    return True
                else:
                    self.console.print(f"[yellow]⚠️ Backtrack verification: State mismatch for {target_state_id}[/yellow]")
                    return False
            else:
                # Fallback for missing root image
                self.console.print(f"[yellow]⚠️ Backtrack verification: No reference image for {target_state_id}[/yellow]")
                self.element_interactor.current_state_id = target_state_id
                return True
        
        # For other states, similar comparison
        return True
    
    def smart_backtrack_to_state(self, target_state: str, reference_screenshot: str) -> bool:
        """Smart backtracking with ESSENTIAL first check"""
        
        self.console.print(f"[bold blue]🔄 SMART BACKTRACKING to {target_state}[/bold blue]")
        self.console.print(f"[dim]📸 Reference screenshot: {reference_screenshot}[/dim]")
        
        # ✅ STEP 0: Are we ALREADY in the target state? (MOST IMPORTANT CHECK!)
        target_state_screenshot = self._get_target_state_screenshot(target_state)
        if target_state_screenshot:
            current_screenshot = self.element_interactor.screenshot_manager.take_screenshot("backtrack_current_check")
            current_similarity = self.visual_differ.calculate_similarity_percentage(
                current_screenshot, target_state_screenshot)
        else:
            # Fallback logic
            current_similarity = 0.0
        
        self.console.print(f"[cyan]🎯 STEP 0: Current vs target similarity: {current_similarity}%[/cyan]")
        
        if current_similarity >= 99.9:
            self.console.print(f"[green]✅ ALREADY IN TARGET STATE! No backtracking needed ({current_similarity}%)[/green]")
            return True
        
        self.console.print(f"[yellow]⚠️ Need to backtrack: {current_similarity}% < 99.9%[/yellow]")
        
        # Store reference for other strategies
        self.backtrack_reference = reference_screenshot
        current_state = self.element_interactor.current_state_id
        
        # ✅ STEP 1: Try learned strategy first
        learned_strategy = self._get_learned_exit_strategy(current_state, target_state)
        if learned_strategy:
            self.console.print(f"[cyan]🧠 Found learned exit strategy for {current_state} → {target_state}[/cyan]")
            if self._execute_learned_exit_strategy(learned_strategy):
                if self._verify_reached_target_with_reference(target_state):
                    return True
        
        # ✅ STRATEGY 1: Click outside diff area (safest)
        if self._try_click_outside_diff_strategy(reference_screenshot):
            if self._verify_reached_target_with_reference(target_state):
                # ✅ SAVE successful safe area strategy
                self._save_successful_backtrack_strategy(current_state, target_state, "safe_area_click")
                return True
        
        # ✅ STRATEGY 2: Click same button that opened this state
        if self._try_click_same_opener_button():
            if self._check_app_and_restart_if_needed():
                if self._verify_reached_target_with_reference(target_state):
                    # ✅ SAVE successful opener button strategy
                    self._save_successful_backtrack_strategy(current_state, target_state, "opener_button")
                    return True
        
        # ✅ STRATEGY 3: Press ESC key
        if self._try_esc_key_strategy():
            if self._check_app_and_restart_if_needed():
                if self._verify_reached_target_with_reference(target_state):
                    # ✅ SAVE successful ESC strategy
                    self._save_successful_backtrack_strategy(current_state, target_state, "esc_key")
                    return True
        
        # ✅ STRATEGY 4: Look for close button (with app restart)
        if self._try_close_button_strategy_fixed():
            if self._check_app_and_restart_if_needed():
                if self._verify_reached_target_with_reference(target_state):
                    # ✅ SAVE successful close button strategy
                    self._save_successful_backtrack_strategy(current_state, target_state, "close_button")
                    return True
        
        # ✅ STRATEGY 5: Reverse navigation chain
        if self._try_reverse_navigation_chain():
            if self._check_app_and_restart_if_needed():
                if self._verify_reached_target_with_reference(target_state):
                    # ✅ SAVE successful reverse navigation strategy
                    self._save_successful_backtrack_strategy(current_state, target_state, "reverse_navigation")
                    return True
        
        # ✅ STRATEGY 6: Ask user (already has learning built-in)
        if self._try_human_input_strategy(target_state):
            return True
        
        self.console.print(f"[red]❌ All backtrack strategies failed[/red]")
        return False

    def _save_successful_backtrack_strategy(self, from_state: str, to_state: str, method: str):
        """Save automatically discovered successful backtrack strategy"""
        try:
            # Create strategy object based on method
            if method == "esc_key":
                strategy = {
                    "method": "key_sequence",
                    "keys": ["ESC"],
                    "learned_from": "automatic_discovery",
                    "success_rate": 1.0,
                    "last_used": time.time(),
                    "discovery_method": method
                }
            elif method == "safe_area_click":
                # Save the last successful safe area click coordinates
                if hasattr(self, '_last_successful_safe_click'):
                    strategy = {
                        "method": "click_coordinates",
                        "coordinates": self._last_successful_safe_click,
                        "learned_from": "automatic_discovery",
                        "success_rate": 1.0,
                        "last_used": time.time(),
                        "discovery_method": method
                    }
                else:
                    return  # No coordinates to save
            elif method == "opener_button":
                # Save the opener button information
                if self.navigation_chain:
                    last_step = self.navigation_chain[-1]
                    strategy = {
                        "method": "click_element",
                        "node_id": last_step['node_id'],
                        "element_name": last_step['element_name'],
                        "learned_from": "automatic_discovery",
                        "success_rate": 1.0,
                        "last_used": time.time(),
                        "discovery_method": method
                    }
                else:
                    return  # No navigation chain info
            elif method == "close_button":
                # Save the last successful close button
                if hasattr(self, '_last_successful_close_button'):
                    strategy = {
                        "method": "click_element",
                        "node_id": self._last_successful_close_button['node_id'],
                        "element_name": self._last_successful_close_button['element_name'],
                        "learned_from": "automatic_discovery",
                        "success_rate": 1.0,
                        "last_used": time.time(),
                        "discovery_method": method
                    }
                else:
                    return  # No close button info
            elif method == "reverse_navigation":
                # Save reverse navigation strategy
                strategy = {
                    "method": "reverse_navigation_chain",
                    "learned_from": "automatic_discovery",
                    "success_rate": 1.0,
                    "last_used": time.time(),
                    "discovery_method": method
                }
            else:
                return  # Unknown method
            
            # Save using existing method
            self._save_learned_exit_strategy(from_state, to_state, strategy)
            
            self.console.print(f"[green]🧠 Auto-learned exit strategy: {from_state} → {to_state} via {method}[/green]")
            
        except Exception as e:
            self.console.print(f"[yellow]⚠️ Error saving successful strategy: {e}[/yellow]")

    def _try_click_outside_diff_strategy(self, reference_screenshot: str) -> bool:
        """STRATEGY 1: Click in SAFE areas that don't overlap with UI elements"""
        self.console.print(f"[yellow]🔧 Strategy 1: Finding safe click areas...[/yellow]")
        
        try:
            window_pos = self.element_interactor._get_current_window_position()
            if not window_pos:
                return False
            
            safe_areas = self._find_safe_click_areas(window_pos)
            
            if not safe_areas:
                self.console.print(f"[red]❌ No safe areas found[/red]")
                return False
            
            self.console.print(f"[cyan]🎯 Found {len(safe_areas)} safe areas[/cyan]")
            
            for i, (safe_x, safe_y) in enumerate(safe_areas[:3]):
                before_click_screenshot = self.element_interactor.screenshot_manager.take_screenshot("before_safe_click")
                
                self.app_controller.gui_api.click(safe_x, safe_y)
                self.console.print(f"[green]✅ Clicked SAFE area #{i+1} at ({safe_x}, {safe_y})[/green]")
                time.sleep(1)
                
                after_click_screenshot = self.element_interactor.screenshot_manager.take_screenshot("after_safe_click")
                reference_similarity = self.visual_differ.calculate_similarity_percentage(after_click_screenshot, reference_screenshot)
                
                # ✅ FIX: Use same 99.0% threshold here too
                if reference_similarity >= 99.0:
                    self.console.print(f"[green]🎉 Safe area click successful - reached target state! (similarity: {reference_similarity}%)[/green]")
                    
                    # Save successful coordinates for learning
                    window_rel_x = safe_x - window_pos['left']
                    window_rel_y = safe_y - window_pos['top']
                    self._last_successful_safe_click = [window_rel_x, window_rel_y]
                    
                    return True
                else:
                    self.console.print(f"[yellow]⚠️ Safe area #{i+1} didn't reach target (similarity: {reference_similarity}%)[/yellow]")
            
            return False
            
        except Exception as e:
            self.console.print(f"[red]❌ Safe area click strategy failed: {e}[/red]")
            return False

    def _try_click_same_opener_button(self) -> bool:
        """STRATEGY 2: Click the same button that opened this state"""
        self.console.print(f"[yellow]🔧 Strategy 2: Clicking same opener button...[/yellow]")
        
        if not self.navigation_chain:
            self.console.print(f"[yellow]⚠️ No navigation chain to find opener button[/yellow]")
            return False
        
        # Get the last navigation step (what opened current state)
        last_step = self.navigation_chain[-1]
        opener_element = last_step['element_name']
        opener_node_id = last_step['node_id']
        
        self.console.print(f"[cyan]🔄 Trying to click opener: {opener_element}[/cyan]")
        
        # Find this element in root state (assuming it's still there)
        root_state_data = self.state_manager.fdom_data["states"].get("root", {})
        root_nodes = root_state_data.get("nodes", {})
        
        if opener_node_id in root_nodes:
            window_pos = self.element_interactor._get_current_window_position()
            if window_pos:
                click_result = self.element_interactor.click_engine.execute_click_with_centroids(
                    root_nodes[opener_node_id], window_pos, opener_element
                )
                
                if click_result.success:
                    self.console.print(f"[green]✅ Opener button clicked successfully[/green]")
                    time.sleep(1)
                    return True
        
        self.console.print(f"[yellow]⚠️ Could not find or click opener button[/yellow]")
        return False
    
    def _try_close_button_strategy_fixed(self) -> bool:
        """STRATEGY 4: Look for close buttons ONLY from recently created dialog elements"""
        self.console.print(f"[yellow]🔧 Strategy 4: Looking for DIALOG-SPECIFIC close buttons...[/yellow]")
        
        current_state_data = self.state_manager.fdom_data["states"].get(self.element_interactor.current_state_id, {})
        current_nodes = current_state_data.get("nodes", {})
        
        # ✅ ENHANCED: Find close buttons but filter out global/app-level ones
        import re
        close_keywords = ["close", "cancel", "✕", "×", "ok", "done", "finish"]
        
        close_buttons = []
        
        for node_id, node_data in current_nodes.items():
            element_name = node_data.get('g_icon_name', '').lower()
            element_bbox = node_data.get('bbox', [])
            
            # ✅ FILTER: Skip elements that are likely global app controls
            if self._is_likely_global_control(element_name, element_bbox):
                self.console.print(f"[dim]🚫 Skipping likely global control: {element_name}[/dim]")
                continue
            
            for keyword in close_keywords:
                # Only exact "x" matches (avoid substring matching issues) 
                if keyword == "x" and element_name.strip() == "x":
                    close_buttons.append({
                        'node_id': node_id,
                        'node_data': node_data,
                        'element_name': element_name,
                        'keyword': keyword
                    })
                    break
                elif keyword != "x" and re.search(r'\b' + re.escape(keyword) + r'\b', element_name):
                    close_buttons.append({
                        'node_id': node_id,
                        'node_data': node_data,
                        'element_name': element_name,
                        'keyword': keyword
                    })
                    break
        
        if not close_buttons:
            self.console.print(f"[yellow]⚠️ No close buttons found[/yellow]")
            return False
        
        self.console.print(f"[cyan]🎯 Found {len(close_buttons)} close button(s): {[btn['element_name'] for btn in close_buttons]}[/cyan]")
        
        # ✅ ENHANCED: Try ALL close buttons until one works
        for i, button in enumerate(close_buttons, 1):
            self.console.print(f"[cyan]🔘 Trying close button #{i}: {button['element_name']}[/cyan]")
            
            window_pos = self.element_interactor._get_current_window_position()
            if window_pos:
                click_result = self.element_interactor.click_engine.execute_click_with_centroids(
                    button['node_data'], window_pos, button['element_name']
                )
                
                if click_result.success:
                    self.console.print(f"[green]🎉 Close button #{i} clicked successfully: {button['element_name']}![/green]")
                    
                    # ✅ SAVE successful close button for learning
                    self._last_successful_close_button = {
                        'node_id': button['node_id'],
                        'element_name': button['element_name']
                    }
                    
                    time.sleep(1)  # Wait for close animation
                    return True
                else:
                    self.console.print(f"[yellow]⚠️ Close button #{i} click failed: {click_result.error_message}[/yellow]")
        
        self.console.print(f"[red]❌ All {len(close_buttons)} close buttons failed[/red]")
        return False
    
    def _check_app_and_restart_if_needed(self) -> bool:
        """Check if app is still running and restart if needed"""
        if not self._verify_app_still_running():
            self.console.print(f"[yellow]⚠️ App closed during backtrack - restarting...[/yellow]")
            restart_success = self._restart_app_after_closure()
            
            if restart_success:
                self.console.print(f"[green]✅ App restarted successfully[/green]")
                return True
            else:
                self.console.print(f"[red]❌ Failed to restart app[/red]")
                return False
        
        return True  # App still running
    
    def _verify_app_still_running(self) -> bool:
        """Check if the app window still exists"""
        try:
            if not self.app_controller.current_app_info:
                return False
            
            window_id = self.app_controller.current_app_info['window_id']
            window_info = self.app_controller.gui_api.get_window_info(window_id)
            
            return window_info is not None
            
        except Exception as e:
            self.console.print(f"[yellow]⚠️ Error checking app status: {e}[/yellow]")
            return False
    
    def _restart_app_after_closure(self) -> bool:
        """Restart the app without running Seraphine (fDOM already exists)"""
        try:
            # Get original app path from element_interactor
            app_path = self.element_interactor.app_executable_path
            
            self.console.print(f"[cyan]🔄 Restarting app: {app_path}[/cyan]")
            
            # Use AppController to relaunch
            launch_result = self.app_controller.launch_app()
            
            if launch_result["success"]:
                self.console.print(f"[green]✅ App relaunched successfully[/green]")
                
                # Wait for app to be ready
                time.sleep(2)
                
                # Verify window tracking
                return self._verify_app_still_running()
            else:
                self.console.print(f"[red]❌ App relaunch failed: {launch_result.get('error')}[/red]")
                return False
                
        except Exception as e:
            self.console.print(f"[red]❌ Exception during app restart: {e}[/red]")
            return False
    
    def _verify_reached_target_with_reference(self, target_state_id: str) -> bool:
        """ENHANCED: Multi-state verification for popup behavior"""
        verification_screenshot = self.element_interactor.screenshot_manager.take_screenshot("verification")
        
        if target_state_id == "root":
            # ✅ MULTI-STATE VERIFICATION: Check against ALL possible target states
            candidate_references = []
            
            # 1. Add the backtrack reference (before_click - might be C4, C3, C2, C1)
            if hasattr(self, 'backtrack_reference') and self.backtrack_reference:
                candidate_references.append(("before_click", self.backtrack_reference))
            
            # 2. Add ROOT state image (S001.png)
            root_state_data = self.state_manager.fdom_data["states"].get("root", {})
            root_image = root_state_data.get("image")
            if root_image and Path(root_image).exists():
                candidate_references.append(("root_state", root_image))
            
            for nav_step in self.navigation_chain:
                state_id = nav_step.get('from_state')
                if state_id and state_id in self.state_manager.fdom_data.get("states", {}):
                    state_image = self.state_manager.fdom_data["states"][state_id].get("image")
                    if state_image and Path(state_image).exists():
                        candidate_references.append((f"nav_state_{state_id}", state_image))
            
            self.console.print(f"[cyan]🎯 Multi-state verification: {len(candidate_references)} candidates[/cyan]")
            
            # ✅ FIX: More reasonable threshold (99.0% instead of 99.99%)
            for ref_name, ref_path in candidate_references:
                similarity = self.visual_differ.calculate_similarity_percentage(
                    verification_screenshot, ref_path
                )
                
                self.console.print(f"[dim]📊 {ref_name}: {similarity}%[/dim]")
                
                # ✅ REASONABLE: 99.0% threshold (not 99.99%)
                if similarity >= 99.0:
                    self.console.print(f"[green]✅ Multi-state verification: Matched {ref_name} ({similarity}%)[/green]")
                    self.element_interactor.current_state_id = target_state_id
                    return True
            
            self.console.print(f"[yellow]⚠️ Multi-state verification: No state matched ≥99.0%[/yellow]")
            return False
        
        return True
    
    def _find_safe_click_areas(self, window_pos: Dict, margin: int = 20, debug: bool = True) -> List[Tuple[int, int]]:
        """Find safe click areas using improved strategies:
        1. Centroids of non-interactive elements
        2. "Home" tab location (safe navigation)
        3. Validated 50x50 blank areas in header region
        """
        safe_areas = []
        
        # Get current state data
        current_state_data = self.state_manager.fdom_data["states"].get(
            self.element_interactor.current_state_id, {}
        )
        current_nodes = current_state_data.get("nodes", {})
        
        # ✅ STRATEGY 1: Use centroids of non-interactive elements
        for node_id, node_data in current_nodes.items():
            if not node_data.get('g_interactive', True):  # Non-interactive elements
                bbox = node_data.get('bbox', [])
                if len(bbox) == 4:
                    # Calculate centroid in absolute coordinates
                    centroid_x = window_pos['left'] + (bbox[0] + bbox[2]) // 2
                    centroid_y = window_pos['top'] + (bbox[1] + bbox[3]) // 2
                    safe_areas.append((centroid_x, centroid_y))
                    
                    if debug:
                        element_name = node_data.get('g_icon_name', 'unknown')
                        self.console.print(f"[dim]✅ Non-interactive safe area: ({centroid_x}, {centroid_y}) from '{element_name}'[/dim]")
        
        # ✅ STRATEGY 2: Find "Home" tab - safe navigation button (LOOK IN ROOT STATE)
        home_found = False
        
        # ✅ FIX: Look for Home tab in ROOT state, not current state
        root_state_data = self.state_manager.fdom_data["states"].get("root", {})
        root_nodes = root_state_data.get("nodes", {})
        
        for node_id, node_data in root_nodes.items():
            element_name = node_data.get('g_icon_name', '').lower()
            if element_name == 'home':
                bbox = node_data.get('bbox', [])
                if len(bbox) == 4:
                    # Calculate centroid in absolute coordinates
                    home_x = window_pos['left'] + (bbox[0] + bbox[2]) // 2
                    home_y = window_pos['top'] + (bbox[1] + bbox[3]) // 2
                    safe_areas.append((home_x, home_y))
                    home_found = True
                    
                    if debug:
                        self.console.print(f"[green]🏠 Home tab safe area: ({home_x}, {home_y}) from ROOT state '{element_name}' ({node_id})[/green]")
                    break
        
        if not home_found and debug:
            self.console.print(f"[yellow]⚠️ No 'Home' tab found in ROOT state[/yellow]")
        
        # ✅ STRATEGY 3: Find validated 50x50 blank areas in header (if we need more safe areas)
        if len(safe_areas) < 3:  # Need at least 3 safe areas for reliability
            header_safe_areas = self._find_validated_header_safe_areas(window_pos)
            safe_areas.extend(header_safe_areas)
        
        if debug:
            self.console.print(f"[dim]🎯 Found {len(safe_areas)} total safe areas[/dim]")
            for i, (x, y) in enumerate(safe_areas):
                self.console.print(f"[dim]   Safe #{i+1}: ({x}, {y})[/dim]")
        
        return safe_areas

    def _find_validated_header_safe_areas(self, window_pos: Dict) -> List[Tuple[int, int]]:
        """Find 4 validated 50x50 blank areas in top header using hover testing"""
        
        # Define header region (top ~100px)
        header_top = window_pos['top'] + 10
        header_bottom = window_pos['top'] + 100
        header_left = window_pos['left'] + 50  
        header_right = window_pos['left'] + window_pos['width'] - 50
        
        # Generate candidate 50x50 areas
        candidates = []
        for y in range(header_top, header_bottom - 50, 25):
            for x in range(header_left, header_right - 50, 100):
                candidates.append((x + 25, y + 25))  # Center of 50x50 area
        
        # ✅ VALIDATE using hover testing (like auto-captioner)
        validated_safe_areas = []
        
        self.console.print(f"[dim]🔍 Testing {min(len(candidates), 8)} header candidates for safe areas...[/dim]")
        
        for candidate_x, candidate_y in candidates[:8]:  # Test max 8 candidates
            try:
                # Take before screenshot
                before_screenshot = self.element_interactor.screenshot_manager.take_screenshot("safe_area_test")
                if not before_screenshot:
                    continue
                
                # Hover over candidate area (like auto-captioner)
                self.app_controller.gui_api.set_cursor_position(candidate_x, candidate_y)
                time.sleep(0.5)  # Brief hover to trigger any tooltips
                
                # Take after screenshot  
                after_screenshot = self.element_interactor.screenshot_manager.take_screenshot("safe_area_after")
                if not after_screenshot:
                    continue
                
                # ✅ CORRECTED: Use the actual method name
                hash_before = self.visual_differ.calculate_image_hash(before_screenshot)
                hash_after = self.visual_differ.calculate_image_hash(after_screenshot)
                
                if hash_before == hash_after:
                    # ✅ No changes - this area is safe!
                    validated_safe_areas.append((candidate_x, candidate_y))
                    self.console.print(f"[dim]✅ Validated header safe area: ({candidate_x}, {candidate_y})[/dim]")
                    
                    if len(validated_safe_areas) >= 4:  # Found enough safe areas
                        break
                else:
                    self.console.print(f"[dim]⚠️ Area ({candidate_x}, {candidate_y}) triggered visual changes - skipping[/dim]")
                
                # Cleanup screenshots
                if not self.element_interactor.debug_mode:
                    self.element_interactor.screenshot_manager.cleanup_screenshot(before_screenshot)
                    self.element_interactor.screenshot_manager.cleanup_screenshot(after_screenshot)
                    
            except Exception as e:
                self.console.print(f"[dim]⚠️ Error testing area ({candidate_x}, {candidate_y}): {e}[/dim]")
                continue
        
        self.console.print(f"[dim]🎯 Header validation found {len(validated_safe_areas)} safe areas[/dim]")
        return validated_safe_areas
    
    def _is_likely_global_control(self, element_name: str, element_bbox: List[int]) -> bool:
        """Determine if an element is likely a global app control vs dialog control"""
        
        # Get current window bounds
        window_pos = self.element_interactor._get_current_window_position()
        if not window_pos or len(element_bbox) != 4:
            return False
        
        x1, y1, x2, y2 = element_bbox
        element_width = x2 - x1
        element_height = y2 - y1
        
        # Convert to window-relative coordinates
        rel_x1 = x1 - window_pos['left']
        rel_y1 = y1 - window_pos['top']
        rel_x2 = x2 - window_pos['left'] 
        rel_y2 = y2 - window_pos['top']
        
        # ✅ WINDOW-RELATIVE FILTERING (works on any screen resolution)
        window_width = window_pos['width']
        window_height = window_pos['height']
        
        # Rule 1: Elements in the top-right corner of the window (typical close button area)
        if (rel_x2 > window_width * 0.9 and  # Right 10% of window
            rel_y1 < window_height * 0.1 and  # Top 10% of window  
            element_width < 50 and element_height < 50 and  # Small button
            element_name.strip() == "x"):
            
            self.console.print(f"[yellow]🚫 Element '{element_name}' is in top-right corner - likely global app close button[/yellow]")
            return True
        
        # Rule 2: Elements at the very top edge (title bar area)
        if (rel_y1 < 50 and  # Very top of window
            element_name.strip() == "x"):
            
            self.console.print(f"[yellow]🚫 Element '{element_name}' is in title bar area - likely global control[/yellow]")
            return True
        
        # Rule 3: If we're NOT in root state, and this is a single "x" character,
        # and it's positioned like a standard Windows close button
        if (self.element_interactor.current_state_id != "root" and
            element_name.strip() == "x" and
            rel_x2 > window_width * 0.85):  # Right 15% of window
            
            self.console.print(f"[yellow]🚫 Element '{element_name}' looks like main app close button (we're in dialog state)[/yellow]")
            return True
        
        return False 

    def _auto_restart_with_default_file(self) -> bool:
        """Auto-restart application using existing launch logic"""
        try:
            self.console.print(f"[cyan]🔄 Step 1: Marking current node as explored...[/cyan]")
            
            # ✅ MARK NODE: Change status from "pending" to "explored" before restart
            self._mark_current_exploration_as_explored()
            
            self.console.print(f"[cyan]🔄 Step 2: Closing current application...[/cyan]")
            
            # Close current app
            if self.app_controller.current_app_info:
                window_id = self.app_controller.current_app_info["window_id"]
                self.app_controller.gui_api.close_window(window_id)
                time.sleep(2)  # Wait for close
            
            self.console.print(f"[cyan]🔄 Step 3: Restarting with existing launch logic...[/cyan]")
            
            # ✅ USE EXISTING: Just call the existing launch method (it already knows about default files)
            app_executable_path = self.app_controller.current_app_info.get("executable_path")
            if not app_executable_path:
                self.console.print(f"[red]❌ No executable path found for restart[/red]")
                return False
            
            # ✅ EXISTING LOGIC: Use the same launch method that already handles default files
            launch_result = self.app_controller.launch_app()
            
            if launch_result["success"]:
                self.console.print(f"[green]✅ App restarted successfully using existing launch logic[/green]")
                
                # Wait for app to be ready
                time.sleep(3)
                
                # ✅ RESET: Clear navigation state and return to root
                self.navigation_chain.clear()
                self.element_interactor.current_state_id = "root"
                
                return True
            else:
                self.console.print(f"[red]❌ App restart failed: {launch_result.get('error')}[/red]")
                return False
                
        except Exception as e:
            self.console.print(f"[red]❌ Auto-restart failed: {e}[/red]")
            return False

    def _mark_current_exploration_as_explored(self):
        """Mark the node we were trying to explore as 'explored' so we don't retry it"""
        try:
            # ✅ IDENTIFY: What node were we trying to explore when things went wrong?
            current_state_id = self.element_interactor.current_state_id
            
            # Get the last navigation step (the node that opened current problematic state)
            if self.navigation_chain:
                last_nav = self.navigation_chain[-1]
                problematic_node = last_nav.get('node_id')
                from_state = last_nav.get('from_state')
                
                if problematic_node and from_state:
                    self.console.print(f"[yellow]📝 Marking {problematic_node} as 'explored' (caused navigation issues)[/yellow]")
                    
                    # Update FDOM status
                    fdom_data = self.state_manager.fdom_data
                    if (from_state in fdom_data.get("states", {}) and 
                        problematic_node in fdom_data["states"][from_state].get("nodes", {})):
                        
                        node_data = fdom_data["states"][from_state]["nodes"][problematic_node]
                        node_data["status"] = "explored"
                        node_data["exploration_result"] = "navigation_failed_restart_required"
                        node_data["exploration_timestamp"] = time.time()
                        
                        # Save to file
                        self.state_manager.save_fdom_to_file()
                        
                        # Remove from pending sets
                        if hasattr(self.state_manager, 'pending_nodes'):
                            pending_id = f"{from_state}::{problematic_node}"
                            self.state_manager.pending_nodes.discard(pending_id)
                        
                        self.console.print(f"[green]✅ Marked {problematic_node} as explored in FDOM[/green]")
                    else:
                        self.console.print(f"[yellow]⚠️ Could not find {problematic_node} in FDOM to mark as explored[/yellow]")
                else:
                    self.console.print(f"[yellow]⚠️ No problematic node identified to mark as explored[/yellow]")
            else:
                self.console.print(f"[yellow]⚠️ No navigation chain to identify problematic node[/yellow]")
                
        except Exception as e:
            self.console.print(f"[yellow]⚠️ Error marking node as explored: {e}[/yellow]") 
    def _get_target_state_screenshot(self, target_state: str):
        """Get screenshot of the target state"""
        try:
            # Implement the logic to get a screenshot of the target state
            # This is a placeholder and should be replaced with the actual implementation
            return None
        except Exception as e:
            self.console.print(f"[red]❌ Error getting target state screenshot: {e}[/red]")
            return None 
