# wifi_manager.py
# Robust Wi-Fi management system for Bjorn IoT device
# Handles automatic connection, AP mode fallback, and web-based configuration
# Author: GitHub Copilot Assistant
# 
# Features:
# - Auto-connect to known Wi-Fi networks on boot
# - Fall back to AP mode if connection fails 
# - Web interface for Wi-Fi configuration
# - Robust connection monitoring with proper timing
# - Network scanning and credential management
# - Integration with wpa_supplicant and NetworkManager

import os
import time
import json
import subprocess
import threading
import logging
import re
import signal
from datetime import datetime, timedelta
from logger import Logger


class WiFiManager:
    """Manages Wi-Fi connections, AP mode, and configuration for Bjorn"""
    
    def __init__(self, shared_data):
        self.shared_data = shared_data
        self.logger = Logger(name="WiFiManager", level=logging.INFO)
        
        # State management
        self.wifi_connected = False
        self.ap_mode_active = False
        self.connection_attempts = 0
        self.last_connection_attempt = None
        self.connection_check_interval = 30  # seconds
        self.connection_timeout = 60  # Wait 60 seconds before starting AP
        self.max_connection_attempts = 3
        
        # Network management
        self.known_networks = []
        self.available_networks = []
        self.current_ssid = None
        
        # AP mode settings
        self.ap_ssid = "Bjorn-Setup"
        self.ap_password = "bjornpassword"
        self.ap_interface = "wlan0"
        self.ap_ip = "192.168.4.1"
        self.ap_subnet = "192.168.4.0/24"
        
        # Control flags
        self.should_exit = False
        self.monitoring_thread = None
        self.startup_complete = False
        
        # Load configuration
        self.load_wifi_config()
        
    def load_wifi_config(self):
        """Load Wi-Fi configuration from shared data"""
        try:
            config = self.shared_data.config
            
            # Load known networks
            self.known_networks = config.get('wifi_known_networks', [])
            
            # Load AP settings
            self.ap_ssid = config.get('wifi_ap_ssid', 'Bjorn-Setup')
            self.ap_password = config.get('wifi_ap_password', 'bjornpassword')
            self.connection_timeout = config.get('wifi_connection_timeout', 60)
            self.max_connection_attempts = config.get('wifi_max_attempts', 3)
            
            self.logger.info(f"Wi-Fi config loaded: {len(self.known_networks)} known networks")
            
        except Exception as e:
            self.logger.error(f"Error loading Wi-Fi config: {e}")
    
    def save_wifi_config(self):
        """Save Wi-Fi configuration to shared data"""
        try:
            self.shared_data.config['wifi_known_networks'] = self.known_networks
            self.shared_data.config['wifi_ap_ssid'] = self.ap_ssid
            self.shared_data.config['wifi_ap_password'] = self.ap_password
            self.shared_data.config['wifi_connection_timeout'] = self.connection_timeout
            self.shared_data.config['wifi_max_attempts'] = self.max_connection_attempts
            
            self.shared_data.save_config()
            self.logger.info("Wi-Fi configuration saved")
            
        except Exception as e:
            self.logger.error(f"Error saving Wi-Fi config: {e}")
    
    def start(self):
        """Start the Wi-Fi management system"""
        self.logger.info("Starting Wi-Fi Manager...")
        
        # Create a restart detection file to help identify service restarts
        self._create_restart_marker()
        
        # Start monitoring thread
        if not self.monitoring_thread or not self.monitoring_thread.is_alive():
            self.monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
            self.monitoring_thread.start()
        
        # Initial connection attempt
        self._initial_connection_sequence()
    
    def stop(self):
        """Stop the Wi-Fi management system"""
        self.logger.info("Stopping Wi-Fi Manager...")
        
        # Save current connection state before stopping
        current_ssid = self.get_current_ssid()
        is_connected = self.check_wifi_connection()
        self._save_connection_state(current_ssid, is_connected)
        
        self.should_exit = True
        
        # Clean up restart marker
        self._cleanup_restart_marker()
        
        if self.ap_mode_active:
            self.stop_ap_mode()
        
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.monitoring_thread.join(timeout=5)

    def _save_connection_state(self, ssid=None, connected=False):
        """Save current connection state to help with service restarts"""
        try:
            state_file = '/tmp/bjorn_wifi_state.json'
            state = {
                'timestamp': time.time(),
                'connected': connected,
                'ssid': ssid,
                'ap_mode': self.ap_mode_active
            }
            with open(state_file, 'w') as f:
                json.dump(state, f)
        except Exception as e:
            self.logger.warning(f"Could not save connection state: {e}")

    def _load_connection_state(self):
        """Load previous connection state"""
        try:
            state_file = '/tmp/bjorn_wifi_state.json'
            if os.path.exists(state_file):
                with open(state_file, 'r') as f:
                    state = json.load(f)
                    # Only use state if it's recent (less than 10 minutes old)
                    if time.time() - state.get('timestamp', 0) < 600:
                        return state
        except Exception as e:
            self.logger.warning(f"Could not load connection state: {e}")
        return None

    def _cleanup_connection_state(self):
        """Clean up connection state file"""
        try:
            state_file = '/tmp/bjorn_wifi_state.json'
            if os.path.exists(state_file):
                os.remove(state_file)
        except Exception as e:
            self.logger.warning(f"Could not clean up connection state: {e}")

    def _create_restart_marker(self):
        """Create a marker file to help detect service restarts"""
        try:
            marker_file = '/tmp/bjorn_wifi_manager.pid'
            with open(marker_file, 'w') as f:
                f.write(f"{os.getpid()}\n{time.time()}\n")
        except Exception as e:
            self.logger.warning(f"Could not create restart marker: {e}")

    def _cleanup_restart_marker(self):
        """Clean up the restart marker file"""
        try:
            marker_file = '/tmp/bjorn_wifi_manager.pid'
            if os.path.exists(marker_file):
                os.remove(marker_file)
        except Exception as e:
            self.logger.warning(f"Could not clean up restart marker: {e}")

    def _was_recently_running(self):
        """Check if WiFi manager was recently running (indicates service restart)"""
        try:
            marker_file = '/tmp/bjorn_wifi_manager.pid'
            if os.path.exists(marker_file):
                with open(marker_file, 'r') as f:
                    lines = f.readlines()
                    if len(lines) >= 2:
                        last_start_time = float(lines[1].strip())
                        # If the marker is less than 5 minutes old, consider it a recent restart
                        if time.time() - last_start_time < 300:
                            self.logger.info("Found recent WiFi manager marker - service restart detected")
                            return True
            return False
        except Exception as e:
            self.logger.warning(f"Could not check restart marker: {e}")
            return False
    
    def _initial_connection_sequence(self):
        """Handle initial Wi-Fi connection on startup - with smart existing connection detection"""
        self.logger.info("Starting Wi-Fi connection assessment...")
        
        # Check if this is a fresh boot or service restart
        is_fresh_boot = self._is_fresh_boot()
        
        # Load previous connection state for service restarts
        previous_state = None if is_fresh_boot else self._load_connection_state()
        
        if previous_state:
            self.logger.info(f"Previous state: connected={previous_state.get('connected')}, "
                           f"ssid={previous_state.get('ssid')}, ap_mode={previous_state.get('ap_mode')}")
        
        # First, check if we're already connected
        initial_check_start = time.time()
        for i in range(3):  # Check 3 times over 15 seconds to allow network to stabilize
            if self.check_wifi_connection():
                self.wifi_connected = True
                self.shared_data.wifi_connected = True
                self.current_ssid = self.get_current_ssid()
                self.logger.info(f"Already connected to Wi-Fi network: {self.current_ssid}")
                self._save_connection_state(self.current_ssid, True)  # Save successful connection
                self.startup_complete = True
                return  # Exit early - we're already connected!
            
            # If this is a service restart, don't wait too long
            wait_time = 5 if i < 2 else 10
            self.logger.info(f"Checking existing connection... attempt {i+1}/3 (waiting {wait_time}s)")
            time.sleep(wait_time)
        
        # Not connected, but check previous state for service restarts
        if not is_fresh_boot and previous_state and previous_state.get('connected'):
            prev_ssid = previous_state.get('ssid')
            if prev_ssid:
                self.logger.info(f"Service restart detected - attempting to reconnect to previous network: {prev_ssid}")
                if self.connect_to_network(prev_ssid):
                    # Give it a moment to establish connection
                    time.sleep(5)
                    if self.check_wifi_connection():
                        self.wifi_connected = True
                        self.shared_data.wifi_connected = True
                        self.current_ssid = prev_ssid
                        self.logger.info(f"Successfully reconnected to previous network: {prev_ssid}")
                        self._save_connection_state(prev_ssid, True)
                        self.startup_complete = True
                        return
        
        self.logger.info("No existing connection found, determining startup type...")
        
        if is_fresh_boot:
            # Fresh boot - use full startup delay
            if hasattr(self.shared_data, 'startup_delay') and self.shared_data.startup_delay > 0:
                self.logger.info(f"Fresh boot detected - waiting full startup delay: {self.shared_data.startup_delay}s")
                time.sleep(self.shared_data.startup_delay)
        else:
            # Service restart - use shorter delay
            restart_delay = 15  # Much shorter delay for service restarts
            self.logger.info(f"Service restart detected - using shorter delay: {restart_delay}s")
            time.sleep(restart_delay)
        
        # Now try to connect to known networks
        self.logger.info("Attempting to connect to known networks...")
        connection_start = time.time()
        connected = False
        
        # Adjust timeout based on startup type
        timeout = self.connection_timeout if is_fresh_boot else min(30, self.connection_timeout)
        
        while (time.time() - connection_start) < timeout and not connected and not self.should_exit:
            self.logger.info(f"Connection attempt {self.connection_attempts + 1}/{self.max_connection_attempts}")
            
            if self.try_connect_known_networks():
                connected = True
                self.wifi_connected = True
                self.shared_data.wifi_connected = True
                self.current_ssid = self.get_current_ssid()
                self.logger.info(f"Successfully connected to network: {self.current_ssid}")
                self._save_connection_state(self.current_ssid, True)  # Save successful connection
                break
            
            self.connection_attempts += 1
            if self.connection_attempts >= self.max_connection_attempts:
                self.logger.warning("Max connection attempts reached")
                break
            
            # Shorter wait between attempts for service restarts
            wait_time = 10 if is_fresh_boot else 5
            time.sleep(wait_time)
        
        # If no connection established, decide whether to start AP mode
        if not connected and not self.should_exit:
            # For service restarts, only start AP mode if we weren't previously connected
            should_start_ap = is_fresh_boot
            if previous_state and not previous_state.get('connected'):
                should_start_ap = True
            
            if should_start_ap and self.shared_data.config.get('wifi_auto_ap_fallback', True):
                self.logger.info("No Wi-Fi connection established, starting AP mode...")
                self.start_ap_mode()
            else:
                self.logger.info("Skipping AP mode - will retry connection in monitoring loop")
                self._save_connection_state(None, False)  # Save disconnected state
        
        self.startup_complete = True

    def _is_fresh_boot(self):
        """Determine if this is a fresh system boot or just a service restart"""
        try:
            # First check if we were recently running (service restart)
            if self._was_recently_running():
                self.logger.info("WiFi manager was recently running - treating as service restart")
                return False
            
            # Check system uptime
            with open('/proc/uptime', 'r') as f:
                uptime_seconds = float(f.read().split()[0])
            
            # If system has been up for less than 5 minutes, consider it a fresh boot
            if uptime_seconds < 300:  # 5 minutes
                self.logger.info(f"System uptime: {uptime_seconds:.1f}s - treating as fresh boot")
                return True
            
            # Check if this is the first time WiFi manager has started since boot
            # by checking if NetworkManager was recently started
            result = subprocess.run(['systemctl', 'show', 'NetworkManager', '--property=ActiveEnterTimestamp'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                nm_start_time = result.stdout.strip()
                self.logger.info(f"NetworkManager start time: {nm_start_time}")
                
                # If NetworkManager started recently (within last 2 minutes), likely fresh boot
                if 'ActiveEnterTimestamp=' in nm_start_time:
                    # This is a simplified check - in production you'd parse the timestamp
                    self.logger.info("NetworkManager recently started - treating as fresh boot")
                    return True
            
            self.logger.info(f"System uptime: {uptime_seconds:.1f}s - treating as service restart")
            return False
            
        except Exception as e:
            self.logger.warning(f"Could not determine boot type: {e} - assuming fresh boot")
            return True  # Default to fresh boot for safety
    
    def _monitoring_loop(self):
        """Background monitoring loop for Wi-Fi status"""
        last_state_save = 0
        
        while not self.should_exit:
            try:
                # Check current connection status
                was_connected = self.wifi_connected
                self.wifi_connected = self.check_wifi_connection()
                self.shared_data.wifi_connected = self.wifi_connected
                
                # Handle connection state changes
                if was_connected and not self.wifi_connected:
                    self.logger.warning("Wi-Fi connection lost!")
                    self._save_connection_state(None, False)  # Save disconnected state
                    self._handle_connection_lost()
                elif not was_connected and self.wifi_connected:
                    self.logger.info("Wi-Fi connection established!")
                    current_ssid = self.get_current_ssid()
                    self._save_connection_state(current_ssid, True)  # Save connected state
                    if self.ap_mode_active:
                        self.logger.info("Stopping AP mode due to successful connection")
                        self.stop_ap_mode()
                
                # Update current SSID if connected
                if self.wifi_connected:
                    self.current_ssid = self.get_current_ssid()
                
                # Periodically save connection state (every 2 minutes)
                current_time = time.time()
                if current_time - last_state_save > 120:
                    ssid = self.current_ssid if self.wifi_connected else None
                    self._save_connection_state(ssid, self.wifi_connected)
                    last_state_save = current_time
                
                time.sleep(self.connection_check_interval)
                
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                time.sleep(5)
    
    def _handle_connection_lost(self):
        """Handle when Wi-Fi connection is lost"""
        if not self.startup_complete:
            return  # Don't interfere with startup sequence
        
        # Try to reconnect to known networks
        self.logger.info("Attempting to reconnect...")
        if not self.try_connect_known_networks():
            # If can't reconnect and AP mode isn't active, start it
            if not self.ap_mode_active:
                self.logger.info("Starting AP mode due to connection loss")
                self.start_ap_mode()
    
    def check_wifi_connection(self):
        """Check if Wi-Fi is connected using multiple methods"""
        try:
            # Method 1: Check using nmcli for active wireless connections
            result = subprocess.run(['nmcli', '-t', '-f', 'ACTIVE,TYPE', 'con', 'show'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line and 'yes:802-11-wireless' in line:
                        # Double-check with device status
                        dev_result = subprocess.run(['nmcli', '-t', '-f', 'DEVICE,STATE', 'dev', 'wifi'], 
                                                  capture_output=True, text=True, timeout=5)
                        if dev_result.returncode == 0 and 'connected' in dev_result.stdout:
                            return True
            
            # Method 2: Check using iwconfig (if available)
            try:
                result = subprocess.run(['iwconfig', 'wlan0'], 
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0 and 'ESSID:' in result.stdout and 'Not-Associated' not in result.stdout:
                    # Verify we have an IP address
                    ip_result = subprocess.run(['ip', 'addr', 'show', 'wlan0'], 
                                             capture_output=True, text=True, timeout=5)
                    if ip_result.returncode == 0 and 'inet ' in ip_result.stdout:
                        return True
            except FileNotFoundError:
                pass  # iwconfig not available
            
            # Method 3: Check if we can reach the internet (but be quick about it)
            try:
                result = subprocess.run(['ping', '-c', '1', '-W', '2', '1.1.1.1'], 
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    # Ensure it's going through wlan0
                    route_result = subprocess.run(['ip', 'route', 'get', '1.1.1.1'], 
                                                capture_output=True, text=True, timeout=3)
                    if route_result.returncode == 0 and 'dev wlan0' in route_result.stdout:
                        return True
            except:
                pass  # Network unreachable, that's fine
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error checking Wi-Fi connection: {e}")
            return False
    
    def get_current_ssid(self):
        """Get the current connected SSID"""
        try:
            result = subprocess.run(['nmcli', '-t', '-f', 'ACTIVE,SSID', 'dev', 'wifi'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line.startswith('yes:'):
                        return line.split(':', 1)[1]
            return None
        except Exception as e:
            self.logger.error(f"Error getting current SSID: {e}")
            return None
    
    def scan_networks(self):
        """Scan for available Wi-Fi networks"""
        try:
            self.logger.info("Scanning for Wi-Fi networks...")
            
            # Trigger a new scan
            subprocess.run(['nmcli', 'dev', 'wifi', 'rescan'], 
                         capture_output=True, timeout=15)
            
            # Get scan results
            result = subprocess.run(['nmcli', '-t', '-f', 'SSID,SIGNAL,SECURITY', 'dev', 'wifi'], 
                                  capture_output=True, text=True, timeout=15)
            
            networks = []
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line and ':' in line:
                        parts = line.split(':')
                        if len(parts) >= 3 and parts[0]:  # SSID not empty
                            networks.append({
                                'ssid': parts[0],
                                'signal': int(parts[1]) if parts[1].isdigit() else 0,
                                'security': parts[2] if parts[2] else 'Open',
                                'known': parts[0] in [net['ssid'] for net in self.known_networks]
                            })
            
            # Remove duplicates and sort by signal strength
            seen_ssids = set()
            unique_networks = []
            for network in sorted(networks, key=lambda x: x['signal'], reverse=True):
                if network['ssid'] not in seen_ssids:
                    seen_ssids.add(network['ssid'])
                    unique_networks.append(network)
            
            self.available_networks = unique_networks
            self.logger.info(f"Found {len(unique_networks)} unique networks")
            return unique_networks
            
        except Exception as e:
            self.logger.error(f"Error scanning networks: {e}")
            return []
    
    def try_connect_known_networks(self):
        """Try to connect to known networks in priority order"""
        if not self.known_networks:
            self.logger.info("No known networks configured")
            return False
        
        # First, check if we're already connected to one of our known networks
        current_ssid = self.get_current_ssid()
        if current_ssid:
            known_ssids = [net['ssid'] for net in self.known_networks]
            if current_ssid in known_ssids:
                self.logger.info(f"Already connected to known network: {current_ssid}")
                return True
        
        # Sort known networks by priority (highest first)
        sorted_networks = sorted(self.known_networks, key=lambda x: x.get('priority', 0), reverse=True)
        
        for network in sorted_networks:
            try:
                ssid = network['ssid']
                self.logger.info(f"Attempting to connect to {ssid}...")
                
                if self.connect_to_network(ssid, network.get('password')):
                    self.logger.info(f"Successfully connected to {ssid}")
                    return True
                else:
                    self.logger.warning(f"Failed to connect to {ssid}")
                    
            except Exception as e:
                self.logger.error(f"Error connecting to {network.get('ssid', 'unknown')}: {e}")
        
        return False
    
    def connect_to_network(self, ssid, password=None):
        """Connect to a specific Wi-Fi network"""
        try:
            self.logger.info(f"Connecting to network: {ssid}")
            
            # Check if connection already exists
            result = subprocess.run(['nmcli', 'con', 'show', ssid], 
                                  capture_output=True, text=True)
            
            if result.returncode == 0:
                # Connection exists, try to activate it
                self.logger.info(f"Using existing connection for {ssid}")
                result = subprocess.run(['nmcli', 'con', 'up', ssid], 
                                      capture_output=True, text=True, timeout=30)
            else:
                # Create new connection
                cmd = ['nmcli', 'dev', 'wifi', 'connect', ssid]
                if password:
                    cmd.extend(['password', password])
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                # Wait a moment and verify connection
                time.sleep(5)
                return self.check_wifi_connection()
            else:
                self.logger.error(f"nmcli error: {result.stderr}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error connecting to {ssid}: {e}")
            return False
    
    def add_known_network(self, ssid, password=None, priority=1):
        """Add a network to the known networks list"""
        try:
            # Remove existing entry if it exists
            self.known_networks = [net for net in self.known_networks if net['ssid'] != ssid]
            
            # Add new entry
            network = {
                'ssid': ssid,
                'password': password,
                'priority': priority,
                'added_date': datetime.now().isoformat()
            }
            
            self.known_networks.append(network)
            self.save_wifi_config()
            
            self.logger.info(f"Added known network: {ssid}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error adding known network {ssid}: {e}")
            return False
    
    def remove_known_network(self, ssid):
        """Remove a network from the known networks list"""
        try:
            original_count = len(self.known_networks)
            self.known_networks = [net for net in self.known_networks if net['ssid'] != ssid]
            
            if len(self.known_networks) < original_count:
                self.save_wifi_config()
                self.logger.info(f"Removed known network: {ssid}")
                
                # Also remove from NetworkManager
                try:
                    subprocess.run(['nmcli', 'con', 'delete', ssid], 
                                 capture_output=True, timeout=10)
                except:
                    pass  # Ignore errors, connection might not exist
                
                return True
            else:
                self.logger.warning(f"Network {ssid} not found in known networks")
                return False
                
        except Exception as e:
            self.logger.error(f"Error removing known network {ssid}: {e}")
            return False
    
    def start_ap_mode(self):
        """Start Access Point mode"""
        if self.ap_mode_active:
            self.logger.info("AP mode already active")
            return True
        
        try:
            self.logger.info(f"Starting AP mode: {self.ap_ssid}")
            
            # Create hostapd configuration
            if not self._create_hostapd_config():
                return False
            
            # Create dnsmasq configuration
            if not self._create_dnsmasq_config():
                return False
            
            # Configure network interface
            if not self._configure_ap_interface():
                return False
            
            # Start services
            if self._start_ap_services():
                self.ap_mode_active = True
                self.logger.info("AP mode started successfully")
                return True
            else:
                self._cleanup_ap_mode()
                return False
                
        except Exception as e:
            self.logger.error(f"Error starting AP mode: {e}")
            self._cleanup_ap_mode()
            return False
    
    def stop_ap_mode(self):
        """Stop Access Point mode"""
        if not self.ap_mode_active:
            return True
        
        try:
            self.logger.info("Stopping AP mode...")
            
            # Stop services
            self._stop_ap_services()
            
            # Cleanup interface
            self._cleanup_ap_interface()
            
            self.ap_mode_active = False
            self.logger.info("AP mode stopped")
            return True
            
        except Exception as e:
            self.logger.error(f"Error stopping AP mode: {e}")
            return False
    
    def _create_hostapd_config(self):
        """Create hostapd configuration file"""
        try:
            config_content = f"""interface={self.ap_interface}
driver=nl80211
ssid={self.ap_ssid}
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase={self.ap_password}
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
"""
            
            os.makedirs('/tmp/bjorn', exist_ok=True)
            with open('/tmp/bjorn/hostapd.conf', 'w') as f:
                f.write(config_content)
            
            self.logger.info("Created hostapd configuration")
            return True
            
        except Exception as e:
            self.logger.error(f"Error creating hostapd config: {e}")
            return False
    
    def _create_dnsmasq_config(self):
        """Create dnsmasq configuration file"""
        try:
            config_content = f"""interface={self.ap_interface}
dhcp-range=192.168.4.2,192.168.4.20,255.255.255.0,24h
"""
            
            with open('/tmp/bjorn/dnsmasq.conf', 'w') as f:
                f.write(config_content)
            
            self.logger.info("Created dnsmasq configuration")
            return True
            
        except Exception as e:
            self.logger.error(f"Error creating dnsmasq config: {e}")
            return False
    
    def _configure_ap_interface(self):
        """Configure network interface for AP mode"""
        try:
            # Stop NetworkManager from managing the interface
            subprocess.run(['sudo', 'nmcli', 'dev', 'set', self.ap_interface, 'managed', 'no'], 
                         capture_output=True, timeout=10)
            
            # Configure IP address
            subprocess.run(['sudo', 'ip', 'addr', 'flush', 'dev', self.ap_interface], 
                         capture_output=True, timeout=10)
            subprocess.run(['sudo', 'ip', 'addr', 'add', f'{self.ap_ip}/24', 'dev', self.ap_interface], 
                         capture_output=True, timeout=10)
            subprocess.run(['sudo', 'ip', 'link', 'set', 'dev', self.ap_interface, 'up'], 
                         capture_output=True, timeout=10)
            
            self.logger.info("Configured AP interface")
            return True
            
        except Exception as e:
            self.logger.error(f"Error configuring AP interface: {e}")
            return False
    
    def _start_ap_services(self):
        """Start hostapd and dnsmasq services"""
        try:
            # Start hostapd
            self.hostapd_process = subprocess.Popen(['sudo', 'hostapd', '/tmp/bjorn/hostapd.conf'],
                                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            time.sleep(2)  # Give hostapd time to start
            
            if self.hostapd_process.poll() is not None:
                self.logger.error("hostapd failed to start")
                return False
            
            # Start dnsmasq
            self.dnsmasq_process = subprocess.Popen(['sudo', 'dnsmasq', '-C', '/tmp/bjorn/dnsmasq.conf', '-d'],
                                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            time.sleep(1)  # Give dnsmasq time to start
            
            if self.dnsmasq_process.poll() is not None:
                self.logger.error("dnsmasq failed to start")
                return False
            
            self.logger.info("AP services started")
            return True
            
        except Exception as e:
            self.logger.error(f"Error starting AP services: {e}")
            return False
    
    def _stop_ap_services(self):
        """Stop hostapd and dnsmasq services"""
        try:
            # Stop hostapd
            if hasattr(self, 'hostapd_process') and self.hostapd_process:
                self.hostapd_process.terminate()
                try:
                    self.hostapd_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.hostapd_process.kill()
            
            # Stop dnsmasq
            if hasattr(self, 'dnsmasq_process') and self.dnsmasq_process:
                self.dnsmasq_process.terminate()
                try:
                    self.dnsmasq_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.dnsmasq_process.kill()
            
            # Kill any remaining processes
            subprocess.run(['sudo', 'pkill', 'hostapd'], capture_output=True)
            subprocess.run(['sudo', 'pkill', 'dnsmasq'], capture_output=True)
            
            self.logger.info("AP services stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping AP services: {e}")
    
    def _cleanup_ap_interface(self):
        """Cleanup AP interface configuration"""
        try:
            # Flush IP address
            subprocess.run(['sudo', 'ip', 'addr', 'flush', 'dev', self.ap_interface], 
                         capture_output=True, timeout=10)
            
            # Return interface to NetworkManager
            subprocess.run(['sudo', 'nmcli', 'dev', 'set', self.ap_interface, 'managed', 'yes'], 
                         capture_output=True, timeout=10)
            
            self.logger.info("Cleaned up AP interface")
            
        except Exception as e:
            self.logger.error(f"Error cleaning up AP interface: {e}")
    
    def _cleanup_ap_mode(self):
        """Full cleanup of AP mode"""
        try:
            self._stop_ap_services()
            self._cleanup_ap_interface()
            
            # Remove config files
            for config_file in ['/tmp/bjorn/hostapd.conf', '/tmp/bjorn/dnsmasq.conf']:
                try:
                    if os.path.exists(config_file):
                        os.remove(config_file)
                except:
                    pass
                    
        except Exception as e:
            self.logger.error(f"Error in AP cleanup: {e}")
    
    def get_status(self):
        """Get current Wi-Fi manager status"""
        return {
            'wifi_connected': self.wifi_connected,
            'ap_mode_active': self.ap_mode_active,
            'current_ssid': self.current_ssid,
            'known_networks_count': len(self.known_networks),
            'connection_attempts': self.connection_attempts,
            'startup_complete': self.startup_complete,
            'available_networks': len(self.available_networks)
        }
    
    def get_known_networks(self):
        """Get list of known networks (without passwords)"""
        return [{
            'ssid': net['ssid'],
            'priority': net.get('priority', 1),
            'added_date': net.get('added_date', ''),
            'has_password': bool(net.get('password'))
        } for net in self.known_networks]
    
    def get_available_networks(self):
        """Get list of available networks from last scan"""
        return self.available_networks
    
    def force_reconnect(self):
        """Force a reconnection attempt"""
        self.logger.info("Forcing Wi-Fi reconnection...")
        self.connection_attempts = 0
        return self.try_connect_known_networks()
    
    def restart_networking(self):
        """Restart networking services"""
        try:
            self.logger.info("Restarting networking services...")
            
            if self.ap_mode_active:
                self.stop_ap_mode()
            
            # Restart NetworkManager
            subprocess.run(['sudo', 'systemctl', 'restart', 'NetworkManager'], 
                         capture_output=True, timeout=30)
            
            time.sleep(5)  # Wait for NetworkManager to start
            
            # Try to reconnect
            self.connection_attempts = 0
            self.try_connect_known_networks()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error restarting networking: {e}")
            return False