// bjorn_modern.js - Enhanced Modern JavaScript for Bjorn web interface

let socket;
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 5;
let currentTab = 'dashboard';
let autoRefreshIntervals = {};

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    initializeSocket();
    initializeTabs();
    initializeMobileMenu();
    loadInitialData();
    setupAutoRefresh();
    setupEpaperAutoRefresh();
    setupEventListeners();
});

// ============================================================================
// WEBSOCKET CONNECTION
// ============================================================================

function initializeSocket() {
    socket = io({
        reconnection: true,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 5000,
        reconnectionAttempts: MAX_RECONNECT_ATTEMPTS
    });

    socket.on('connect', function() {
        console.log('Connected to Bjorn server');
        updateConnectionStatus(true);
        reconnectAttempts = 0;
        addConsoleMessage('Connected to Bjorn server', 'success');
        
        // Request initial data
        socket.emit('request_status');
        socket.emit('request_logs');
    });

    socket.on('disconnect', function() {
        console.log('Disconnected from Bjorn server');
        updateConnectionStatus(false);
        addConsoleMessage('Disconnected from server', 'error');
    });

    socket.on('status_update', function(data) {
        updateDashboardStatus(data);
    });

    socket.on('log_update', function(logs) {
        updateConsole(logs);
    });

    socket.on('network_update', function(data) {
        if (currentTab === 'network') {
            displayNetworkTable(data);
        }
    });

    socket.on('credentials_update', function(data) {
        if (currentTab === 'credentials') {
            displayCredentialsTable(data);
        }
    });

    socket.on('loot_update', function(data) {
        if (currentTab === 'loot') {
            displayLootTable(data);
        }
    });

    socket.on('config_updated', function(config) {
        addConsoleMessage('Configuration updated successfully', 'info');
        if (currentTab === 'config') {
            displayConfigForm(config);
        }
    });

    socket.on('connect_error', function(error) {
        reconnectAttempts++;
        console.error('Connection error:', error);
        if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
            addConsoleMessage('Failed to connect to server after multiple attempts', 'error');
        }
    });
}

function updateConnectionStatus(connected) {
    const statusEl = document.getElementById('connection-status');
    if (statusEl) {
        if (connected) {
            statusEl.innerHTML = `
                <span class="w-2 h-2 bg-green-500 rounded-full pulse-glow"></span>
                <span class="text-xs text-gray-400">Connected</span>
            `;
        } else {
            statusEl.innerHTML = `
                <span class="w-2 h-2 bg-red-500 rounded-full"></span>
                <span class="text-xs text-gray-400">Disconnected</span>
            `;
        }
    }
}

// ============================================================================
// EVENT LISTENERS
// ============================================================================

function setupEventListeners() {
    // Tab navigation
    document.querySelectorAll('[data-tab]').forEach(button => {
        button.addEventListener('click', function() {
            const tabName = this.getAttribute('data-tab');
            showTab(tabName);
        });
    });

    // Refresh buttons
    document.addEventListener('click', function(e) {
        if (e.target.classList.contains('refresh-btn')) {
            refreshCurrentTab();
        }
    });

    // Clear console button
    const clearBtn = document.getElementById('clear-console');
    if (clearBtn) {
        clearBtn.addEventListener('click', clearConsole);
    }
}

// ============================================================================
// TAB MANAGEMENT
// ============================================================================

function initializeTabs() {
    // Set dashboard as active by default
    showTab('dashboard');
}

function showTab(tabName) {
    // Store current tab
    currentTab = tabName;
    
    // Hide all tabs
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.add('hidden');
    });
    
    // Remove active class from all nav buttons
    document.querySelectorAll('.nav-btn, [data-tab]').forEach(btn => {
        btn.classList.remove('bg-bjorn-600');
        btn.classList.add('text-gray-300', 'hover:text-white', 'hover:bg-gray-700');
    });
    
    // Show selected tab
    const selectedTab = document.getElementById(`${tabName}-tab`);
    if (selectedTab) {
        selectedTab.classList.remove('hidden');
    }
    
    // Add active class to selected nav button
    const selectedBtn = document.querySelector(`[data-tab="${tabName}"]`);
    if (selectedBtn) {
        selectedBtn.classList.add('bg-bjorn-600');
        selectedBtn.classList.remove('text-gray-300', 'hover:text-white', 'hover:bg-gray-700');
    }
    
    // Load tab-specific data
    loadTabData(tabName);
    
    // Close mobile menu
    const mobileMenu = document.getElementById('mobile-menu');
    if (mobileMenu) {
        mobileMenu.classList.add('hidden');
    }
}

function refreshCurrentTab() {
    loadTabData(currentTab);
    addConsoleMessage(`Refreshed ${currentTab} data`, 'info');
}

function setupAutoRefresh() {
    // Set up auto-refresh for different tabs
    autoRefreshIntervals.network = setInterval(() => {
        if (currentTab === 'network' && socket && socket.connected) {
            socket.emit('request_network');
        }
    }, 10000); // Every 10 seconds

    autoRefreshIntervals.credentials = setInterval(() => {
        if (currentTab === 'credentials' && socket && socket.connected) {
            socket.emit('request_credentials');
        }
    }, 15000); // Every 15 seconds

    autoRefreshIntervals.loot = setInterval(() => {
        if (currentTab === 'loot' && socket && socket.connected) {
            socket.emit('request_loot');
        }
    }, 20000); // Every 20 seconds
    
    // Set up console log refreshing (fallback when WebSocket is not working)
    autoRefreshIntervals.console = setInterval(() => {
        if (currentTab === 'dashboard') {
            loadConsoleLogs();
        }
    }, 5000); // Every 5 seconds when on dashboard
    
    // Set up periodic update checking
    autoRefreshIntervals.updates = setInterval(() => {
        checkForUpdatesQuiet();
    }, 300000); // Every 5 minutes
    
    // Initial update check after page load
    setTimeout(() => {
        checkForUpdatesQuiet();
    }, 5000); // Check 5 seconds after page load
}

function initializeMobileMenu() {
    const menuBtn = document.getElementById('mobile-menu-btn');
    const mobileMenu = document.getElementById('mobile-menu');
    
    if (menuBtn && mobileMenu) {
        menuBtn.addEventListener('click', () => {
            mobileMenu.classList.toggle('hidden');
        });
    }
}

// ============================================================================
// DATA LOADING
// ============================================================================

async function loadInitialData() {
    try {
        // Load status
        const status = await fetchAPI('/api/status');
        if (status) {
            updateDashboardStatus(status);
        }
        
        // Load initial console logs
        await loadConsoleLogs();
        
        // Add welcome message to console
        addConsoleMessage('Bjorn Modern Web Interface Initialized', 'success');
        addConsoleMessage('Dashboard loaded successfully', 'info');
        
    } catch (error) {
        console.error('Error loading initial data:', error);
        addConsoleMessage('Error loading initial data', 'error');
    }
}

async function loadTabData(tabName) {
    switch(tabName) {
        case 'dashboard':
            await loadConsoleLogs();
            break;
        case 'network':
            await loadNetworkData();
            break;
        case 'credentials':
            await loadCredentialsData();
            break;
        case 'loot':
            await loadLootData();
            break;
        case 'epaper':
            await loadEpaperDisplay();
            break;
        case 'config':
            await loadConfigData();
            break;
    }
}

async function loadNetworkData() {
    try {
        const data = await fetchAPI('/api/network');
        displayNetworkTable(data);
    } catch (error) {
        console.error('Error loading network data:', error);
    }
}

async function loadCredentialsData() {
    try {
        const data = await fetchAPI('/api/credentials');
        displayCredentialsTable(data);
    } catch (error) {
        console.error('Error loading credentials:', error);
    }
}

async function loadLootData() {
    try {
        const data = await fetchAPI('/api/loot');
        displayLootTable(data);
    } catch (error) {
        console.error('Error loading loot data:', error);
    }
}

async function loadConfigData() {
    try {
        const config = await fetchAPI('/api/config');
        displayConfigForm(config);
        
        // Also check for updates when loading config tab
        checkForUpdates();
    } catch (error) {
        console.error('Error loading config:', error);
    }
}

// ============================================================================
// SYSTEM MANAGEMENT FUNCTIONS
// ============================================================================

async function checkForUpdates() {
    try {
        updateElement('update-status', 'Checking...');
        updateElement('update-info', 'Checking for updates...');
        addConsoleMessage('Checking for system updates...', 'info');
        
        const data = await fetchAPI('/api/system/check-updates');
        
        if (data.updates_available) {
            updateElement('update-status', 'Update Available');
            document.getElementById('update-status').className = 'text-sm px-2 py-1 rounded bg-orange-700 text-orange-300';
            updateElement('update-info', `${data.commits_behind} commits behind. Latest: ${data.latest_commit || 'Unknown'}`);
            
            // Enable update button
            const updateBtn = document.getElementById('update-btn');
            updateBtn.disabled = false;
            updateBtn.className = 'w-full bg-green-600 hover:bg-green-700 text-white py-2 px-4 rounded transition-colors';
            
            addConsoleMessage(`Update available: ${data.commits_behind} commits behind`, 'warning');
        } else {
            updateElement('update-status', 'Up to Date');
            document.getElementById('update-status').className = 'text-sm px-2 py-1 rounded bg-green-700 text-green-300';
            updateElement('update-info', 'System is up to date');
            
            // Disable update button
            const updateBtn = document.getElementById('update-btn');
            updateBtn.disabled = true;
            updateBtn.className = 'w-full bg-gray-600 text-white py-2 px-4 rounded cursor-not-allowed';
            
            addConsoleMessage('System is up to date', 'success');
        }
        
    } catch (error) {
        console.error('Error checking for updates:', error);
        updateElement('update-status', 'Error');
        document.getElementById('update-status').className = 'text-sm px-2 py-1 rounded bg-red-700 text-red-300';
        updateElement('update-info', 'Failed to check for updates');
        addConsoleMessage('Failed to check for updates', 'error');
    }
}

async function performUpdate() {
    if (!confirm('This will update the system and restart the service. Continue?')) {
        return;
    }
    
    try {
        updateElement('update-btn-text', 'Updating...');
        const updateBtn = document.getElementById('update-btn');
        updateBtn.disabled = true;
        updateBtn.className = 'w-full bg-gray-600 text-white py-2 px-4 rounded cursor-not-allowed';
        
        addConsoleMessage('Starting system update...', 'info');
        
        const data = await postAPI('/api/system/update', {});
        
        if (data.success) {
            addConsoleMessage('Update completed successfully', 'success');
            addConsoleMessage('System will restart automatically...', 'info');
            updateElement('update-info', 'Update completed. System restarting...');
            
            // Check for updates again after a delay
            setTimeout(() => {
                checkForUpdates();
            }, 30000); // Check again in 30 seconds
        } else {
            addConsoleMessage(`Update failed: ${data.error || 'Unknown error'}`, 'error');
            updateElement('update-btn-text', 'Update System');
            updateBtn.disabled = false;
            updateBtn.className = 'w-full bg-green-600 hover:bg-green-700 text-white py-2 px-4 rounded transition-colors';
        }
        
    } catch (error) {
        console.error('Error performing update:', error);
        addConsoleMessage('Update failed due to network error', 'error');
        updateElement('update-btn-text', 'Update System');
        const updateBtn = document.getElementById('update-btn');
        updateBtn.disabled = false;
        updateBtn.className = 'w-full bg-green-600 hover:bg-green-700 text-white py-2 px-4 rounded transition-colors';
    }
}

async function checkForUpdatesQuiet() {
    try {
        const data = await fetchAPI('/api/system/check-updates');
        
        if (data.updates_available && data.commits_behind > 0) {
            // Show update notification in console if not on config tab
            if (currentTab !== 'config') {
                addConsoleMessage(`🔄 System update available: ${data.commits_behind} commits behind`, 'warning');
            }
            
            // Add visual indicator to config tab
            const configTabBtn = document.querySelector('[data-tab="config"]');
            if (configTabBtn && !configTabBtn.querySelector('.update-indicator')) {
                const indicator = document.createElement('span');
                indicator.className = 'update-indicator absolute -top-1 -right-1 w-3 h-3 bg-orange-500 rounded-full pulse-glow';
                configTabBtn.style.position = 'relative';
                configTabBtn.appendChild(indicator);
            }
        } else {
            // Remove update indicator if up to date
            const configTabBtn = document.querySelector('[data-tab="config"]');
            const indicator = configTabBtn?.querySelector('.update-indicator');
            if (indicator) {
                indicator.remove();
            }
        }
        
    } catch (error) {
        // Silently fail for background checks
        console.debug('Background update check failed:', error);
    }
}

async function restartService() {
    if (!confirm('This will restart the Bjorn service. The web interface may be temporarily unavailable. Continue?')) {
        return;
    }
    
    try {
        addConsoleMessage('Restarting Bjorn service...', 'info');
        updateElement('service-status', 'Restarting...');
        document.getElementById('service-status').className = 'text-sm px-2 py-1 rounded bg-yellow-700 text-yellow-300';
        
        const data = await postAPI('/api/system/restart-service', {});
        
        if (data.success) {
            addConsoleMessage('Service restart initiated', 'success');
            addConsoleMessage('Service will be back online shortly...', 'info');
            
            // Update status after delay
            setTimeout(() => {
                updateElement('service-status', 'Running');
                document.getElementById('service-status').className = 'text-sm px-2 py-1 rounded bg-green-700 text-green-300';
                addConsoleMessage('Service restart completed', 'success');
            }, 10000); // 10 seconds delay
        } else {
            addConsoleMessage(`Service restart failed: ${data.error || 'Unknown error'}`, 'error');
            updateElement('service-status', 'Error');
            document.getElementById('service-status').className = 'text-sm px-2 py-1 rounded bg-red-700 text-red-300';
        }
        
    } catch (error) {
        console.error('Error restarting service:', error);
        addConsoleMessage('Failed to restart service', 'error');
        updateElement('service-status', 'Error');
        document.getElementById('service-status').className = 'text-sm px-2 py-1 rounded bg-red-700 text-red-300';
    }
}

async function rebootSystem() {
    if (!confirm('This will reboot the entire system. The device will be offline for several minutes. Continue?')) {
        return;
    }
    
    try {
        addConsoleMessage('Initiating system reboot...', 'warning');
        
        const data = await postAPI('/api/system/reboot', {});
        
        if (data.success) {
            addConsoleMessage('System reboot initiated', 'success');
            addConsoleMessage('Device will be offline for several minutes...', 'warning');
            
            // Update connection status
            updateConnectionStatus(false);
        } else {
            addConsoleMessage(`Reboot failed: ${data.error || 'Unknown error'}`, 'error');
        }
        
    } catch (error) {
        console.error('Error rebooting system:', error);
        addConsoleMessage('Failed to initiate system reboot', 'error');
    }
}

async function loadConsoleLogs() {
    try {
        const data = await fetchAPI('/api/logs');
        if (data && data.logs) {
            updateConsole(data.logs);
        }
    } catch (error) {
        console.error('Error loading console logs:', error);
        // Add fallback console messages if log loading fails
        addConsoleMessage('Unable to load historical logs from server', 'warning');
        addConsoleMessage('Console will show new messages as they occur', 'info');
    }
}

// ============================================================================
// API HELPERS
// ============================================================================

async function fetchAPI(endpoint) {
    try {
        const response = await fetch(endpoint);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.error(`Error fetching ${endpoint}:`, error);
        throw error;
    }
}

async function postAPI(endpoint, data) {
    try {
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data)
        });
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.error(`Error posting to ${endpoint}:`, error);
        throw error;
    }
}

// ============================================================================
// DASHBOARD UPDATES
// ============================================================================

function updateDashboardStatus(data) {
    // Update counters
    updateElement('target-count', data.target_count || 0);
    updateElement('port-count', data.port_count || 0);
    updateElement('vuln-count', data.vulnerability_count || 0);
    updateElement('cred-count', data.credential_count || 0);
    
    // Update status - use the actual e-paper display text
    updateElement('bjorn-status', data.bjorn_status || 'IDLE');
    updateElement('bjorn-says', (data.bjorn_status2 || data.bjorn_status || 'Awakening...'));
    updateElement('bjorn-mode', data.manual_mode ? 'Manual' : 'Auto');
    
    // Update connectivity status
    updateConnectivityIndicator('wifi-status', data.wifi_connected);
    updateConnectivityIndicator('bluetooth-status', data.bluetooth_active);
    updateConnectivityIndicator('usb-status', data.usb_active);
    updateConnectivityIndicator('pan-status', data.pan_connected);
}

function updateElement(id, value) {
    const element = document.getElementById(id);
    if (element) {
        element.textContent = value;
    }
}

function updateConnectivityIndicator(id, active) {
    const element = document.getElementById(id);
    if (element) {
        if (active) {
            element.className = 'w-3 h-3 bg-green-500 rounded-full pulse-glow';
        } else {
            element.className = 'w-3 h-3 bg-gray-600 rounded-full';
        }
    }
}

// ============================================================================
// CONSOLE
// ============================================================================

let consoleBuffer = [];
const MAX_CONSOLE_LINES = 200;

function addConsoleMessage(message, type = 'info') {
    const timestamp = new Date().toLocaleTimeString();
    const colors = {
        'success': 'text-green-400',
        'error': 'text-red-400',
        'warning': 'text-yellow-400',
        'info': 'text-blue-400'
    };
    
    const colorClass = colors[type] || colors['info'];
    const logEntry = {
        timestamp,
        message,
        type,
        colorClass
    };
    
    consoleBuffer.push(logEntry);
    
    // Keep only the last MAX_CONSOLE_LINES
    if (consoleBuffer.length > MAX_CONSOLE_LINES) {
        consoleBuffer = consoleBuffer.slice(-MAX_CONSOLE_LINES);
    }
    
    updateConsoleDisplay();
}

function updateConsole(logs) {
    if (!logs || !Array.isArray(logs)) {
        // If no logs available, add informational messages
        if (consoleBuffer.length === 0) {
            addConsoleMessage('No historical logs available', 'warning');
            addConsoleMessage('New activity will appear here as it occurs', 'info');
        }
        return;
    }
    
    // If logs are empty array, provide user feedback
    if (logs.length === 0) {
        if (consoleBuffer.length === 0) {
            addConsoleMessage('No recent activity logged', 'info');
            addConsoleMessage('Waiting for new events...', 'info');
        }
        return;
    }
    
    // Clear existing buffer and add new logs
    consoleBuffer = [];
    
    logs.forEach(log => {
        // Skip empty lines
        if (!log.trim()) return;
        
        let type = 'info';
        if (log.includes('ERROR') || log.includes('Error') || log.includes('error')) type = 'error';
        else if (log.includes('WARN') || log.includes('Warning') || log.includes('warning')) type = 'warning';
        else if (log.includes('INFO') || log.includes('Info')) type = 'info';
        else if (log.includes('DEBUG') || log.includes('Debug')) type = 'info';
        else if (log.includes('SUCCESS') || log.includes('Success')) type = 'success';
        
        const timestamp = new Date().toLocaleTimeString();
        const colors = {
            'success': 'text-green-400',
            'error': 'text-red-400',
            'warning': 'text-yellow-400',
            'info': 'text-gray-300'
        };
        
        consoleBuffer.push({
            timestamp,
            message: log.trim(),
            type,
            colorClass: colors[type]
        });
    });
    
    updateConsoleDisplay();
}

function updateConsoleDisplay() {
    const console = document.getElementById('console-output');
    if (!console) return;
    
    console.innerHTML = consoleBuffer.map(entry => 
        `<div class="${entry.colorClass}">[${entry.timestamp}] ${escapeHtml(entry.message)}</div>`
    ).join('');
    
    // Auto-scroll to bottom
    console.scrollTop = console.scrollHeight;
}

function clearConsole() {
    consoleBuffer = [];
    const console = document.getElementById('console-output');
    if (console) {
        console.innerHTML = '<div class="text-green-400">Console cleared</div>';
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ============================================================================
// TABLE DISPLAYS
// ============================================================================

function displayNetworkTable(data) {
    const container = document.getElementById('network-table');
    if (!container) return;
    
    if (!data || data.length === 0) {
        container.innerHTML = '<p class="text-gray-400">No network data available</p>';
        return;
    }
    
    let html = `
        <div class="overflow-x-auto">
            <table class="min-w-full divide-y divide-gray-700">
                <thead class="bg-gray-800">
                    <tr>
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider">IP Address</th>
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider">Hostname</th>
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider">MAC Address</th>
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider">Status</th>
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider">Open Ports</th>
                    </tr>
                </thead>
                <tbody class="bg-gray-900 divide-y divide-gray-700">
    `;
    
    data.forEach(item => {
        const status = item.Alive === '1' ? 'Online' : 'Offline';
        const statusColor = item.Alive === '1' ? 'text-green-400' : 'text-gray-400';
        const ports = item.Ports ? item.Ports.split(';').filter(p => p.trim()).join(', ') : 'None';
        
        html += `
            <tr class="hover:bg-gray-800 transition-colors">
                <td class="px-6 py-4 whitespace-nowrap text-sm text-white">${item.IPs || 'N/A'}</td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">${item.Hostname || '-'}</td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300 font-mono">${item['MAC Address'] || '-'}</td>
                <td class="px-6 py-4 whitespace-nowrap text-sm ${statusColor}">${status}</td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">${ports}</td>
            </tr>
        `;
    });
    
    html += '</tbody></table></div>';
    container.innerHTML = html;
}

function displayCredentialsTable(data) {
    const container = document.getElementById('credentials-table');
    if (!container) return;
    
    if (!data || Object.keys(data).length === 0) {
        container.innerHTML = '<p class="text-gray-400">No credentials discovered yet</p>';
        return;
    }
    
    let html = '<div class="space-y-6">';
    
    Object.entries(data).forEach(([service, creds]) => {
        if (creds && creds.length > 0) {
            html += `
                <div class="bg-gray-800 rounded-lg p-4">
                    <h3 class="text-lg font-semibold text-bjorn-400 mb-3">${service.toUpperCase()} (${creds.length})</h3>
                    <div class="overflow-x-auto">
                        <table class="min-w-full divide-y divide-gray-700">
                            <thead>
                                <tr>
                                    <th class="px-4 py-2 text-left text-xs font-medium text-gray-300 uppercase">Target</th>
                                    <th class="px-4 py-2 text-left text-xs font-medium text-gray-300 uppercase">Username</th>
                                    <th class="px-4 py-2 text-left text-xs font-medium text-gray-300 uppercase">Password</th>
                                </tr>
                            </thead>
                            <tbody class="divide-y divide-gray-700">
            `;
            
            creds.forEach(cred => {
                html += `
                    <tr class="hover:bg-gray-700 transition-colors">
                        <td class="px-4 py-2 text-sm text-white">${cred.ip || 'N/A'}</td>
                        <td class="px-4 py-2 text-sm text-green-400 font-mono">${cred.username || 'N/A'}</td>
                        <td class="px-4 py-2 text-sm text-yellow-400 font-mono">${cred.password || 'N/A'}</td>
                    </tr>
                `;
            });
            
            html += `
                            </tbody>
                        </table>
                    </div>
                </div>
            `;
        }
    });
    
    html += '</div>';
    
    if (html === '<div class="space-y-6"></div>') {
        container.innerHTML = '<p class="text-gray-400">No credentials discovered yet</p>';
    } else {
        container.innerHTML = html;
    }
}

function displayLootTable(data) {
    const container = document.getElementById('loot-table');
    if (!container) return;
    
    if (!data || data.length === 0) {
        container.innerHTML = '<p class="text-gray-400">No loot data available</p>';
        return;
    }
    
    let html = `<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">`;
    
    data.forEach(item => {
        html += `
            <div class="bg-gray-800 rounded-lg p-4 hover:bg-gray-700 transition-colors">
                <div class="flex items-center justify-between mb-2">
                    <h3 class="text-lg font-semibold text-bjorn-400 truncate" title="${item.filename || 'Unknown File'}">${item.filename || 'Unknown File'}</h3>
                    <span class="text-xs text-gray-400 ml-2">${item.size || 'N/A'}</span>
                </div>
                <div class="space-y-2 text-sm text-gray-300">
                    <p><span class="text-gray-400">Source:</span> ${item.source || 'Unknown'}</p>
                    <p><span class="text-gray-400">Timestamp:</span> ${item.timestamp || 'Unknown'}</p>
                </div>
            </div>
        `;
    });
    
    html += '</div>';
    container.innerHTML = html;
}

function displayConfigForm(config) {
    const container = document.getElementById('config-form');
    
    let html = '<div class="space-y-6"><form id="config-update-form">';
    
    // Group config by sections
    const sections = {
        'General': ['manual_mode', 'websrv', 'debug_mode', 'web_increment', 'blacklistcheck'],
        'Timing': ['startup_delay', 'web_delay', 'screen_delay', 'scan_interval'],
        'Display': ['epd_type', 'ref_width', 'ref_height']
    };
    
    for (const [sectionName, keys] of Object.entries(sections)) {
        html += `
            <div class="bg-slate-800 bg-opacity-50 rounded-lg p-4">
                <h3 class="text-lg font-bold mb-4 text-bjorn-400">${sectionName}</h3>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        `;
        
        keys.forEach(key => {
            if (config.hasOwnProperty(key)) {
                const value = config[key];
                const type = typeof value === 'boolean' ? 'checkbox' : 'text';
                
                if (type === 'checkbox') {
                    html += `
                        <label class="flex items-center space-x-3 p-3 rounded-lg hover:bg-slate-700 hover:bg-opacity-50 transition-colors cursor-pointer">
                            <input type="checkbox" name="${key}" ${value ? 'checked' : ''} 
                                   class="w-5 h-5 rounded bg-slate-700 border-slate-600 text-bjorn-500 focus:ring-bjorn-500">
                            <span>${key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</span>
                        </label>
                    `;
                } else {
                    html += `
                        <div class="space-y-2">
                            <label class="block text-sm text-gray-400">
                                ${key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                            </label>
                            <input type="${type}" name="${key}" value="${value}"
                                   class="w-full px-4 py-2 rounded-lg bg-slate-700 border border-slate-600 focus:border-bjorn-500 focus:ring-1 focus:ring-bjorn-500">
                        </div>
                    `;
                }
            }
        });
        
        html += '</div></div>';
    }
    
    html += `
        <button type="submit" class="w-full bg-bjorn-600 hover:bg-bjorn-700 text-white font-bold py-3 px-6 rounded-lg transition-colors">
            Save Configuration
        </button>
    </form></div>`;
    
    container.innerHTML = html;
    
    // Add form submit handler
    document.getElementById('config-update-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        await saveConfig(e.target);
    });
}

async function saveConfig(form) {
    const formData = new FormData(form);
    const config = {};
    
    // Get all form values
    for (const [key, value] of formData.entries()) {
        // Convert checkbox values to boolean
        const input = form.elements[key];
        if (input.type === 'checkbox') {
            config[key] = input.checked;
        } else if (!isNaN(value) && value !== '') {
            config[key] = Number(value);
        } else {
            config[key] = value;
        }
    }
    
    try {
        const result = await postAPI('/api/config', config);
        addConsoleMessage('Configuration saved successfully', 'success');
    } catch (error) {
        addConsoleMessage('Failed to save configuration', 'error');
    }
}

// E-Paper Display Functions
async function loadEpaperDisplay() {
    try {
        const data = await fetchAPI('/api/epaper-display');
        
        // Update status text
        updateElement('epaper-status-1', data.status_text || 'Unknown');
        updateElement('epaper-status-2', data.status_text2 || 'Unknown');
        
        // Update timestamp
        if (data.timestamp) {
            const date = new Date(data.timestamp * 1000);
            updateElement('epaper-timestamp', date.toLocaleString());
        }
        
        // Update display image
        const imgElement = document.getElementById('epaper-display-image');
        const loadingElement = document.getElementById('epaper-loading');
        const connectionElement = document.getElementById('epaper-connection');
        
        if (data.image) {
            imgElement.src = data.image;
            imgElement.style.display = 'block';
            loadingElement.style.display = 'none';
            
            // Update resolution info
            if (data.width && data.height) {
                updateElement('epaper-resolution', `${data.width} x ${data.height}`);
            }
            
            // Update connection status
            connectionElement.textContent = 'Live';
            connectionElement.className = 'text-green-400 font-medium';
        } else {
            imgElement.style.display = 'none';
            loadingElement.style.display = 'flex';
            loadingElement.innerHTML = `
                <div class="text-center text-gray-600">
                    <svg class="h-8 w-8 mx-auto mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                    </svg>
                    <p>${data.message || 'No display image available'}</p>
                </div>
            `;
            
            // Update connection status
            connectionElement.textContent = 'Offline';
            connectionElement.className = 'text-red-400 font-medium';
        }
        
    } catch (error) {
        console.error('Error loading e-paper display:', error);
        addConsoleMessage('Failed to load e-paper display', 'error');
        
        // Update connection status
        const connectionElement = document.getElementById('epaper-connection');
        connectionElement.textContent = 'Error';
        connectionElement.className = 'text-red-400 font-medium';
    }
}

function refreshEpaperDisplay() {
    addConsoleMessage('Refreshing e-paper display...', 'info');
    loadEpaperDisplay();
}

// E-Paper display size toggle functionality
let epaperSizeMode = 'large'; // default to large size
function toggleEpaperSize() {
    const imgElement = document.getElementById('epaper-display-image');
    
    if (epaperSizeMode === 'large') {
        // Switch to extra large
        imgElement.style.maxHeight = '1200px';
        imgElement.style.minHeight = '600px';
        epaperSizeMode = 'xlarge';
        addConsoleMessage('E-paper display size: Extra Large', 'info');
    } else if (epaperSizeMode === 'xlarge') {
        // Switch to medium
        imgElement.style.maxHeight = '600px';
        imgElement.style.minHeight = '300px';
        epaperSizeMode = 'medium';
        addConsoleMessage('E-paper display size: Medium', 'info');
    } else {
        // Switch back to large
        imgElement.style.maxHeight = '800px';
        imgElement.style.minHeight = '400px';
        epaperSizeMode = 'large';
        addConsoleMessage('E-paper display size: Large', 'info');
    }
}

// Add e-paper display to auto-refresh
function setupEpaperAutoRefresh() {
    setInterval(() => {
        if (currentTab === 'epaper') {
            loadEpaperDisplay();
        }
    }, 5000); // Refresh every 5 seconds when on e-paper tab
}

// ============================================================================
// GLOBAL FUNCTION EXPORTS (for HTML onclick handlers)
// ============================================================================

// Make functions available globally for HTML onclick handlers
window.loadConsoleLogs = loadConsoleLogs;
window.clearConsole = clearConsole;
window.refreshEpaperDisplay = refreshEpaperDisplay;
window.toggleEpaperSize = toggleEpaperSize;
window.checkForUpdates = checkForUpdates;
window.checkForUpdatesQuiet = checkForUpdatesQuiet;
window.performUpdate = performUpdate;
window.restartService = restartService;
window.rebootSystem = rebootSystem;
