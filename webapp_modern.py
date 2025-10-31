#webapp_modern.py
"""
Modern Flask-based web application for Bjorn
Features:
- Fast Flask backend with proper routing
- RESTful API endpoints
- WebSocket support for real-time updates
- Static file caching
- Better performance than SimpleHTTPRequestHandler
"""

import os
import sys
import json
import signal
import logging
import threading
from datetime import datetime
from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from init_shared import shared_data
from utils import WebUtils
from logger import Logger

# Initialize logger
logger = Logger(name="webapp_modern.py", level=logging.DEBUG)

# Initialize Flask app
app = Flask(__name__,
            static_folder='web',
            template_folder='web')
app.config['SECRET_KEY'] = 'bjorn-cyberviking-secret-key'
app.config['JSON_SORT_KEYS'] = False

# Enable CORS
CORS(app)

# Initialize SocketIO for real-time updates
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Initialize web utilities
web_utils = WebUtils(shared_data, logger)

# Global state
clients_connected = 0


# ============================================================================
# STATIC FILE ROUTES
# ============================================================================

@app.route('/')
def index():
    """Serve the main dashboard page"""
    return send_from_directory('web', 'index_modern.html')


@app.route('/<path:filename>')
def serve_static(filename):
    """Serve static files from web directory"""
    return send_from_directory('web', filename)


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.route('/api/status')
def get_status():
    """Get current Bjorn status"""
    try:
        status_data = {
            'bjorn_status': shared_data.bjornstatustext,
            'bjorn_status2': shared_data.bjornstatustext2,
            'bjorn_says': shared_data.bjornsays,
            'orchestrator_status': shared_data.bjornorch_status,
            'target_count': shared_data.targetnbr,
            'port_count': shared_data.portnbr,
            'vulnerability_count': shared_data.vulnnbr,
            'credential_count': shared_data.crednbr,
            'data_count': shared_data.datanbr,
            'wifi_connected': shared_data.wifi_connected,
            'bluetooth_active': shared_data.bluetooth_active,
            'pan_connected': shared_data.pan_connected,
            'usb_active': shared_data.usb_active,
            'manual_mode': shared_data.config.get('manual_mode', False),
            'timestamp': datetime.now().isoformat()
        }
        return jsonify(status_data)
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/config', methods=['GET'])
def get_config():
    """Get current configuration"""
    try:
        return jsonify(shared_data.config)
    except Exception as e:
        logger.error(f"Error getting config: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/config', methods=['POST'])
def update_config():
    """Update configuration"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Update configuration
        for key, value in data.items():
            if key in shared_data.config:
                shared_data.config[key] = value
        
        # Save configuration
        shared_data.save_config()
        
        # Emit update to all connected clients
        socketio.emit('config_updated', shared_data.config)
        
        return jsonify({'success': True, 'message': 'Configuration updated'})
    except Exception as e:
        logger.error(f"Error updating config: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/network')
def get_network():
    """Get network scan data"""
    try:
        data = shared_data.read_data()
        return jsonify(data)
    except Exception as e:
        logger.error(f"Error getting network data: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/credentials')
def get_credentials():
    """Get discovered credentials"""
    try:
        credentials = web_utils.get_all_credentials()
        return jsonify(credentials)
    except Exception as e:
        logger.error(f"Error getting credentials: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/loot')
def get_loot():
    """Get stolen data/loot"""
    try:
        loot = web_utils.get_loot_data()
        return jsonify(loot)
    except Exception as e:
        logger.error(f"Error getting loot: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/logs')
def get_logs():
    """Get recent logs"""
    try:
        # Read last 100 lines of temp log
        log_file = shared_data.webconsolelog
        if os.path.exists(log_file):
            with open(log_file, 'r') as f:
                lines = f.readlines()
                return jsonify({'logs': lines[-100:]})
        return jsonify({'logs': []})
    except Exception as e:
        logger.error(f"Error getting logs: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/display')
def get_display():
    """Get current EPD display image"""
    try:
        # Return the current display status image
        image_path = os.path.join(shared_data.picdir, 'current_display.png')
        if os.path.exists(image_path):
            return send_from_directory(shared_data.picdir, 'current_display.png')
        return jsonify({'error': 'Display image not found'}), 404
    except Exception as e:
        logger.error(f"Error getting display: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/actions', methods=['GET'])
def get_actions():
    """Get available actions"""
    try:
        with open(shared_data.actions_file, 'r') as f:
            actions = json.load(f)
        return jsonify(actions)
    except Exception as e:
        logger.error(f"Error getting actions: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/vulnerabilities')
def get_vulnerabilities():
    """Get vulnerability scan results"""
    try:
        vuln_data = web_utils.get_vulnerability_data()
        return jsonify(vuln_data)
    except Exception as e:
        logger.error(f"Error getting vulnerabilities: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# WEBSOCKET EVENTS
# ============================================================================

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    global clients_connected
    clients_connected += 1
    logger.info(f"Client connected. Total clients: {clients_connected}")
    emit('connected', {'message': 'Connected to Bjorn'})


@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    global clients_connected
    clients_connected -= 1
    logger.info(f"Client disconnected. Total clients: {clients_connected}")


@socketio.on('request_status')
def handle_status_request():
    """Handle status update request"""
    try:
        status_data = {
            'bjorn_status': shared_data.bjornstatustext,
            'bjorn_says': shared_data.bjornsays,
            'target_count': shared_data.targetnbr,
            'port_count': shared_data.portnbr,
            'vulnerability_count': shared_data.vulnnbr,
            'credential_count': shared_data.crednbr,
        }
        emit('status_update', status_data)
    except Exception as e:
        logger.error(f"Error handling status request: {e}")


# ============================================================================
# BACKGROUND TASKS
# ============================================================================

def broadcast_status_updates():
    """Broadcast status updates to all connected clients"""
    while not shared_data.webapp_should_exit:
        try:
            if clients_connected > 0:
                status_data = {
                    'bjorn_status': shared_data.bjornstatustext,
                    'bjorn_status2': shared_data.bjornstatustext2,
                    'bjorn_says': shared_data.bjornsays,
                    'target_count': shared_data.targetnbr,
                    'port_count': shared_data.portnbr,
                    'vulnerability_count': shared_data.vulnnbr,
                    'credential_count': shared_data.crednbr,
                    'data_count': shared_data.datanbr,
                    'timestamp': datetime.now().isoformat()
                }
                socketio.emit('status_update', status_data)
            
            socketio.sleep(2)  # Update every 2 seconds
        except Exception as e:
            logger.error(f"Error broadcasting status: {e}")
            socketio.sleep(5)


# ============================================================================
# SIGNAL HANDLERS
# ============================================================================

def handle_exit(signum, frame):
    """Handle exit signals"""
    logger.info("Shutting down web server...")
    shared_data.webapp_should_exit = True
    socketio.stop()
    sys.exit(0)


# ============================================================================
# MAIN
# ============================================================================

def run_server(host='0.0.0.0', port=8000):
    """Run the Flask server"""
    try:
        logger.info(f"Starting Bjorn web server on {host}:{port}")
        logger.info(f"Access the interface at http://{host}:{port}")
        
        # Start background status broadcaster
        socketio.start_background_task(broadcast_status_updates)
        
        # Run the server
        socketio.run(app, host=host, port=port, debug=False, allow_unsafe_werkzeug=True)
    except Exception as e:
        logger.error(f"Error running server: {e}")
        raise


if __name__ == "__main__":
    # Set up signal handling
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)
    
    # Run the server
    run_server()
