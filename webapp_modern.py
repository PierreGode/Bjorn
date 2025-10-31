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


def safe_int(value, default=0):
    """Safely convert value to int, handling numpy types"""
    try:
        if hasattr(value, 'item'):  # numpy types have .item() method
            return int(value.item())
        return int(value) if value is not None else default
    except (ValueError, TypeError, AttributeError):
        return default

def safe_str(value, default=""):
    """Safely convert value to string"""
    try:
        return str(value) if value is not None else default
    except (ValueError, TypeError):
        return default

def safe_bool(value, default=False):
    """Safely convert value to boolean"""
    try:
        return bool(value) if value is not None else default
    except (ValueError, TypeError):
        return default


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
            'bjorn_status': safe_str(shared_data.bjornstatustext),
            'bjorn_status2': safe_str(shared_data.bjornstatustext2),
            'bjorn_says': safe_str(shared_data.bjornsays),
            'orchestrator_status': safe_str(shared_data.bjornorch_status),
            'target_count': safe_int(shared_data.targetnbr),
            'port_count': safe_int(shared_data.portnbr),
            'vulnerability_count': safe_int(shared_data.vulnnbr),
            'credential_count': safe_int(shared_data.crednbr),
            'data_count': safe_int(shared_data.datanbr),
            'wifi_connected': safe_bool(shared_data.wifi_connected),
            'bluetooth_active': safe_bool(shared_data.bluetooth_active),
            'pan_connected': safe_bool(shared_data.pan_connected),
            'usb_active': safe_bool(shared_data.usb_active),
            'manual_mode': safe_bool(shared_data.config.get('manual_mode', False)),
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


@app.route('/api/stats')
def get_stats():
    """Get aggregated statistics"""
    try:
        stats = {
            'total_targets': safe_int(shared_data.targetnbr),
            'total_ports': safe_int(shared_data.portnbr),
            'total_vulnerabilities': safe_int(shared_data.vulnnbr),
            'total_credentials': safe_int(shared_data.crednbr),
            'total_data_stolen': safe_int(shared_data.datanbr),
            'scan_results_count': 0,
            'services_discovered': {}
        }
        
        # Add scan results count
        if os.path.exists(shared_data.netkbfile):
            import pandas as pd
            df = pd.read_csv(shared_data.netkbfile)
            stats['scan_results_count'] = safe_int(len(df[df['Alive'] == 1]) if 'Alive' in df.columns else len(df))
        
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# LEGACY ENDPOINTS (for compatibility)
# ============================================================================

@app.route('/network_data')
def legacy_network_data():
    """Legacy endpoint for network data"""
    return get_network()

@app.route('/list_credentials')
def legacy_credentials():
    """Legacy endpoint for credentials"""
    return get_credentials()

@app.route('/get_logs')
def legacy_logs():
    """Legacy endpoint for logs"""
    return get_logs()

@app.route('/netkb_data_json')
def legacy_netkb_json():
    """Legacy endpoint for network knowledge base JSON"""
    try:
        netkb_file = shared_data.netkbfile
        if not os.path.exists(netkb_file):
            return jsonify({'ips': [], 'ports': {}, 'actions': []})
            
        import pandas as pd
        df = pd.read_csv(netkb_file)
        data = df[df['Alive'] == 1] if 'Alive' in df.columns else df
        
        # Get available actions from actions file
        actions = []
        try:
            with open(shared_data.actions_file, 'r') as f:
                actions_config = json.load(f)
                actions = list(actions_config.keys())
        except Exception:
            pass
        
        response_data = {
            'ips': data['IPs'].tolist() if 'IPs' in data.columns else [],
            'ports': {row['IPs']: row['Ports'].split(';') for _, row in data.iterrows() if 'Ports' in row},
            'actions': actions
        }
        
        return jsonify(response_data)
    except Exception as e:
        logger.error(f"Error getting netkb JSON: {e}")
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
    
    # Send initial data to new client
    try:
        status_data = get_current_status()
        emit('status_update', status_data)
        
        # Send recent logs
        logs = get_recent_logs()
        emit('log_update', logs)
    except Exception as e:
        logger.error(f"Error sending initial data: {e}")


@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    global clients_connected
    clients_connected = max(0, clients_connected - 1)
    logger.info(f"Client disconnected. Total clients: {clients_connected}")


@socketio.on('request_status')
def handle_status_request():
    """Handle status update request"""
    try:
        status_data = get_current_status()
        emit('status_update', status_data)
    except Exception as e:
        logger.error(f"Error handling status request: {e}")


@socketio.on('request_logs')
def handle_log_request():
    """Handle request for recent logs"""
    try:
        logs = get_recent_logs()
        emit('log_update', logs)
    except Exception as e:
        logger.error(f"Error sending logs: {e}")


@socketio.on('request_network')
def handle_network_request():
    """Handle request for network data"""
    try:
        data = shared_data.read_data()
        emit('network_update', data)
    except Exception as e:
        logger.error(f"Error sending network data: {e}")


@socketio.on('request_credentials')
def handle_credentials_request():
    """Handle request for credentials data"""
    try:
        credentials = web_utils.get_all_credentials()
        emit('credentials_update', credentials)
    except Exception as e:
        logger.error(f"Error sending credentials: {e}")


@socketio.on('request_loot')
def handle_loot_request():
    """Handle request for loot data"""
    try:
        loot = web_utils.get_loot_data()
        emit('loot_update', loot)
    except Exception as e:
        logger.error(f"Error sending loot data: {e}")


# ============================================================================
# BACKGROUND TASKS
# ============================================================================

def get_current_status():
    """Get current status data"""
    return {
        'bjorn_status': safe_str(shared_data.bjornstatustext),
        'bjorn_status2': safe_str(shared_data.bjornstatustext2),
        'bjorn_says': safe_str(shared_data.bjornsays),
        'orchestrator_status': safe_str(shared_data.bjornorch_status),
        'target_count': safe_int(shared_data.targetnbr),
        'port_count': safe_int(shared_data.portnbr),
        'vulnerability_count': safe_int(shared_data.vulnnbr),
        'credential_count': safe_int(shared_data.crednbr),
        'data_count': safe_int(shared_data.datanbr),
        'wifi_connected': safe_bool(shared_data.wifi_connected),
        'bluetooth_active': safe_bool(shared_data.bluetooth_active),
        'pan_connected': safe_bool(shared_data.pan_connected),
        'usb_active': safe_bool(shared_data.usb_active),
        'manual_mode': safe_bool(shared_data.config.get('manual_mode', False)),
        'timestamp': datetime.now().isoformat()
    }

def get_recent_logs():
    """Get recent log entries"""
    logs = []
    try:
        log_file = shared_data.webconsolelog
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                # Return last 50 lines
                logs = [line.strip() for line in lines[-50:] if line.strip()]
    except Exception as e:
        logger.error(f"Error reading logs: {e}")
    return logs

def broadcast_status_updates():
    """Broadcast status updates to all connected clients"""
    log_counter = 0
    while not shared_data.webapp_should_exit:
        try:
            if clients_connected > 0:
                # Send status update
                status_data = get_current_status()
                socketio.emit('status_update', status_data)
                
                # Send logs every 5 cycles (10 seconds)
                log_counter += 1
                if log_counter % 5 == 0:
                    logs = get_recent_logs()
                    socketio.emit('log_update', logs)
            
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
