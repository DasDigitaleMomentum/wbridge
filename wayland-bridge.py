#!/usr/bin/env python3
"""
Witsy Wayland Bridge - Self-contained GTK4-based solution
=========================================================

This bridge provides Wayland compatibility for Witsy using only GTK4/GDK APIs.
No external clipboard tools required - completely self-contained.

Features:
- Direct GTK4 clipboard/primary selection monitoring
- GTK-native global shortcut registration
- HTTP communication with Witsy
- GUI for configuration and monitoring
- Headless mode for background operation

Requirements:
- python3
- PyGObject (GTK4)
- requests library

Usage:
    python3 wayland-bridge.py              # GUI mode
    python3 wayland-bridge.py --headless   # Background mode
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gtk, Gdk, GLib, Gio

import sys
import json
import threading
import argparse
import subprocess
import configparser
import time
from pathlib import Path
from typing import Optional, Dict, Any

try:
    import requests
except ImportError:
    print("Error: requests library not found. Install with: pip install requests")
    sys.exit(1)

# Configuration constants
POLL_INTERVAL_MS = 300
MAX_HISTORY = 50
CONFIG_DIR = Path.home() / '.config' / 'witsy-bridge'
CONFIG_FILE = CONFIG_DIR / 'config.ini'


class WitsyClient:
    """HTTP client for communicating with Witsy"""
    
    def __init__(self, base_url: str = "http://127.0.0.1:8080", api_key: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Witsy-Bridge/1.0'
        }
        if api_key:
            self.headers['Authorization'] = f'Bearer {api_key}'
    
    def send_selection(self, text: str, selection_type: str = "primary") -> bool:
        """Send selection text to Witsy"""
        try:
            response = requests.post(
                f'{self.base_url}/api/selection/set',
                json={
                    'text': text,
                    'type': selection_type,
                    'sourceApp': self._get_active_window_info()
                },
                headers=self.headers,
                timeout=5
            )
            return response.status_code == 200
        except requests.RequestException as e:
            print(f"Failed to send selection: {e}")
            return False
    
    def trigger_shortcut(self, action: str) -> bool:
        """Trigger a Witsy shortcut"""
        try:
            response = requests.post(
                f'{self.base_url}/api/shortcut/{action}',
                json={
                    'sourceApp': self._get_active_window_info()
                },
                headers=self.headers,
                timeout=5
            )
            return response.status_code == 200
        except requests.RequestException as e:
            print(f"Failed to trigger {action}: {e}")
            return False
    
    def trigger_shortcut_with_text(self, action: str, text: str) -> bool:
        """Trigger shortcut with specific text"""
        try:
            response = requests.post(
                f'{self.base_url}/api/automation/grab-and-process',
                json={
                    'action': action,
                    'selectedText': text,
                    'sourceApp': self._get_active_window_info()
                },
                headers=self.headers,
                timeout=10
            )
            return response.status_code == 200
        except requests.RequestException as e:
            print(f"Failed to trigger {action} with text: {e}")
            return False
    
    def health_check(self) -> bool:
        """Check if Witsy is accessible"""
        try:
            response = requests.get(
                f'{self.base_url}/api/health',
                headers=self.headers,
                timeout=3
            )
            return response.status_code == 200
        except requests.RequestException:
            return False
    
    def _get_active_window_info(self) -> Dict:
        """Get information about currently active window"""
        try:
            # Try different methods to get window info
            if self._command_exists('hyprctl'):
                # Hyprland
                result = subprocess.run(['hyprctl', 'activewindow', '-j'], 
                                     capture_output=True, text=True, timeout=1)
                if result.returncode == 0:
                    info = json.loads(result.stdout)
                    return {
                        "name": info.get('class', 'unknown'),
                        "pid": info.get('pid', 0),
                        "title": info.get('title', 'unknown')
                    }
            
            elif self._command_exists('swaymsg'):
                # Sway
                result = subprocess.run(['swaymsg', '-t', 'get_tree'], 
                                     capture_output=True, text=True, timeout=1)
                if result.returncode == 0:
                    tree = json.loads(result.stdout)
                    focused = self._find_focused_sway_node(tree)
                    if focused:
                        return {
                            "name": focused.get('app_id', 'unknown'),
                            "pid": focused.get('pid', 0),
                            "title": focused.get('name', 'unknown')
                        }
        
        except (subprocess.SubprocessError, FileNotFoundError, ValueError, json.JSONDecodeError):
            pass
        
        # Fallback
        return {
            "name": "unknown",
            "pid": 0,
            "title": "unknown"
        }
    
    def _command_exists(self, command: str) -> bool:
        """Check if command exists"""
        try:
            subprocess.run(['which', command], capture_output=True, check=True, timeout=1)
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False
    
    def _find_focused_sway_node(self, node: dict) -> Optional[dict]:
        """Find focused node in Sway tree"""
        if node.get('focused'):
            return node
        
        for child in node.get('nodes', []):
            result = self._find_focused_sway_node(child)
            if result:
                return result
        
        for child in node.get('floating_nodes', []):
            result = self._find_focused_sway_node(child)
            if result:
                return result
        
        return None


class HotkeyManager:
    """Manages global hotkeys for different environments"""
    
    def __init__(self, witsy_client: WitsyClient, config: configparser.ConfigParser):
        self.witsy_client = witsy_client
        self.config = config
        self.registered_hotkeys = {}
        self.default_hotkeys = {
            'prompt': '<Ctrl><Alt>p',
            'chat': '<Ctrl><Alt>c', 
            'command': '<Ctrl><Alt>m',
            'readaloud': '<Ctrl><Alt>r',
            'transcribe': '<Ctrl><Alt>t',
            'scratchpad': '<Ctrl><Alt>s',
            'realtime': '<Ctrl><Alt>v',
            'studio': '<Ctrl><Alt>d',
            'forge': '<Ctrl><Alt>f'
        }
    
    def get_default_hotkey(self, action: str) -> str:
        """Get default hotkey for action"""
        return self.default_hotkeys.get(action, '')
    
    def register_hotkeys(self):
        """Register global hotkeys"""
        if not self.config.getboolean('hotkeys', 'enabled', fallback=True):
            print("Hotkeys disabled in config")
            return
        
        # Method 1: Try Hyprland
        if self._try_hyprland_hotkeys():
            return
        
        # Method 2: Try Sway
        if self._try_sway_hotkeys():
            return
        
        # Method 3: Try GNOME/KDE gsettings
        if self._try_gsettings_hotkeys():
            return
        
        print("Warning: Could not register hotkeys - no supported method found")
        print("Supported: Hyprland, Sway, GNOME/KDE with gsettings")
        print("Available shortcuts (Ctrl+Alt+key):")
        for action, hotkey in self.default_hotkeys.items():
            print(f"  {action}: {hotkey}")
    
    def _try_hyprland_hotkeys(self) -> bool:
        """Try registering hotkeys with Hyprland"""
        if not self._command_exists('hyprctl'):
            return False
        
        print("Registering hotkeys with Hyprland...")
        for action in self.default_hotkeys.keys():
            hotkey = self.config.get('hotkeys', action, fallback=self.default_hotkeys[action])
            if hotkey:
                # Convert GTK format to Hyprland format
                hypr_key = self._convert_to_hyprland_format(hotkey)
                command = f'python3 {__file__} --trigger {action}'
                
                try:
                    subprocess.run([
                        'hyprctl', 'keyword', 'bind', 
                        f'{hypr_key}, exec, {command}'
                    ], check=True, capture_output=True)
                    print(f"✓ Registered {action}: {hotkey}")
                except subprocess.CalledProcessError as e:
                    print(f"✗ Failed to register {action}: {e}")
        
        return True
    
    def _try_sway_hotkeys(self) -> bool:
        """Try registering hotkeys with Sway"""
        if not self._command_exists('swaymsg'):
            return False
        
        print("Registering hotkeys with Sway...")
        for action in self.default_hotkeys.keys():
            hotkey = self.config.get('hotkeys', action, fallback=self.default_hotkeys[action])
            if hotkey:
                # Convert GTK format to Sway format
                sway_key = self._convert_to_sway_format(hotkey)
                command = f'python3 {__file__} --trigger {action}'
                
                try:
                    subprocess.run([
                        'swaymsg', f'bindsym {sway_key} exec {command}'
                    ], check=True, capture_output=True)
                    print(f"✓ Registered {action}: {hotkey}")
                except subprocess.CalledProcessError as e:
                    print(f"✗ Failed to register {action}: {e}")
        
        return True
    
    def _try_gsettings_hotkeys(self) -> bool:
        """Try registering hotkeys with GNOME/KDE gsettings"""
        if not self._command_exists('gsettings'):
            return False
        
        print("Note: For GNOME/KDE, you may need to manually configure shortcuts in System Settings")
        print("Custom Commands:")
        
        for action in self.default_hotkeys.keys():
            hotkey = self.config.get('hotkeys', action, fallback=self.default_hotkeys[action])
            command = f'python3 {__file__} --trigger {action}'
            print(f"  {action}: {hotkey} -> {command}")
        
        return True
    
    def _convert_to_hyprland_format(self, gtk_hotkey: str) -> str:
        """Convert GTK hotkey format to Hyprland format"""
        # <Ctrl><Alt>p -> CTRL ALT, p
        result = gtk_hotkey.replace('<Super>', 'SUPER ').replace('<Shift>', 'SHIFT ').replace('<Ctrl>', 'CTRL ').replace('<Alt>', 'ALT ')
        result = result.replace('>', '').replace('<', '').strip()
        return result.replace('  ', ' ')
    
    def _convert_to_sway_format(self, gtk_hotkey: str) -> str:
        """Convert GTK hotkey format to Sway format"""
        # <Ctrl><Alt>p -> Ctrl+Alt+p
        result = gtk_hotkey.replace('<Super>', 'Mod4+').replace('<Shift>', 'Shift+').replace('<Ctrl>', 'Ctrl+').replace('<Alt>', 'Alt+')
        result = result.replace('>', '').replace('<', '')
        return result
    
    def _command_exists(self, command: str) -> bool:
        """Check if command exists"""
        try:
            subprocess.run(['which', command], capture_output=True, check=True, timeout=1)
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False


class ConfigManager:
    """Configuration management"""
    
    def __init__(self):
        self.config_dir = CONFIG_DIR
        self.config_file = CONFIG_FILE
        self.ensure_config_dir()
    
    def ensure_config_dir(self):
        """Ensure config directory exists"""
        self.config_dir.mkdir(parents=True, exist_ok=True)
    
    def load_config(self) -> configparser.ConfigParser:
        """Load configuration"""
        config = configparser.ConfigParser()
        
        # Set defaults
        config.add_section('witsy')
        config.set('witsy', 'url', 'http://127.0.0.1:8080')
        config.set('witsy', 'api_key', '')
        config.set('witsy', 'auto_send_selection', 'false')
        
        config.add_section('hotkeys')
        config.set('hotkeys', 'enabled', 'true')
        config.set('hotkeys', 'prompt', '<Ctrl><Alt>p')
        config.set('hotkeys', 'chat', '<Ctrl><Alt>c')
        config.set('hotkeys', 'command', '<Ctrl><Alt>m')
        config.set('hotkeys', 'readaloud', '<Ctrl><Alt>r')
        config.set('hotkeys', 'transcribe', '<Ctrl><Alt>t')
        config.set('hotkeys', 'scratchpad', '<Ctrl><Alt>s')
        config.set('hotkeys', 'realtime', '<Ctrl><Alt>v')
        config.set('hotkeys', 'studio', '<Ctrl><Alt>d')
        config.set('hotkeys', 'forge', '<Ctrl><Alt>f')
        
        config.add_section('general')
        config.set('general', 'max_history', '50')
        config.set('general', 'poll_interval_ms', '300')
        
        # Load from file if exists
        if self.config_file.exists():
            try:
                config.read(self.config_file)
            except Exception as e:
                print(f"Error loading config: {e}")
        
        return config
    
    def save_config(self, config: configparser.ConfigParser):
        """Save configuration"""
        try:
            with open(self.config_file, 'w') as f:
                config.write(f)
            print(f"Configuration saved to {self.config_file}")
        except Exception as e:
            print(f"Error saving config: {e}")


class WaylandBridgeWindow(Gtk.ApplicationWindow):
    """Main application window with GTK4 clipboard monitoring"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.set_title("Witsy Wayland Bridge")
        self.set_default_size(800, 600)
        
        # Configuration
        self.config_manager = ConfigManager()
        self.config = self.config_manager.load_config()
        
        # Witsy client
        self.witsy_client = WitsyClient(
            self.config.get('witsy', 'url', fallback='http://127.0.0.1:8080'),
            self.config.get('witsy', 'api_key', fallback=None) or None
        )
        
        # Hotkey manager
        self.hotkey_manager = HotkeyManager(self.witsy_client, self.config)
        
        # Clipboard models
        self.clipboard_model = Gtk.StringList()
        self.primary_model = Gtk.StringList()
        
        # Clipboard caches
        self.cache_clip = None
        self.cache_prim = None
        
        # Build UI
        self.build_ui()
        
        # Initialize GTK4 clipboard monitoring (SELF-CONTAINED!)
        display = self.get_display()
        self.clipboard = display.get_clipboard()
        self.primary = display.get_primary_clipboard()
        
        # Start polling clipboard using native GTK APIs
        GLib.timeout_add(POLL_INTERVAL_MS, self.poll_clipboards)
        
        # Register hotkeys
        self.hotkey_manager.register_hotkeys()
        
        # Check Witsy connection
        GLib.timeout_add(5000, self.check_witsy_connection)
        self.check_witsy_connection()
    
    def build_ui(self):
        """Build the user interface"""
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_child(main_box)
        
        # Status bar
        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        status_box.set_margin_start(10)
        status_box.set_margin_end(10)
        status_box.set_margin_top(10)
        
        self.status_label = Gtk.Label(label="Connecting to Witsy...")
        self.connection_indicator = Gtk.Label(label="⚪")
        status_box.append(self.status_label)
        status_box.append(self.connection_indicator)
        main_box.append(status_box)
        
        # Notebook for tabs
        notebook = Gtk.Notebook()
        main_box.append(notebook)
        
        # History tab
        history_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        history_box.set_margin_start(10)
        history_box.set_margin_end(10)
        history_box.append(self.create_history_view("CLIPBOARD", self.clipboard_model))
        history_box.append(self.create_history_view("PRIMARY", self.primary_model))
        notebook.append_page(history_box, Gtk.Label(label="Selection History"))
        
        # Test Commands tab
        test_commands_box = self.create_test_commands_view()
        notebook.append_page(test_commands_box, Gtk.Label(label="Test Commands"))
        
        # Settings tab
        settings_box = self.create_settings_view()
        notebook.append_page(settings_box, Gtk.Label(label="Settings"))
        
        # Status tab
        status_tab = self.create_status_view()
        notebook.append_page(status_tab, Gtk.Label(label="Status"))
    
    def create_history_view(self, title_text, model):
        """Create history view"""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        
        # Title with action buttons
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        title_label = Gtk.Label(label=f"<b>{title_text}</b>")
        title_label.set_use_markup(True)
        title_box.append(title_label)
        
        # Action buttons
        prompt_button = Gtk.Button(label="→ Prompt")
        prompt_button.connect("clicked", self.on_send_to_witsy, model, 'prompt')
        title_box.append(prompt_button)
        
        chat_button = Gtk.Button(label="→ Chat")
        chat_button.connect("clicked", self.on_send_to_witsy, model, 'chat')
        title_box.append(chat_button)
        
        box.append(title_box)
        
        # List view
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._on_factory_setup)
        factory.connect("bind", self._on_factory_bind)
        
        list_view = Gtk.ListView(model=Gtk.NoSelection(model=model), factory=factory)
        
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_child(list_view)
        scrolled.set_vexpand(True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        
        box.append(scrolled)
        return box
    
    def create_test_commands_view(self):
        """Create test commands view with buttons for all Witsy actions"""
        scrolled = Gtk.ScrolledWindow()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_start(20)
        box.set_margin_end(20)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        
        # Title
        title_label = Gtk.Label(label="<b>Test Witsy Commands</b>")
        title_label.set_use_markup(True)
        title_label.set_xalign(0)
        box.append(title_label)
        
        # Test text input
        text_frame = Gtk.Frame(label="Test Text (for commands that need text)")
        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        text_box.set_margin_start(10)
        text_box.set_margin_end(10)
        text_box.set_margin_top(10)
        text_box.set_margin_bottom(10)
        
        self.test_text_view = Gtk.TextView()
        self.test_text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        buffer = self.test_text_view.get_buffer()
        buffer.set_text("Das ist ein Testtext für Witsy Kommandos. Diese Nachricht wird an Witsy gesendet, wenn Sie einen der Buttons unten klicken.")
        
        scrolled_text = Gtk.ScrolledWindow()
        scrolled_text.set_child(self.test_text_view)
        scrolled_text.set_size_request(-1, 100)
        scrolled_text.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        text_box.append(scrolled_text)
        
        text_frame.set_child(text_box)
        box.append(text_frame)
        
        # Commands grid
        commands_frame = Gtk.Frame(label="Available Commands")
        commands_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        commands_box.set_margin_start(10)
        commands_box.set_margin_end(10)
        commands_box.set_margin_top(10)
        commands_box.set_margin_bottom(10)
        
        # Commands with descriptions
        commands = [
            ('prompt', 'Prompt', 'Send text to AI prompt window'),
            ('chat', 'Chat', 'Start a chat with the selected text'),
            ('command', 'Command', 'Execute a command with the text'),
            ('readaloud', 'Read Aloud', 'Have the text read aloud'),
            ('transcribe', 'Transcribe', 'Transcribe audio to text'),
            ('scratchpad', 'Scratchpad', 'Add text to scratchpad'),
            ('realtime', 'Realtime', 'Start realtime conversation'),
            ('studio', 'Studio', 'Open in studio mode'),
            ('forge', 'Forge', 'Use forge functionality')
        ]
        
        # Create grid of buttons
        grid = Gtk.Grid()
        grid.set_column_spacing(10)
        grid.set_row_spacing(10)
        
        row = 0
        col = 0
        for action, label, description in commands:
            # Button box with shortcut display
            button_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            
            # Main button
            button = Gtk.Button(label=f"Test {label}")
            button.connect("clicked", self.on_test_command, action)
            button.set_size_request(150, 40)
            button_box.append(button)
            
            # Shortcut label
            shortcut = self.hotkey_manager.get_default_hotkey(action)
            shortcut_label = Gtk.Label(label=f"({shortcut})")
            shortcut_label.set_css_classes(['dim-label'])
            shortcut_label.set_xalign(0.5)
            button_box.append(shortcut_label)
            
            # Description label
            desc_label = Gtk.Label(label=description)
            desc_label.set_wrap(True)
            desc_label.set_max_width_chars(20)
            desc_label.set_css_classes(['caption'])
            desc_label.set_xalign(0.5)
            button_box.append(desc_label)
            
            grid.attach(button_box, col, row, 1, 1)
            
            col += 1
            if col >= 3:  # 3 columns
                col = 0
                row += 1
        
        commands_box.append(grid)
        commands_frame.set_child(commands_box)
        box.append(commands_frame)
        
        # Action log
        log_frame = Gtk.Frame(label="Action Log")
        log_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        log_box.set_margin_start(10)
        log_box.set_margin_end(10)
        log_box.set_margin_top(10)
        log_box.set_margin_bottom(10)
        
        # Clear log button
        clear_button = Gtk.Button(label="Clear Log")
        clear_button.connect("clicked", self.on_clear_log)
        log_box.append(clear_button)
        
        # Log text view
        self.log_text_view = Gtk.TextView()
        self.log_text_view.set_editable(False)
        self.log_text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        log_buffer = self.log_text_view.get_buffer()
        
        scrolled_log = Gtk.ScrolledWindow()
        scrolled_log.set_child(self.log_text_view)
        scrolled_log.set_size_request(-1, 150)
        scrolled_log.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        log_box.append(scrolled_log)
        
        log_frame.set_child(log_box)
        box.append(log_frame)
        
        scrolled.set_child(box)
        return scrolled
    
    def on_test_command(self, button, action):
        """Test a specific command"""
        # Get test text
        buffer = self.test_text_view.get_buffer()
        start_iter = buffer.get_start_iter()
        end_iter = buffer.get_end_iter()
        test_text = buffer.get_text(start_iter, end_iter, False)
        
        # Log the action
        self.log_action(f"Testing {action} with text: '{test_text[:50]}{'...' if len(test_text) > 50 else ''}'")
        
        # Trigger command
        def test_in_thread():
            timestamp = time.strftime("%H:%M:%S")
            
            # Always send with text for text-based commands
            text_commands = ['prompt', 'chat', 'command', 'readaloud', 'scratchpad', 'studio', 'forge']
            
            if action in text_commands and test_text.strip():
                # Use the grab-and-process endpoint that simulates selection
                success = self.witsy_client.trigger_shortcut_with_text(action, test_text)
                self.log_action(f"[{timestamp}] {action} (with text): {'✓ SUCCESS' if success else '✗ FAILED'}")
            elif action in ['transcribe', 'realtime']:
                # These don't need text, just trigger
                success = self.witsy_client.trigger_shortcut(action)
                self.log_action(f"[{timestamp}] {action} (no text): {'✓ SUCCESS' if success else '✗ FAILED'}")
            else:
                # Fallback - try both
                if test_text.strip():
                    success = self.witsy_client.trigger_shortcut_with_text(action, test_text)
                    self.log_action(f"[{timestamp}] {action} (with text): {'✓ SUCCESS' if success else '✗ FAILED'}")
                else:
                    success = self.witsy_client.trigger_shortcut(action)
                    self.log_action(f"[{timestamp}] {action} (no text): {'✓ SUCCESS' if success else '✗ FAILED'}")
            
            GLib.idle_add(self.update_test_button, button, action)
        
        button.set_sensitive(False)
        button.set_label("Testing...")
        threading.Thread(target=test_in_thread, daemon=True).start()
    
    def update_test_button(self, button, action):
        """Update button after test"""
        button.set_sensitive(True)
        button.set_label(f"Test {action.title()}")
    
    def on_clear_log(self, button):
        """Clear the action log"""
        buffer = self.log_text_view.get_buffer()
        buffer.set_text("")
        self.log_action("Log cleared")
    
    def log_action(self, message):
        """Add message to action log"""
        buffer = self.log_text_view.get_buffer()
        timestamp = time.strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}\n"
        
        # Append to buffer
        end_iter = buffer.get_end_iter()
        buffer.insert(end_iter, log_message)
        
        # Auto-scroll to bottom
        mark = buffer.get_insert()
        self.log_text_view.scroll_mark_onscreen(mark)
        
        # Print to console too
        print(log_message.strip())
    
    def create_settings_view(self):
        """Create settings view"""
        scrolled = Gtk.ScrolledWindow()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_start(20)
        box.set_margin_end(20)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        
        # Witsy connection
        witsy_frame = Gtk.Frame(label="Witsy Connection")
        witsy_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        witsy_box.set_margin_start(10)
        witsy_box.set_margin_end(10)
        witsy_box.set_margin_top(10)
        witsy_box.set_margin_bottom(10)
        
        # URL
        url_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        url_label = Gtk.Label(label="Witsy URL:")
        url_label.set_size_request(100, -1)
        self.url_entry = Gtk.Entry()
        self.url_entry.set_text(self.config.get('witsy', 'url'))
        self.url_entry.set_hexpand(True)
        url_box.append(url_label)
        url_box.append(self.url_entry)
        witsy_box.append(url_box)
        
        # API Key
        key_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        key_label = Gtk.Label(label="API Key:")
        key_label.set_size_request(100, -1)
        self.key_entry = Gtk.Entry()
        self.key_entry.set_text(self.config.get('witsy', 'api_key'))
        self.key_entry.set_visibility(False)
        self.key_entry.set_hexpand(True)
        key_box.append(key_label)
        key_box.append(self.key_entry)
        witsy_box.append(key_box)
        
        # Test button
        test_button = Gtk.Button(label="Test Connection")
        test_button.connect("clicked", self.on_test_connection)
        witsy_box.append(test_button)
        
        witsy_frame.set_child(witsy_box)
        box.append(witsy_frame)
        
        # Save button
        save_button = Gtk.Button(label="Save Settings")
        save_button.connect("clicked", self.on_save_settings)
        box.append(save_button)
        
        scrolled.set_child(box)
        return scrolled
    
    def create_status_view(self):
        """Create status view"""
        scrolled = Gtk.ScrolledWindow()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_start(20)
        box.set_margin_end(20)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        
        # Status information
        status_label = Gtk.Label(label="<b>Bridge Status</b>")
        status_label.set_use_markup(True)
        box.append(status_label)
        
        # Environment detection
        env_text = "Detected Environment:\n"
        if subprocess.run(['which', 'hyprctl'], capture_output=True).returncode == 0:
            env_text += "• Hyprland ✓\n"
        elif subprocess.run(['which', 'swaymsg'], capture_output=True).returncode == 0:
            env_text += "• Sway ✓\n"
        elif subprocess.run(['which', 'gsettings'], capture_output=True).returncode == 0:
            env_text += "• GNOME/KDE (limited shortcuts) ⚠️\n"
        else:
            env_text += "• Unknown environment ⚠️\n"
        
        env_label = Gtk.Label(label=env_text)
        env_label.set_xalign(0)
        box.append(env_label)
        
        # Clipboard monitoring status
        monitor_label = Gtk.Label(label="Clipboard Monitoring: ✓ Active (GTK4 native)")
        monitor_label.set_xalign(0)
        box.append(monitor_label)
        
        # Shortcut information
        shortcut_text = "Available Shortcuts (Ctrl+Alt+key):\n"
        for action, hotkey in self.hotkey_manager.default_hotkeys.items():
            shortcut_text += f"• {action}: {hotkey}\n"
        
        shortcut_label = Gtk.Label(label=shortcut_text)
        shortcut_label.set_xalign(0)
        box.append(shortcut_label)
        
        scrolled.set_child(box)
        return scrolled
    
    def _on_factory_setup(self, factory, list_item):
        """Setup list item"""
        label = Gtk.Label(xalign=0, wrap=True)
        label.set_margin_start(5)
        label.set_margin_end(5)
        list_item.set_child(label)
    
    def _on_factory_bind(self, factory, list_item):
        """Bind list item"""
        label = list_item.get_child()
        text = list_item.get_item().get_string()
        display_text = text[:100] + "..." if len(text) > 100 else text
        label.set_text(display_text)
    
    def poll_clipboards(self):
        """Poll clipboards using native GTK4 APIs - SELF-CONTAINED!"""
        # Read clipboard asynchronously
        self.clipboard.read_text_async(None, self._on_clipboard_read, "clipboard")
        self.primary.read_text_async(None, self._on_clipboard_read, "primary")
        return True
    
    def _on_clipboard_read(self, source, res, selection_type):
        """Handle clipboard read - completely GTK-based"""
        try:
            text = source.read_text_finish(res)
            if not text or len(text.strip()) == 0:
                return
            
            # Update history
            if selection_type == "clipboard":
                if text != self.cache_clip:
                    self.cache_clip = text
                    self.clipboard_model.splice(0, 0, [text])
                    if self.clipboard_model.get_n_items() > MAX_HISTORY:
                        self.clipboard_model.splice(MAX_HISTORY, 1, [])
            elif selection_type == "primary":
                if text != self.cache_prim:
                    self.cache_prim = text
                    self.primary_model.splice(0, 0, [text])
                    if self.primary_model.get_n_items() > MAX_HISTORY:
                        self.primary_model.splice(MAX_HISTORY, 1, [])
            
            # Optionally send to Witsy
            if self.config.getboolean('witsy', 'auto_send_selection', fallback=False):
                threading.Thread(
                    target=self.witsy_client.send_selection,
                    args=(text, selection_type),
                    daemon=True
                ).start()
                
        except GLib.Error:
            pass
    
    def check_witsy_connection(self):
        """Check Witsy connection"""
        def check_in_thread():
            if self.witsy_client.health_check():
                GLib.idle_add(self.update_connection_status, True, "Connected to Witsy")
            else:
                GLib.idle_add(self.update_connection_status, False, "Cannot connect to Witsy")
        
        threading.Thread(target=check_in_thread, daemon=True).start()
        return True
    
    def update_connection_status(self, connected, message):
        """Update connection status"""
        self.status_label.set_text(message)
        self.connection_indicator.set_text("🟢" if connected else "🔴")
    
    def on_test_connection(self, button):
        """Test connection"""
        button.set_sensitive(False)
        button.set_label("Testing...")
        
        def test_in_thread():
            url = self.url_entry.get_text()
            api_key = self.key_entry.get_text() or None
            
            temp_client = WitsyClient(url, api_key)
            success = temp_client.health_check()
            
            GLib.idle_add(self.show_test_result, button, success)
        
        threading.Thread(target=test_in_thread, daemon=True).start()
    
    def show_test_result(self, button, success):
        """Show test result"""
        button.set_sensitive(True)
        button.set_label("Test Connection")
        
        message = "✓ Connection successful" if success else "✗ Connection failed"
        self.status_label.set_text(message)
        self.connection_indicator.set_text("🟢" if success else "🔴")
    
    def on_save_settings(self, button):
        """Save settings"""
        self.config.set('witsy', 'url', self.url_entry.get_text())
        self.config.set('witsy', 'api_key', self.key_entry.get_text())
        
        self.config_manager.save_config(self.config)
        
        # Update client
        self.witsy_client = WitsyClient(
            self.url_entry.get_text(),
            self.key_entry.get_text() or None
        )
        
        self.status_label.set_text("Settings saved")
    
    def on_send_to_witsy(self, button, model, action):
        """Send latest selection to Witsy"""
        if model.get_n_items() > 0:
            text = model.get_item(0).get_string()
            self.send_selection_to_witsy(text, action)
    
    def send_selection_to_witsy(self, text, action):
        """Send selection to Witsy"""
        def send_in_thread():
            success = self.witsy_client.trigger_shortcut_with_text(action, text)
            message = f"✓ Sent to Witsy ({action})" if success else f"✗ Failed to send"
            GLib.idle_add(lambda: self.status_label.set_text(message))
        
        threading.Thread(target=send_in_thread, daemon=True).start()


class WaylandBridgeApp(Gtk.Application):
    """Main application class"""
    
    def __init__(self):
        super().__init__(
            application_id='org.witsy.waylandbridge',
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE
        )
        self.add_main_option(
            "headless", ord("h"), GLib.OptionFlags.NONE,
            GLib.OptionArg.NONE, "Run in headless mode", None
        )
        self.add_main_option(
            "trigger", ord("t"), GLib.OptionFlags.NONE,
            GLib.OptionArg.STRING, "Trigger specific action", None
        )
        self.headless = False
        self.trigger_action = None
    
    def do_command_line(self, command_line):
        options = command_line.get_options_dict()
        options = options.end().unpack()
        
        if "headless" in options:
            self.headless = True
        
        if "trigger" in options:
            self.trigger_action = options["trigger"]
        
        self.activate()
        return 0
    
    def do_activate(self):
        if self.trigger_action:
            # Single action mode - just trigger and exit
            config_manager = ConfigManager()
            config = config_manager.load_config()
            
            witsy_client = WitsyClient(
                config.get('witsy', 'url', fallback='http://127.0.0.1:8080'),
                config.get('witsy', 'api_key', fallback=None) or None
            )
            
            print(f"Shortcut triggered: {self.trigger_action}")
            success = witsy_client.trigger_shortcut(self.trigger_action)
            print(f"Result: {'✓ SUCCESS' if success else '✗ FAILED'}")
            return
        
        # Normal GUI/headless mode
        win = self.props.active_window
        if not win:
            win = WaylandBridgeWindow(application=self)
        
        if not self.headless:
            win.present()
        else:
            print("Running in headless mode...")
            print("Clipboard monitoring active, hotkeys registered")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Witsy Wayland Bridge - Self-contained GTK4 solution')
    parser.add_argument('--headless', action='store_true', help='Run in headless mode')
    parser.add_argument('--trigger', '-t', help='Trigger specific action and exit')
    parser.add_argument('--version', '-v', action='version', version='Witsy Wayland Bridge 1.0.0')
    
    # Handle arguments manually since Gtk.Application also uses argparse
    if len(sys.argv) > 1:
        # Quick action trigger mode
        if '--trigger' in sys.argv or '-t' in sys.argv:
            try:
                idx = sys.argv.index('--trigger') if '--trigger' in sys.argv else sys.argv.index('-t')
                if idx + 1 < len(sys.argv):
                    action = sys.argv[idx + 1]
                    
                    config_manager = ConfigManager()
                    config = config_manager.load_config()
                    
                    witsy_client = WitsyClient(
                        config.get('witsy', 'url', fallback='http://127.0.0.1:8080'),
                        config.get('witsy', 'api_key', fallback=None) or None
                    )
                    
                    print(f"Shortcut triggered: {action}")
                    success = witsy_client.trigger_shortcut(action)
                    print(f"Result: {'✓ SUCCESS' if success else '✗ FAILED'}")
                    return 0
            except (ValueError, IndexError):
                print("Error: --trigger requires an action argument")
                return 1
    
    # Normal application mode
    app = WaylandBridgeApp()
    return app.run(sys.argv)


if __name__ == '__main__':
    sys.exit(main())
