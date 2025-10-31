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
        
        # Start monitoring thread
        if not self.monitoring_thread or not self.monitoring_thread.is_alive():
            self.monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
            self.monitoring_thread.start()
        
        # Initial connection attempt
        self._initial_connection_sequence()
    
    def stop(self):
        """Stop the Wi-Fi management system"""
        self.logger.info("Stopping Wi-Fi Manager...")
        self.should_exit = True
        
        if self.ap_mode_active:
            self.stop_ap_mode()
        
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.monitoring_thread.join(timeout=5)
    
    def _initial_connection_sequence(self):
        """Handle initial Wi-Fi connection on startup"""
        self.logger.info("Starting initial Wi-Fi connection sequence...")
        
        # Wait for system to stabilize
        if hasattr(self.shared_data, 'startup_delay') and self.shared_data.startup_delay > 0:
            self.logger.info(f"Waiting for system startup delay: {self.shared_data.startup_delay}s")
            time.sleep(self.shared_data.startup_delay)
        
        # Try to connect to known networks
        startup_start = time.time()
        connected = False
        
        while (time.time() - startup_start) < self.connection_timeout and not connected and not self.should_exit:
            self.logger.info(f"Connection attempt {self.connection_attempts + 1}/{self.max_connection_attempts}")
            
            if self.try_connect_known_networks():
                connected = True
                self.wifi_connected = True
                self.shared_data.wifi_connected = True
                self.logger.info("Successfully connected to known network")
                break
            
            self.connection_attempts += 1
            if self.connection_attempts >= self.max_connection_attempts:
                self.logger.warning("Max connection attempts reached")
                break
            
            time.sleep(10)  # Wait 10 seconds between attempts
        
        # If no connection established, start AP mode
        if not connected and not self.should_exit:
            self.logger.info("No Wi-Fi connection established, starting AP mode...")
            self.start_ap_mode()
        
        self.startup_complete = True
    
    def _monitoring_loop(self):
        """Background monitoring loop for Wi-Fi status"""
        while not self.should_exit:
            try:
                # Check current connection status
                was_connected = self.wifi_connected
                self.wifi_connected = self.check_wifi_connection()
                self.shared_data.wifi_connected = self.wifi_connected
                
                # Handle connection state changes
                if was_connected and not self.wifi_connected:
                    self.logger.warning("Wi-Fi connection lost!")
                    self._handle_connection_lost()
                elif not was_connected and self.wifi_connected:
                    self.logger.info("Wi-Fi connection established!")
                    if self.ap_mode_active:
                        self.logger.info("Stopping AP mode due to successful connection")
                        self.stop_ap_mode()
                
                # Update current SSID if connected
                if self.wifi_connected:
                    self.current_ssid = self.get_current_ssid()
                
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
            # Method 1: Check using nmcli
            result = subprocess.run(['nmcli', '-t', '-f', 'ACTIVE,TYPE', 'con', 'show'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line and 'yes:802-11-wireless' in line:
                        return True
            
            # Method 2: Check using ip command
            result = subprocess.run(['ip', 'route', 'get', '8.8.8.8'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and 'dev wlan0' in result.stdout:
                return True
            
            # Method 3: Ping test
            result = subprocess.run(['ping', '-c', '1', '-W', '3', '8.8.8.8'], 
                                  capture_output=True, text=True, timeout=10)
            return result.returncode == 0
            
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