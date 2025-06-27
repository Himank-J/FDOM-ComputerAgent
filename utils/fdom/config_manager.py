"""
ConfigManager - Foundation for fDOM Framework
Handles all configuration loading, validation, and testing
"""
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

class ConfigManager:
    """
    Professional configuration management for fDOM framework
    Handles loading, validation, and testing of all configuration settings
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize ConfigManager with automatic config loading
        
        Args:
            config_path: Optional path to config file. Uses default if None.
        """
        self.console = Console()
        self.config_path = config_path or self._get_default_config_path()
        self.config = self._load_and_validate_config()
        
    def _get_default_config_path(self) -> str:
        """Get default config file path relative to this module"""
        current_dir = Path(__file__).parent
        return str(current_dir / "fdom_config.json")
    
    def _load_and_validate_config(self) -> Dict[str, Any]:
        """
        Load configuration file with comprehensive validation
        
        Returns:
            Loaded and validated configuration dictionary
            
        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If config file is invalid JSON or missing required keys
        """
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in config file: {e}")
        
        # Validate required sections
        required_sections = [
            "exploration", "graph_traversal", "node_status_tracking",
            "capture", "storage", "seraphine", "interaction", "debug"
        ]
        
        missing_sections = [section for section in required_sections if section not in config]
        if missing_sections:
            raise ValueError(f"Missing required config sections: {missing_sections}")
        
        return config
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get configuration value using dot notation
        
        Args:
            key_path: Dot-separated path to config value (e.g., "exploration.max_states_per_session")
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        keys = key_path.split('.')
        value = self.config
        
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default
    
    def update(self, key_path: str, value: Any) -> None:
        """
        Update configuration value using dot notation
        
        Args:
            key_path: Dot-separated path to config value
            value: New value to set
        """
        keys = key_path.split('.')
        config = self.config
        
        # Navigate to parent of target key
        for key in keys[:-1]:
            if key not in config:
                config[key] = {}
            config = config[key]
        
        # Set the final value
        config[keys[-1]] = value
    
    def test_config(self) -> bool:
        """
        Comprehensive configuration testing with rich console output
        
        Returns:
            True if all tests pass, False otherwise
        """
        self.console.print("\n[bold blue]🔧 FDOM CONFIGURATION TEST[/bold blue]")
        self.console.print("=" * 60)
        
        try:
            # Test 1: Config file exists and loads
            self.console.print(f"[yellow]📁 Config file:[/yellow] {self.config_path}")
            self.console.print(f"[green]✅ Config loaded successfully[/green]")
            
            # Test 2: Show all configuration sections
            self._display_config_sections()
            
            # Test 3: Validate critical values
            validation_results = self._validate_config_values()
            
            # Test 4: Check file paths and permissions
            path_results = self._test_storage_paths()
            
            # Summary
            all_passed = validation_results and path_results
            status = "[green]✅ PASSED[/green]" if all_passed else "[red]❌ FAILED[/red]"
            self.console.print(f"\n[bold]🎯 Configuration Test Result: {status}[/bold]")
            
            return all_passed
            
        except Exception as e:
            self.console.print(f"[red]❌ Configuration test failed: {e}[/red]")
            return False
    
    def _display_config_sections(self) -> None:
        """Display all configuration sections in a beautiful table"""
        table = Table(title="📋 Configuration Sections", show_header=True, header_style="bold magenta")
        table.add_column("Section", style="cyan", width=20)
        table.add_column("Key Settings", style="white", width=40)
        table.add_column("Status", justify="center", width=10)
        
        for section_name, section_data in self.config.items():
            if isinstance(section_data, dict):
                key_count = len(section_data)
                sample_keys = list(section_data.keys())[:3]
                if len(section_data) > 3:
                    sample_keys.append("...")
                
                table.add_row(
                    section_name,
                    f"{key_count} settings: {', '.join(sample_keys)}",
                    "[green]✓[/green]"
                )
        
        self.console.print(table)
    
    def _validate_config_values(self) -> bool:
        """Validate configuration values for correctness"""
        self.console.print("\n[yellow]🔍 Validating Configuration Values[/yellow]")
        
        validation_tests = [
            ("exploration.max_states_per_session", lambda x: isinstance(x, int) and x > 0, "Must be positive integer"),
            ("exploration.click_timeout_seconds", lambda x: isinstance(x, (int, float)) and x > 0, "Must be positive number"),
            ("capture.screenshot_format", lambda x: x in ["png", "jpg", "jpeg"], "Must be png, jpg, or jpeg"),
            ("capture.screenshot_quality", lambda x: isinstance(x, int) and 1 <= x <= 100, "Must be integer 1-100"),
            ("seraphine.confidence_threshold", lambda x: isinstance(x, (int, float)) and 0 <= x <= 1, "Must be float 0-1"),
            ("storage.screenshots_subdir", lambda x: isinstance(x, str) and len(x) > 0, "Must be non-empty string"),
            ("interaction.window_focus_delay", lambda x: isinstance(x, (int, float)) and x > 0, "Must be positive number"),
            ("debug.verbose_logging", lambda x: isinstance(x, bool), "Must be boolean"),
        ]
        
        all_valid = True
        for key_path, validator, error_msg in validation_tests:
            value = self.get(key_path)
            
            # Check if key exists
            if value is None:
                self.console.print(f"  [red]❌[/red] {key_path}: [red]MISSING[/red]")
                self.console.print(f"    [red]Error: Key not found in configuration[/red]")
                all_valid = False
                continue
            
            # Validate value
            is_valid = validator(value)
            status = "[green]✅[/green]" if is_valid else "[red]❌[/red]"
            self.console.print(f"  {status} {key_path}: {value}")
            
            if not is_valid:
                self.console.print(f"    [red]Error: {error_msg}[/red]")
                all_valid = False
        
        return all_valid
    
    def _test_storage_paths(self) -> bool:
        """Test storage path configuration"""
        self.console.print("\n[yellow]📁 Testing Storage Path Configuration[/yellow]")
        
        storage_dirs = [
            self.get("storage.screenshots_subdir"),
            self.get("storage.crops_subdir"),
            self.get("storage.diffs_subdir"),
            self.get("storage.templates_subdir")
        ]
        
        all_valid = True
        for dir_name in storage_dirs:
            if not dir_name or not isinstance(dir_name, str):
                self.console.print(f"  [red]❌ Invalid directory name: {dir_name}[/red]")
                all_valid = False
            else:
                self.console.print(f"  [green]✅[/green] {dir_name}: Valid directory name")
        
        return all_valid
    
    def get_app_storage_config(self) -> Dict[str, str]:
        """
        Get storage configuration for app directory creation
        
        Returns:
            Dictionary with storage subdirectory names
        """
        return {
            'screenshots': self.get("storage.screenshots_subdir"),
            'crops': self.get("storage.crops_subdir"),
            'diffs': self.get("storage.diffs_subdir"),
            'templates': self.get("storage.templates_subdir")
        }
    
    def get_seraphine_config(self) -> Dict[str, Any]:
        """
        Get seraphine integration configuration
        
        Returns:
            Dictionary with seraphine settings
        """
        return self.config.get("seraphine", {})
    
    def is_debug_mode(self) -> bool:
        """Check if debug mode is enabled"""
        return self.get("debug.verbose_logging", False)
    
    def should_use_rich_output(self) -> bool:
        """Check if rich console output should be used"""
        return self.get("debug.rich_console_output", True)


def test_config_manager():
    """Test function for ConfigManager - DELTA 1 testing"""
    console = Console()
    
    console.print("\n[bold green]🚀 DELTA 1: ConfigManager Test[/bold green]")
    console.print("=" * 50)
    
    try:
        # Test 1: Initialize ConfigManager
        console.print("[yellow]🔧 Initializing ConfigManager...[/yellow]")
        config_manager = ConfigManager()
        console.print("[green]✅ ConfigManager initialized successfully[/green]")
        
        # Test 2: Run comprehensive config test
        test_result = config_manager.test_config()
        
        # Test 3: Test specific value retrieval
        console.print("\n[yellow]🔍 Testing Value Retrieval[/yellow]")
        test_keys = [
            "exploration.max_states_per_session",
            "capture.screenshot_format", 
            "seraphine.mode",
            "seraphine.confidence_threshold",
            "storage.screenshots_subdir"
        ]
        
        for key in test_keys:
            value = config_manager.get(key)
            console.print(f"  {key}: [cyan]{value}[/cyan]")
        
        # Test 4: Test configuration helpers
        console.print("\n[yellow]🛠️ Testing Helper Methods[/yellow]")
        storage_config = config_manager.get_app_storage_config()
        console.print(f"  Storage config: [cyan]{storage_config}[/cyan]")
        
        seraphine_config = config_manager.get_seraphine_config()
        console.print(f"  Seraphine config: [cyan]{seraphine_config}[/cyan]")
        
        debug_mode = config_manager.is_debug_mode()
        console.print(f"  Debug mode: [cyan]{debug_mode}[/cyan]")
        
        rich_output = config_manager.should_use_rich_output()
        console.print(f"  Rich output: [cyan]{rich_output}[/cyan]")
        
        # Final result
        if test_result:
            console.print("\n[bold green]🎉 DELTA 1 PASSED: ConfigManager is ready![/bold green]")
        else:
            console.print("\n[bold red]❌ DELTA 1 FAILED: Configuration issues detected[/bold red]")
            
        return test_result
        
    except Exception as e:
        console.print(f"\n[bold red]💥 DELTA 1 FAILED: {e}[/bold red]")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="fDOM ConfigManager - Delta 1 Testing")
    parser.add_argument("--test-config", action="store_true", help="Run comprehensive config test")
    parser.add_argument("--config-path", type=str, help="Path to custom config file")
    
    args = parser.parse_args()
    
    if args.test_config:
        success = test_config_manager()
        exit(0 if success else 1)
    else:
        print("Usage: python config_manager.py --test-config")
        print("       python config_manager.py --test-config --config-path /path/to/config.json")
