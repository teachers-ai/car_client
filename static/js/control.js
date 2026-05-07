// WebSocket connection to Flask-SocketIO server
const socket = io();

// Global state
let connections = [];
let currentSpeed = { movement_speed: 0.5, rotation_speed: 0.5 };
let serverConnected = false;

// Image capture state
let currentCaptureFilename = null;
let autoCaptureEnabled = false;

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    checkStatus();
    setupKeyboardControls();
    setupSocketListeners();
    loadCapturedImages();
    checkModelStatus();
    loadAvailableModels();
    initAutoCapture();
});

// Setup Socket.IO event listeners
function setupSocketListeners() {
    socket.on('connect', function() {
        // Don't update car server connection status here
        // Socket.IO connects to Flask client, not the car server
        console.log('Connected to Flask client server');
    });

    socket.on('disconnect', function() {
        // Don't update car server connection status here
        console.log('Disconnected from Flask client server');
    });

    socket.on('connection_list', function(data) {
        console.log('Received connection list:', data);
        connections = data;
        updateConnectionsList(data);
    });

    socket.on('control_status', function(data) {
        console.log('Received control status:', data);
        updateControllerStatus(data.controlling);
    });

    socket.on('speed_update', function(data) {
        console.log('Received speed update:', data);
        currentSpeed = data;
        updateSpeedSliders(data);
    });

    socket.on('training_progress', function(data) {
        console.log('Training progress:', data);
        updateTrainingProgress(data);
    });

    socket.on('training_complete', function(data) {
        console.log('Training complete:', data);
        document.getElementById('training-progress').style.display = 'none';
        document.getElementById('btn-train').disabled = false;
        showNotification('Training completed successfully!', 'success');
        checkModelStatus();
        loadAvailableModels();
    });

    socket.on('training_error', function(data) {
        console.error('Training error:', data);
        document.getElementById('training-progress').style.display = 'none';
        document.getElementById('btn-train').disabled = false;
        showNotification('Training failed: ' + data.error, 'error');
    });

    socket.on('autonomous_prediction', function(data) {
        console.log('Autonomous prediction:', data);
        updatePredictionDisplay(data);
    });
}

// Check server status
async function checkStatus() {
    try {
        const response = await fetch('/status');
        const data = await response.json();
        updateConnectionStatus(data.connected);

        // Update controller status
        if (data.connected && data.controlling !== undefined) {
            updateControllerStatus(data.controlling);
        }

        // Update server info display
        const currentServerSpan = document.getElementById('current-server');
        if (data.server && data.connected) {
            currentServerSpan.textContent = data.server.replace('http://', '');
        } else {
            currentServerSpan.textContent = 'Not connected';
        }

        if (data.current_speed) {
            currentSpeed = data.current_speed;
            updateSpeedSliders(data.current_speed);
        }

        // Also update speed from status if available
        if (data.move_speed !== undefined || data.turn_speed !== undefined) {
            updateSpeedSliders(data);
        }

        // Update connection info
        const connectionInfoText = document.getElementById('connection-info-text');
        if (connectionInfoText) {
            connectionInfoText.textContent = data.connected ? 'Connected & Ready' : 'Disconnected';
            connectionInfoText.style.color = data.connected ? '#4CAF50' : '#999';
        }
    } catch (error) {
        console.error('Failed to check status:', error);
        updateConnectionStatus(false);
    }
}

// Update connection status indicator
function updateConnectionStatus(connected) {
    const statusBadge = document.getElementById('connection-status');
    const statusText = document.getElementById('connection-status-text');
    const connectBtn = document.getElementById('btn-connect');
    const disconnectBtn = document.getElementById('btn-disconnect');
    const serverIpInput = document.getElementById('server-ip');
    const serverPortInput = document.getElementById('server-port');
    const currentServerSpan = document.getElementById('current-server');
    const controllerSection = document.getElementById('controller-section');

    serverConnected = connected;

    if (connected) {
        const serverAddress = `${serverIpInput.value}:${serverPortInput.value}`;

        statusBadge.textContent = 'Connected';
        statusBadge.className = 'status-badge connected';
        statusText.textContent = `Connected to ${serverAddress}`;
        statusText.className = 'connection-status-text connected';

        currentServerSpan.textContent = serverAddress;

        connectBtn.style.display = 'none';
        disconnectBtn.style.display = 'block';

        serverIpInput.disabled = true;
        serverPortInput.disabled = true;

        // Show controller section when connected
        if (controllerSection) {
            controllerSection.style.display = 'block';
        }
    } else {
        statusBadge.textContent = 'Disconnected';
        statusBadge.className = 'status-badge disconnected';
        statusText.textContent = 'Not connected to car server';
        statusText.className = 'connection-status-text disconnected';

        currentServerSpan.textContent = 'Not connected';

        connectBtn.style.display = 'block';
        disconnectBtn.style.display = 'none';

        serverIpInput.disabled = false;
        serverPortInput.disabled = false;

        // Hide controller section when disconnected
        if (controllerSection) {
            controllerSection.style.display = 'none';
        }
    }
}

// Update controller status indicator
function updateControllerStatus(controlling) {
    const controllerStatus = document.getElementById('controller-status');

    if (controllerStatus) {
        if (controlling) {
            controllerStatus.textContent = '✅ Controlling';
            controllerStatus.style.color = '#4CAF50';
        } else {
            controllerStatus.textContent = '❌ Not Controlling';
            controllerStatus.style.color = '#f44336';
        }
    }
}

// Connect to server
async function connectToServer() {
    const serverIp = document.getElementById('server-ip').value;
    const serverPort = document.getElementById('server-port').value;

    if (!serverIp || !serverPort) {
        showNotification('Please enter server IP and port', 'error');
        return;
    }

    try {
        showNotification('Connecting to server...', 'info');

        const response = await fetch('/connect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                server: serverIp,
                port: parseInt(serverPort)
            })
        });

        const data = await response.json();

        if (response.ok) {
            showNotification(`Connected to ${data.server} - Ready to drive!`, 'success');
            updateConnectionStatus(true);
        } else {
            showNotification('Failed to connect: ' + data.error, 'error');
            updateConnectionStatus(false);
        }
    } catch (error) {
        console.error('Connection error:', error);
        showNotification('Connection error: ' + error.message, 'error');
        updateConnectionStatus(false);
    }
}

// Disconnect from server
async function disconnectFromServer() {
    try {
        showNotification('Disconnecting from server...', 'info');

        const response = await fetch('/disconnect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        const data = await response.json();

        if (response.ok) {
            showNotification('Disconnected from server', 'success');
            updateConnectionStatus(false);
        } else {
            showNotification('Failed to disconnect: ' + data.error, 'error');
        }
    } catch (error) {
        console.error('Disconnect error:', error);
        showNotification('Disconnect error: ' + error.message, 'error');
    }
}

// Take control of the car
async function takeControl() {
    try {
        const response = await fetch('/take_control', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await response.json();

        if (response.ok) {
            console.log('Control requested');
            showNotification('Control requested. Waiting for confirmation...', 'info');

            // Check after 2 seconds if we got control
            setTimeout(async () => {
                const statusResponse = await fetch('/status');
                const statusData = await statusResponse.json();
                if (statusData.controlling) {
                    showNotification('Control acquired successfully!', 'success');
                } else {
                    showNotification('Control request rejected - another client may be controlling', 'warning');
                }
            }, 2000);
        } else {
            showNotification('Failed to take control: ' + data.error, 'error');
        }
    } catch (error) {
        console.error('Failed to take control:', error);
        showNotification('Failed to take control: ' + error.message, 'error');
    }
}

// Release control of the car
async function releaseControl() {
    try {
        const response = await fetch('/release_control', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await response.json();

        if (response.ok) {
            console.log('Control released');
            isControlling = false;
            updateControlStatus();
            showNotification('Control released', 'success');
        } else {
            showNotification('Failed to release control: ' + data.error, 'error');
        }
    } catch (error) {
        console.error('Failed to release control:', error);
        showNotification('Failed to release control: ' + error.message, 'error');
    }
}

// Send movement command
async function sendCommand(direction) {
    // Check if connected to server
    console.log('sendCommand called with direction:', direction, 'serverConnected:', serverConnected);

    if (!serverConnected) {
        showNotification('⚠️ You must connect to the server first!', 'warning');
        return;
    }

    try {
        const response = await fetch('/command', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ direction: direction })
        });

        console.log('Response status:', response.status, 'response.ok:', response.ok);
        const data = await response.json();
        console.log('Response data:', data);

        if (response.ok) {
            console.log('Command sent successfully:', direction);
            highlightButton(direction);

            // Auto-capture image with direction tag (only for movement commands, not STOP)
            if (direction !== 'S') {
                autoCaptureWithTag(direction);
            }
        } else {
            console.error('Command failed with status:', response.status, 'data:', data);
            showNotification('Failed to send command: ' + data.error, 'error');
        }
    } catch (error) {
        console.error('Failed to send command - exception:', error);
        showNotification('Failed to send command: ' + error.message, 'error');
    }
}

// Auto-capture image with direction tag
async function autoCaptureWithTag(direction) {
    // Check if auto-capture is enabled
    if (!autoCaptureEnabled) {
        console.log('Auto-capture disabled, skipping capture');
        return;
    }

    const directionNames = {
        'F': 'Forward',
        'B': 'Backward',
        'L': 'Left',
        'R': 'Right'
    };

    const tag = directionNames[direction] || direction;

    try {
        const response = await fetch('/capture_image', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tags: [tag] })
        });

        const data = await response.json();

        if (response.ok) {
            console.log('Auto-captured image with tag:', tag, '(bottom half)');
            loadCapturedImages(); // Refresh the image list
        } else {
            console.error('Auto-capture failed:', data.error);
        }
    } catch (error) {
        console.error('Auto-capture error:', error);
    }
}

// Initialize auto-capture checkbox
async function initAutoCapture() {
    try {
        // Get current auto-capture status from server
        const response = await fetch('/auto_capture');
        const data = await response.json();

        autoCaptureEnabled = data.auto_capture_enabled || false;

        // Set checkbox state
        const checkbox = document.getElementById('auto-capture-toggle');
        if (checkbox) {
            checkbox.checked = autoCaptureEnabled;
            // Add change event listener
            checkbox.addEventListener('change', toggleAutoCapture);
        }

        console.log('Auto-capture initialized:', autoCaptureEnabled);
    } catch (error) {
        console.error('Failed to initialize auto-capture:', error);
    }
}

// Toggle auto-capture on/off
async function toggleAutoCapture(event) {
    const enabled = event.target.checked;

    try {
        const response = await fetch('/auto_capture', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled: enabled })
        });

        const data = await response.json();
        autoCaptureEnabled = data.auto_capture_enabled;

        console.log('Auto-capture', autoCaptureEnabled ? 'enabled' : 'disabled');
        showNotification(
            `Auto-capture ${autoCaptureEnabled ? 'enabled' : 'disabled'} (bottom half)`,
            'success'
        );
    } catch (error) {
        console.error('Failed to toggle auto-capture:', error);
        // Revert checkbox on error
        event.target.checked = !enabled;
        showNotification('Failed to toggle auto-capture', 'error');
    }
}

// Set speed parameters
async function setSpeed() {
    const movementSpeed = document.getElementById('movement-speed').value / 100;
    const rotationSpeed = document.getElementById('rotation-speed').value / 100;

    try {
        const response = await fetch('/speed', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                movement_speed: movementSpeed,
                rotation_speed: rotationSpeed
            })
        });
        const data = await response.json();

        if (response.ok) {
            console.log('Speed set:', data);
            showNotification('Speed settings applied', 'success');
        } else {
            showNotification('Failed to set speed: ' + data.error, 'error');
        }
    } catch (error) {
        console.error('Failed to set speed:', error);
        showNotification('Failed to set speed: ' + error.message, 'error');
    }
}

// Drop a client by session ID
async function dropClient(sid) {
    if (!confirm('Are you sure you want to drop this client?')) {
        return;
    }

    try {
        const response = await fetch(`/drop/${sid}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await response.json();

        if (response.ok) {
            console.log('Client drop requested:', sid);
            showNotification('Client drop requested', 'success');
        } else {
            showNotification('Failed to drop client: ' + data.error, 'error');
        }
    } catch (error) {
        console.error('Failed to drop client:', error);
        showNotification('Failed to drop client: ' + error.message, 'error');
    }
}

// Update connections list display
function updateConnectionsList(connectionData) {
    const listContainer = document.getElementById('connections-list');

    // Handle the new format: {active_controller: 'sid', connections: [...]}
    let activeController = null;
    let connList = [];

    if (connectionData && typeof connectionData === 'object') {
        if (connectionData.active_controller !== undefined) {
            activeController = connectionData.active_controller;
            connList = connectionData.connections || [];
        } else if (Array.isArray(connectionData)) {
            connList = connectionData;
        }
    }

    if (!connList || connList.length === 0) {
        listContainer.innerHTML = '<p style="color: #999; text-align: center;">No connections</p>';
        return;
    }

    let html = '';
    connList.forEach(conn => {
        const isControllingCar = conn.is_controller || conn.sid === activeController;
        const controlClass = isControllingCar ? 'controlling' : '';
        const controlLabel = isControllingCar ? ' [CONTROLLING]' : '';

        html += `
            <div class="connection-item ${controlClass}">
                <div class="connection-info">
                    <div><strong>${conn.ip || 'Session'} ${controlLabel}</strong></div>
                    <div class="connection-sid">SID: ${conn.sid || 'Unknown'}</div>
                    <div style="font-size: 0.85em; color: #666;">Connected: ${conn.connected_at || 'Unknown'}</div>
                </div>
                ${conn.sid ?
                    `<button class="btn-drop" onclick="dropClient('${conn.sid}')">Drop</button>` :
                    ''}
            </div>
        `;
    });

    listContainer.innerHTML = html;
}

// Note: Control status is now tracked via 'control_status' event from server
// The server checks if its Socket.IO client (not the browser's) is the active controller

// Control status no longer used - removed

// Update speed display values
function updateSpeedDisplay() {
    const movementSpeed = document.getElementById('movement-speed').value;
    const rotationSpeed = document.getElementById('rotation-speed').value;

    document.getElementById('movement-speed-value').textContent = movementSpeed + '%';
    document.getElementById('rotation-speed-value').textContent = rotationSpeed + '%';
}

// Update speed sliders from server data
function updateSpeedSliders(speedData) {
    // Handle both old format (movement_speed/rotation_speed) and new format (move_speed/turn_speed)
    const moveSpeed = speedData.move_speed !== undefined ? speedData.move_speed : speedData.movement_speed;
    const turnSpeed = speedData.turn_speed !== undefined ? speedData.turn_speed : speedData.rotation_speed;

    if (moveSpeed !== undefined) {
        document.getElementById('movement-speed').value = moveSpeed * 100;
        document.getElementById('movement-speed-value').textContent =
            Math.round(moveSpeed * 100) + '%';
    }
    if (turnSpeed !== undefined) {
        document.getElementById('rotation-speed').value = turnSpeed * 100;
        document.getElementById('rotation-speed-value').textContent =
            Math.round(turnSpeed * 100) + '%';
    }
}

// Highlight button when pressed
function highlightButton(direction) {
    const buttonMap = {
        'F': 'btn-forward',
        'B': 'btn-back',
        'L': 'btn-left',
        'R': 'btn-right',
        'S': 'btn-stop'
    };

    const buttonId = buttonMap[direction];
    if (buttonId) {
        const button = document.getElementById(buttonId);
        button.style.transform = 'scale(0.95)';
        setTimeout(() => {
            button.style.transform = '';
        }, 200);
    }
}

// Show notification
function showNotification(message, type = 'info') {
    // Simple console notification for now
    console.log(`[${type.toUpperCase()}] ${message}`);

    // You can enhance this with a toast notification library if needed
    const colors = {
        success: '#4CAF50',
        error: '#f44336',
        warning: '#FF9800',
        info: '#2196F3'
    };

    const notification = document.createElement('div');
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: ${colors[type] || colors.info};
        color: white;
        padding: 15px 25px;
        border-radius: 8px;
        box-shadow: 0 5px 15px rgba(0,0,0,0.3);
        z-index: 10000;
        font-weight: bold;
        animation: slideIn 0.3s ease-out;
    `;
    notification.textContent = message;

    document.body.appendChild(notification);

    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease-out';
        setTimeout(() => {
            document.body.removeChild(notification);
        }, 300);
    }, 3000);
}

// Update training progress display
function updateTrainingProgress(data) {
    const progressContainer = document.getElementById('training-progress');
    const progressText = document.getElementById('training-status');

    if (progressContainer) {
        progressContainer.style.display = 'block';

        // Update progress text with epoch metrics
        if (progressText) {
            const statusText = `Epoch ${data.epoch}/${data.total_epochs} - ` +
                `Train Acc: ${(data.accuracy * 100).toFixed(2)}% | ` +
                `Val Acc: ${(data.val_accuracy * 100).toFixed(2)}%`;
            progressText.textContent = statusText;
        }
    }
}

// Keyboard controls
function setupKeyboardControls() {
    document.addEventListener('keydown', function(event) {
        // Ignore keyboard controls if user is typing in an input field
        if (event.target.tagName === 'INPUT' || event.target.tagName === 'TEXTAREA') {
            return;
        }

        // Prevent default for arrow keys and WASD
        if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'w', 'a', 's', 'd', ' '].includes(event.key)) {
            event.preventDefault();
        }

        switch(event.key) {
            case 'ArrowUp':
            case 'w':
            case 'W':
                sendCommand('F');
                break;
            case 'ArrowDown':
            case 's':
            case 'S':
                sendCommand('B');
                break;
            case 'ArrowLeft':
            case 'a':
            case 'A':
                sendCommand('L');
                break;
            case 'ArrowRight':
            case 'd':
            case 'D':
                sendCommand('R');
                break;
            case ' ':
                sendCommand('S');
                break;
        }
    });

    // Stop on key release
    document.addEventListener('keyup', function(event) {
        // Ignore keyboard controls if user is typing in an input field
        if (event.target.tagName === 'INPUT' || event.target.tagName === 'TEXTAREA') {
            return;
        }

        if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'w', 'a', 's', 'd'].includes(event.key)) {
            sendCommand('S');
        }
    });
}

// Add CSS animation for notifications
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(400px);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(400px);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);

// Image capture functionality
async function captureImage() {
    try {
        showNotification('Capturing image...', 'info');

        const response = await fetch('/capture_image', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tags: [] })
        });

        const data = await response.json();

        if (response.ok) {
            currentCaptureFilename = data.filename;
            showNotification('Image captured! Add tags...', 'success');
            openTagModal();
            loadCapturedImages();
        } else {
            showNotification('Failed to capture image: ' + data.error, 'error');
        }
    } catch (error) {
        console.error('Capture error:', error);
        showNotification('Capture error: ' + error.message, 'error');
    }
}

function openTagModal() {
    document.getElementById('tag-modal').style.display = 'flex';
    document.getElementById('tag-input').value = '';
    document.getElementById('tag-input').focus();
}

function closeTagModal() {
    document.getElementById('tag-modal').style.display = 'none';
    currentCaptureFilename = null;
}

async function saveTags() {
    if (!currentCaptureFilename) {
        closeTagModal();
        return;
    }

    const tagInput = document.getElementById('tag-input').value;
    const tags = tagInput.split(',').map(tag => tag.trim()).filter(tag => tag.length > 0);

    try {
        const response = await fetch(`/update_tags/${currentCaptureFilename}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tags: tags })
        });

        const data = await response.json();

        if (response.ok) {
            showNotification(`Tags saved: ${tags.join(', ')}`, 'success');
            loadCapturedImages();
        } else {
            showNotification('Failed to save tags: ' + data.error, 'error');
        }
    } catch (error) {
        console.error('Save tags error:', error);
        showNotification('Save tags error: ' + error.message, 'error');
    }

    closeTagModal();
}

async function loadCapturedImages() {
    try {
        const response = await fetch('/images');
        const data = await response.json();

        if (response.ok) {
            updateCapturedImagesList(data.images);
        }
    } catch (error) {
        console.error('Load images error:', error);
    }
}

function updateCapturedImagesList(images) {
    const listContainer = document.getElementById('captured-images-list');
    const imageCount = document.getElementById('image-count');

    imageCount.textContent = images.length;

    if (!images || images.length === 0) {
        listContainer.innerHTML = '<p style="color: #999; text-align: center;">No images captured</p>';
        return;
    }

    let html = '';
    images.reverse().forEach(img => {
        const tagsHtml = img.tags && img.tags.length > 0
            ? img.tags.map(tag => `<span class="tag">${tag}</span>`).join('')
            : '<span style="color: #999; font-size: 0.85em;">No tags</span>';

        html += `
            <div class="image-item">
                <img src="/image/${img.filename}" alt="Captured image">
                <div class="image-info">
                    <div style="font-size: 0.9em; color: #666;">${img.timestamp}</div>
                    <div class="image-tags">${tagsHtml}</div>
                </div>
            </div>
        `;
    });

    listContainer.innerHTML = html;
}

// Allow Enter key to save tags
document.addEventListener('keydown', function(event) {
    if (event.key === 'Enter' && event.target.id === 'tag-input') {
        saveTags();
    }
    if (event.key === 'Escape' && document.getElementById('tag-modal').style.display === 'flex') {
        closeTagModal();
    }
});

// ========== ML Training Functions ==========

async function checkModelStatus() {
    try {
        const response = await fetch('/model_status');
        const data = await response.json();

        if (data.model_exists) {
            document.getElementById('model-status').textContent = 'Trained';
            document.getElementById('model-status').style.color = '#4CAF50';

            if (data.training_history && data.training_history.val_accuracy) {
                const lastAccuracy = data.training_history.val_accuracy[data.training_history.val_accuracy.length - 1];
                document.getElementById('last-accuracy').textContent = (lastAccuracy * 100).toFixed(2) + '%';
            }
        } else {
            document.getElementById('model-status').textContent = 'Not Trained';
            document.getElementById('model-status').style.color = '#f44336';
        }
    } catch (error) {
        console.error('Failed to check model status:', error);
    }
}

async function loadAvailableModels() {
    try {
        const response = await fetch('/list_models');
        const data = await response.json();

        const modelSelect = document.getElementById('model-select');
        modelSelect.innerHTML = '';

        if (data.models && data.models.length > 0) {
            data.models.forEach(model => {
                const option = document.createElement('option');
                option.value = model.name;

                let label = model.name;
                if (model.accuracy) {
                    label += ` (${(model.accuracy * 100).toFixed(1)}% accuracy)`;
                }
                option.textContent = label;

                modelSelect.appendChild(option);
            });
        } else {
            const option = document.createElement('option');
            option.value = '';
            option.textContent = 'No models available';
            modelSelect.appendChild(option);
        }
    } catch (error) {
        console.error('Failed to load models:', error);
        const modelSelect = document.getElementById('model-select');
        modelSelect.innerHTML = '<option value="">Error loading models</option>';
    }
}

async function startTraining() {
    const modelName = document.getElementById('model-name').value.trim();
    const epochs = parseInt(document.getElementById('epochs').value);
    const batchSize = parseInt(document.getElementById('batch-size').value);

    if (!modelName) {
        showNotification('Please enter a model name', 'error');
        return;
    }

    if (!confirm(`Start training model "${modelName}" with ${epochs} epochs and batch size ${batchSize}?`)) {
        return;
    }

    try {
        document.getElementById('btn-train').disabled = true;
        document.getElementById('training-progress').style.display = 'block';
        document.getElementById('training-status').textContent = 'Preparing training data...';

        const response = await fetch('/train_model', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model_name: modelName,
                epochs,
                batch_size: batchSize
            })
        });

        const data = await response.json();

        if (response.ok) {
            document.getElementById('training-status').textContent = 'Training model... This may take several minutes.';
            showNotification(`Model "${modelName}" training started`, 'info');
        } else {
            throw new Error(data.error || 'Training failed');
        }
    } catch (error) {
        console.error('Training error:', error);
        document.getElementById('training-progress').style.display = 'none';
        document.getElementById('btn-train').disabled = false;
        showNotification('Training error: ' + error.message, 'error');
    }
}

async function startAutonomous() {
    const modelSelect = document.getElementById('model-select');
    const selectedModel = modelSelect.value;

    if (!selectedModel) {
        showNotification('Please select a model first', 'error');
        return;
    }

    try {
        const response = await fetch('/start_autonomous', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ model_name: selectedModel })
        });

        const data = await response.json();

        if (response.ok) {
            document.getElementById('auto-status').textContent = 'Running';
            document.getElementById('auto-status').style.color = '#4CAF50';
            document.getElementById('btn-start-auto').style.display = 'none';
            document.getElementById('btn-stop-auto').style.display = 'block';
            document.getElementById('prediction-display').style.display = 'block';
            showNotification(`Autonomous mode started with "${selectedModel}"`, 'success');
        } else {
            throw new Error(data.error || 'Failed to start autonomous mode');
        }
    } catch (error) {
        console.error('Start autonomous error:', error);
        showNotification('Error: ' + error.message, 'error');
    }
}

async function stopAutonomous() {
    try {
        const response = await fetch('/stop_autonomous', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        const data = await response.json();

        if (response.ok) {
            document.getElementById('auto-status').textContent = 'Stopped';
            document.getElementById('auto-status').style.color = '#f44336';
            document.getElementById('btn-start-auto').style.display = 'block';
            document.getElementById('btn-stop-auto').style.display = 'none';
            document.getElementById('prediction-display').style.display = 'none';
            showNotification('Autonomous mode stopped', 'success');
        } else {
            throw new Error(data.error || 'Failed to stop autonomous mode');
        }
    } catch (error) {
        console.error('Stop autonomous error:', error);
        showNotification('Error: ' + error.message, 'error');
    }
}

function updatePredictionDisplay(data) {
    document.getElementById('prediction-direction').textContent = data.direction;
    document.getElementById('prediction-confidence').textContent = (data.confidence * 100).toFixed(1);
    document.getElementById('prediction-command').textContent = data.command;
}

function showNotification(message, type = 'info') {
    const colors = {
        success: '#4CAF50',
        error: '#f44336',
        warning: '#FF9800',
        info: '#2196F3'
    };

    const notification = document.createElement('div');
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: ${colors[type] || colors.info};
        color: white;
        padding: 15px 25px;
        border-radius: 8px;
        box-shadow: 0 5px 15px rgba(0,0,0,0.3);
        z-index: 10000;
        font-weight: bold;
    `;
    notification.textContent = message;

    document.body.appendChild(notification);

    setTimeout(() => {
        document.body.removeChild(notification);
    }, 3000);
}
