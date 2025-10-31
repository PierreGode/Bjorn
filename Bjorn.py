#bjorn.py
# This script defines the main execution flow for the Bjorn application. It initializes and starts
# various components such as network scanning, display, and web server functionalities. The Bjorn 
# class manages the primary operations, including initiating network scans and orchestrating tasks.
# The script handles startup delays, checks for Wi-Fi connectivity, and coordinates the execution of
# scanning and orchestrator tasks using semaphores to limit concurrent threads. It also sets up 
# signal handlers to ensure a clean exit when the application is terminated.

# Functions:
# - handle_exit:  handles the termination of the main and display threads.
# - handle_exit_webserver:  handles the termination of the web server thread.
# - is_wifi_connected: Checks for Wi-Fi connectivity using the nmcli command.

# The script starts by loading shared data configurations, then initializes and sta
# bjorn.py


import threading
import signal
import logging
import time
import sys
import subprocess
from init_shared import shared_data
from display import Display, handle_exit_display
from comment import Commentaireia
from webapp_modern import run_server, handle_exit as handle_exit_web
from orchestrator import Orchestrator
from logger import Logger
from wifi_manager import WiFiManager

logger = Logger(name="Bjorn.py", level=logging.DEBUG)

class Bjorn:
    """Main class for Bjorn. Manages the primary operations of the application."""
    def __init__(self, shared_data):
        self.shared_data = shared_data
        self.commentaire_ia = Commentaireia()
        self.orchestrator_thread = None
        self.orchestrator = None
        self.wifi_manager = WiFiManager(shared_data)
        
        # Set reference to this instance in shared_data for other modules
        self.shared_data.bjorn_instance = self

    def run(self):
        """Main loop for Bjorn. Waits for Wi-Fi connection and starts Orchestrator."""
        # Initialize Wi-Fi management system
        logger.info("Starting Wi-Fi management system...")
        self.wifi_manager.start()
        
        # Main loop to keep Bjorn running
        while not self.shared_data.should_exit:
            if not self.shared_data.manual_mode:
                self.check_and_start_orchestrator()
            time.sleep(10)  # Main loop idle waiting



    def check_and_start_orchestrator(self):
        """Check Wi-Fi and start the orchestrator if connected."""
        if self.wifi_manager.check_wifi_connection():
            self.shared_data.wifi_connected = True
            if self.orchestrator_thread is None or not self.orchestrator_thread.is_alive():
                self.start_orchestrator()
        else:
            self.shared_data.wifi_connected = False
            if not self.wifi_manager.startup_complete:
                logger.info("Waiting for Wi-Fi management system to complete startup...")
            else:
                logger.info("Waiting for Wi-Fi connection to start Orchestrator...")

    def start_orchestrator(self):
        """Start the orchestrator thread."""
        # Use Wi-Fi manager's connection check
        if self.wifi_manager.check_wifi_connection():
            self.shared_data.wifi_connected = True
            if self.orchestrator_thread is None or not self.orchestrator_thread.is_alive():
                logger.info("Starting Orchestrator thread...")
                self.shared_data.orchestrator_should_exit = False
                self.shared_data.manual_mode = False
                self.orchestrator = Orchestrator()
                self.orchestrator_thread = threading.Thread(target=self.orchestrator.run)
                self.orchestrator_thread.start()
                logger.info("Orchestrator thread started, automatic mode activated.")
            else:
                logger.info("Orchestrator thread is already running.")
        else:
            logger.warning("Cannot start Orchestrator: Wi-Fi is not connected.")

    def stop_orchestrator(self):
        """Stop the orchestrator thread."""
        self.shared_data.manual_mode = True
        logger.info("Stop button pressed. Manual mode activated & Stopping Orchestrator...")
        if self.orchestrator_thread is not None and self.orchestrator_thread.is_alive():
            logger.info("Stopping Orchestrator thread...")
            self.shared_data.orchestrator_should_exit = True
            self.orchestrator_thread.join()
            logger.info("Orchestrator thread stopped.")
            self.shared_data.bjornorch_status = "IDLE"
            self.shared_data.bjornstatustext2 = ""
            self.shared_data.manual_mode = True
        else:
            logger.info("Orchestrator thread is not running.")

    def stop(self):
        """Stop Bjorn and cleanup all resources."""
        logger.info("Stopping Bjorn...")
        
        # Stop orchestrator
        self.stop_orchestrator()
        
        # Stop Wi-Fi manager
        if hasattr(self, 'wifi_manager'):
            self.wifi_manager.stop()
        
        # Set exit flags
        self.shared_data.should_exit = True
        self.shared_data.orchestrator_should_exit = True
        self.shared_data.display_should_exit = True
        self.shared_data.webapp_should_exit = True
        
        logger.info("Bjorn stopped successfully")

    def is_wifi_connected(self):
        """Legacy method - use wifi_manager for new code."""
        if hasattr(self, 'wifi_manager'):
            return self.wifi_manager.check_wifi_connection()
        else:
            # Fallback to original method
            result = subprocess.Popen(['nmcli', '-t', '-f', 'active', 'dev', 'wifi'], stdout=subprocess.PIPE, text=True).communicate()[0]
            return 'yes' in result

    
    @staticmethod
    def start_display():
        """Start the display thread"""
        display = Display(shared_data)
        display_thread = threading.Thread(target=display.run)
        display_thread.start()
        return display_thread

def handle_exit(sig, frame, display_thread, bjorn_thread, web_thread):
    """Handles the termination of the main, display, and web threads."""
    logger.info("Received exit signal, initiating clean shutdown...")
    
    # Stop Bjorn instance first
    if hasattr(shared_data, 'bjorn_instance') and shared_data.bjorn_instance:
        shared_data.bjorn_instance.stop()
    
    # Set all exit flags
    shared_data.should_exit = True
    shared_data.orchestrator_should_exit = True
    shared_data.display_should_exit = True
    shared_data.webapp_should_exit = True
    
    # Stop individual threads
    handle_exit_display(sig, frame, display_thread)
    
    if display_thread and display_thread.is_alive():
        display_thread.join(timeout=5)
    if bjorn_thread and bjorn_thread.is_alive():
        bjorn_thread.join(timeout=5)
    if web_thread and web_thread.is_alive():
        web_thread.join(timeout=5)
    
    logger.info("Main loop finished. Clean exit.")
    sys.exit(0)



if __name__ == "__main__":
    logger.info("Starting threads")

    try:
        logger.info("Loading shared data config...")
        shared_data.load_config()

        logger.info("Starting display thread...")
        shared_data.display_should_exit = False  # Initialize display should_exit
        display_thread = Bjorn.start_display()

        logger.info("Starting Bjorn thread...")
        bjorn = Bjorn(shared_data)
        shared_data.bjorn_instance = bjorn  # Assigner l'instance de Bjorn à shared_data
        bjorn_thread = threading.Thread(target=bjorn.run)
        bjorn_thread.start()

        if shared_data.config["websrv"]:
            logger.info("Starting the web server...")
            web_thread = threading.Thread(target=run_server)
            web_thread.start()
        else:
            web_thread = None

        signal.signal(signal.SIGINT, lambda sig, frame: handle_exit(sig, frame, display_thread, bjorn_thread, web_thread))
        signal.signal(signal.SIGTERM, lambda sig, frame: handle_exit(sig, frame, display_thread, bjorn_thread, web_thread))

    except Exception as e:
        logger.error(f"An exception occurred during thread start: {e}")
        if 'display_thread' in locals():
            handle_exit_display(signal.SIGINT, None, display_thread)
        exit(1)
