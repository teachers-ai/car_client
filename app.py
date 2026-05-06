from flask import Flask, render_template, request, jsonify, Response
from flask_socketio import SocketIO as FlaskSocketIO
import socketio
import requests
import threading
import logging
import sys
import os
import shutil
from datetime import datetime
import json
import time
import io
from PIL import Image
import numpy as np

app = Flask(__name__)
app.config['SECRET_KEY'] = 'car-client-secret-key'
flask_socketio = FlaskSocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Server configuration (will be set by user input)
SERVER_URL = None
SERVER_HOST = None

# Socket.IO client for connecting to the car server
sio = socketio.Client()

# Global state
connections = []
current_speed = {'movement_speed': 0.5, 'rotation_speed': 0.5}
is_connected = False
my_session_id = None
am_i_controlling = False

# Autonomous driving state
autonomous_mode = False
autonomous_thread = None
direction_model = None

# Image capture state
IMAGES_DIR = 'captured_images'
ARCHIVE_DIR = 'archived_images'
METADATA_FILE = 'captured_images/metadata.json'
ARCHIVE_METADATA_FILE = 'archived_images/metadata.json'
latest_frame = None
auto_capture_enabled = False  # Toggle for auto-capture on movement

# Create directory structure
LABEL_DIRS = ['Forward', 'Backward', 'Left', 'Right', 'Manual']
for base_dir in [IMAGES_DIR, ARCHIVE_DIR]:
    if not os.path.exists(base_dir):
        os.makedirs(base_dir)
    for label in LABEL_DIRS:
        label_dir = os.path.join(base_dir, label)
        if not os.path.exists(label_dir):
            os.makedirs(label_dir)

# Load or create metadata files
if os.path.exists(METADATA_FILE):
    with open(METADATA_FILE, 'r') as f:
        image_metadata = json.load(f)
else:
    image_metadata = []

if os.path.exists(ARCHIVE_METADATA_FILE):
    with open(ARCHIVE_METADATA_FILE, 'r') as f:
        archive_metadata = json.load(f)
else:
    archive_metadata = []

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Socket.IO event handlers (client -> server connection)
@sio.event
def connect():
    global is_connected, my_session_id
    is_connected = True
    my_session_id = sio.sid
    logger.info(f'Connected to car server with session ID: {my_session_id}')
    # Automatically take control on connect (like sample code)
    sio.emit('take_control')
    logger.info('Emitted take_control on connect')


@sio.event
def disconnect():
    global is_connected
    is_connected = False
    logger.info('Disconnected from car server')


@sio.on('connection_list')
def on_connection_list(data):
    global connections, am_i_controlling, my_session_id
    connections = data

    # Check if our Python client is the active controller (like sample code)
    if isinstance(data, dict):
        active_controller = data.get('active_controller')
        am_i_controlling = (active_controller == my_session_id)
        # Log like sample code: [status] controller={is_controller}
        logger.info(f'[status] controller={am_i_controlling} (Active: {active_controller}, My SID: {my_session_id})')

    # Broadcast to all web clients with our controlling status
    flask_socketio.emit('connection_list', data)
    flask_socketio.emit('control_status', {'controlling': am_i_controlling})


@sio.on('speed_update')
def on_speed_update(data):
    global current_speed
    current_speed = data
    logger.info(f'Received speed update: {data}')
    # Broadcast to all web clients
    flask_socketio.emit('speed_update', data)


# Flask routes
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/camera')
def camera():
    """Proxy the camera stream from the car server"""
    global latest_frame
    try:
        def generate():
            global latest_frame
            r = requests.get(f'{SERVER_URL}/video_feed', stream=True, timeout=5)
            bytes_data = b''
            for chunk in r.iter_content(chunk_size=1024):
                bytes_data += chunk
                # Extract frame from MJPEG stream
                a = bytes_data.find(b'\xff\xd8')  # JPEG start
                b = bytes_data.find(b'\xff\xd9')  # JPEG end
                if a != -1 and b != -1:
                    jpg = bytes_data[a:b+2]
                    bytes_data = bytes_data[b+2:]
                    # Store latest frame
                    latest_frame = jpg
                    yield jpg
                else:
                    yield chunk

        return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')
    except Exception as e:
        logger.error(f'Camera proxy error: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/take_control', methods=['POST'])
def take_control():
    """Request control of the car"""
    try:
        logger.info(f'Take control requested. Connected: {is_connected}, SIO connected: {sio.connected}')

        if not is_connected or not sio.connected:
            logger.error('Cannot take control - not connected to car server')
            return jsonify({'error': 'Not connected to server'}), 503

        logger.info(f'Emitting take_control to car server (SID: {my_session_id})')
        sio.emit('take_control')
        logger.info('take_control event emitted successfully')
        return jsonify({'status': 'control_requested'})
    except Exception as e:
        logger.error(f'Take control error: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/release_control', methods=['POST'])
def release_control():
    """Release control of the car"""
    try:
        logger.info(f'Release control requested. Connected: {is_connected}, SIO connected: {sio.connected}')

        if not is_connected or not sio.connected:
            logger.error('Cannot release control - not connected to car server')
            return jsonify({'error': 'Not connected to server'}), 503

        logger.info('Emitting release_control to car server')
        sio.emit('release_control')
        logger.info('release_control event emitted successfully')
        return jsonify({'status': 'control_released'})
    except Exception as e:
        logger.error(f'Release control error: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/command', methods=['POST'])
def send_command():
    """Send movement command to the car"""
    try:
        if not is_connected or not sio.connected:
            logger.error('[cmd] not connected to server')
            return jsonify({'error': 'Not connected to server'}), 503

        data = request.get_json()
        direction = data.get('direction')

        if direction not in ['F', 'B', 'L', 'R', 'S']:
            return jsonify({'error': 'Invalid direction. Use F/B/L/R/S'}), 400

        # Send command directly
        sio.emit('command', {'dir': direction})
        logger.info(f'[cmd] {direction}')
        return jsonify({'status': 'command_sent', 'direction': direction})

    except Exception as e:
        logger.error(f'Command error: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/drop/<sid>', methods=['POST'])
def drop_client(sid):
    """Drop another client by session ID"""
    try:
        if not is_connected:
            return jsonify({'error': 'Not connected to server'}), 503

        sio.emit('drop_client', {'sid': sid})
        return jsonify({'status': 'drop_requested', 'sid': sid})
    except Exception as e:
        logger.error(f'Drop client error: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/speed', methods=['POST'])
def set_speed():
    """Set movement and rotation speed"""
    global current_speed
    try:
        if not is_connected:
            return jsonify({'error': 'Not connected to server'}), 503

        data = request.get_json()
        movement_speed = float(data.get('movement_speed', 0.5))
        rotation_speed = float(data.get('rotation_speed', 0.5))

        # Validate speed range
        if not (0.0 <= movement_speed <= 1.0) or not (0.0 <= rotation_speed <= 1.0):
            return jsonify({'error': 'Speed values must be between 0.0 and 1.0'}), 400

        # Store speed settings globally for use in autonomous mode
        current_speed = {
            'movement_speed': movement_speed,
            'rotation_speed': rotation_speed
        }
        logger.info(f'Speed settings updated: movement={movement_speed}, rotation={rotation_speed}')

        # Use correct API format: 'move_speed' and 'turn_speed'
        sio.emit('set_speed', {
            'move_speed': movement_speed,
            'turn_speed': rotation_speed
        })
        return jsonify({'status': 'speed_set', 'movement_speed': movement_speed, 'rotation_speed': rotation_speed})
    except Exception as e:
        logger.error(f'Set speed error: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/connections', methods=['GET'])
def get_connections():
    """Get list of active connections"""
    return jsonify(connections)


@app.route('/status', methods=['GET'])
def get_status():
    """Get client connection status"""
    return jsonify({
        'connected': is_connected,
        'server': SERVER_URL,
        'current_speed': current_speed,
        'controlling': am_i_controlling,
        'my_session_id': my_session_id
    })


@app.route('/connect', methods=['POST'])
def connect_route():
    """Connect to car server from UI"""
    global SERVER_URL, SERVER_HOST
    try:
        data = request.get_json()
        server = data.get('server', '192.168.12.147')
        port = data.get('port', 5000)

        # Validate port
        try:
            port = int(port)
            if port < 1 or port > 65535:
                return jsonify({'error': 'Invalid port number'}), 400
        except ValueError:
            return jsonify({'error': 'Port must be a number'}), 400

        # Update server configuration
        SERVER_HOST = f"{server}:{port}"
        SERVER_URL = f"http://{SERVER_HOST}"

        logger.info(f'Connection request to {SERVER_URL}')

        # Disconnect if already connected
        if sio.connected:
            disconnect_from_server()

        # Connect to new server
        success = connect_to_server()

        if success:
            return jsonify({
                'status': 'connected',
                'server': SERVER_URL
            })
        else:
            return jsonify({'error': 'Failed to connect to server'}), 503

    except Exception as e:
        logger.error(f'Connect route error: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/disconnect', methods=['POST'])
def disconnect_route():
    """Disconnect from car server"""
    try:
        logger.info('Disconnect request received')
        success = disconnect_from_server()

        if success:
            return jsonify({'status': 'disconnected'})
        else:
            return jsonify({'error': 'Failed to disconnect'}), 500

    except Exception as e:
        logger.error(f'Disconnect route error: {e}')
        return jsonify({'error': str(e)}), 500


def _save_image_thread(frame_data, tags, timestamp, label):
    """Background thread to save image (avoids blocking the main thread)"""
    global image_metadata
    try:
        # Generate filename with timestamp
        filename = f'capture_{timestamp}.jpg'

        # Save in label-specific folder
        label_dir = os.path.join(IMAGES_DIR, label)
        if not os.path.exists(label_dir):
            os.makedirs(label_dir)

        filepath = os.path.join(label_dir, filename)
        relative_path = os.path.join(label, filename)

        # Convert bytes to PIL Image
        img = Image.open(io.BytesIO(frame_data))

        # Crop to bottom half of image
        width, height = img.size
        bottom_half = img.crop((0, height // 2, width, height))

        # Save the cropped image
        bottom_half.save(filepath, 'JPEG', quality=95)

        # Save metadata
        metadata_entry = {
            'filename': filename,
            'filepath': relative_path,
            'label': label,
            'timestamp': timestamp,
            'tags': tags,
            'datetime': datetime.now().isoformat(),
            'archived': False,
            'cropped': 'bottom_half'
        }
        image_metadata.append(metadata_entry)

        # Save metadata to file
        with open(METADATA_FILE, 'w') as f:
            json.dump(image_metadata, f, indent=2)

        logger.info(f'Image captured (bottom half): {filename} in {label} folder with tags: {tags}')

    except Exception as e:
        logger.error(f'Background image save error: {e}')


@app.route('/capture_image', methods=['POST'])
def capture_image():
    """Capture current camera frame and save it (bottom half only, in background thread)"""
    global latest_frame
    try:
        if latest_frame is None:
            return jsonify({'error': 'No camera frame available'}), 400

        # Get tags from request
        data = request.get_json() or {}
        tags = data.get('tags', [])

        # Determine label/folder based on first tag
        label = tags[0] if tags else 'Manual'

        # Generate timestamp now (before thread)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'capture_{timestamp}.jpg'

        # Start background thread to save image (non-blocking)
        capture_thread = threading.Thread(
            target=_save_image_thread,
            args=(latest_frame, tags, timestamp, label),
            daemon=True
        )
        capture_thread.start()

        # Return immediately without waiting for save to complete
        logger.info(f'Started capture thread for: {filename} in {label} folder')
        return jsonify({
            'status': 'success',
            'filename': filename,
            'label': label,
            'tags': tags,
            'cropped': 'bottom_half'
        })

    except Exception as e:
        logger.error(f'Capture image error: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/auto_capture', methods=['GET', 'POST'])
def toggle_auto_capture():
    """Toggle or get auto-capture setting"""
    global auto_capture_enabled
    try:
        if request.method == 'POST':
            data = request.get_json() or {}
            auto_capture_enabled = data.get('enabled', auto_capture_enabled)
            logger.info(f'Auto-capture {"enabled" if auto_capture_enabled else "disabled"}')

        return jsonify({'auto_capture_enabled': auto_capture_enabled})

    except Exception as e:
        logger.error(f'Auto-capture toggle error: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/images', methods=['GET'])
def list_images():
    """Get list of captured images"""
    try:
        return jsonify({'images': image_metadata})
    except Exception as e:
        logger.error(f'List images error: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/image/<path:filepath>', methods=['GET'])
def get_image(filepath):
    """Get a specific captured image"""
    try:
        # Try in captured_images first
        full_path = os.path.join(IMAGES_DIR, filepath)

        # If not found, try in archived_images
        if not os.path.exists(full_path):
            full_path = os.path.join(ARCHIVE_DIR, filepath)

        if not os.path.exists(full_path):
            return jsonify({'error': 'Image not found'}), 404

        with open(full_path, 'rb') as f:
            image_data = f.read()

        return Response(image_data, mimetype='image/jpeg')
    except Exception as e:
        logger.error(f'Get image error: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/update_tags/<filename>', methods=['POST'])
def update_tags(filename):
    """Update tags for a captured image"""
    global image_metadata
    try:
        data = request.get_json()
        new_tags = data.get('tags', [])

        # Find and update the image metadata
        for entry in image_metadata:
            if entry['filename'] == filename:
                entry['tags'] = new_tags
                break
        else:
            return jsonify({'error': 'Image not found'}), 404

        # Save updated metadata
        with open(METADATA_FILE, 'w') as f:
            json.dump(image_metadata, f, indent=2)

        logger.info(f'Updated tags for {filename}: {new_tags}')
        return jsonify({'status': 'success', 'filename': filename, 'tags': new_tags})

    except Exception as e:
        logger.error(f'Update tags error: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/archive_images', methods=['POST'])
def archive_images():
    """Archive selected images"""
    global image_metadata, archive_metadata
    try:
        data = request.get_json()
        filenames = data.get('filenames', [])

        if not filenames:
            return jsonify({'error': 'No filenames provided'}), 400

        archived_count = 0

        for filename in filenames:
            # Find the image in metadata
            for entry in image_metadata:
                if entry['filename'] == filename:
                    # Move the file
                    src_path = os.path.join(IMAGES_DIR, entry['filepath'])
                    label = entry.get('label', 'Manual')
                    dest_dir = os.path.join(ARCHIVE_DIR, label)

                    if not os.path.exists(dest_dir):
                        os.makedirs(dest_dir)

                    dest_path = os.path.join(dest_dir, filename)

                    if os.path.exists(src_path):
                        shutil.move(src_path, dest_path)

                        # Update metadata
                        entry['archived'] = True
                        entry['filepath'] = os.path.join(label, filename)
                        archive_metadata.append(entry)
                        archived_count += 1

                    break

        # Remove archived entries from active metadata
        image_metadata = [entry for entry in image_metadata if entry['filename'] not in filenames]

        # Save updated metadata
        with open(METADATA_FILE, 'w') as f:
            json.dump(image_metadata, f, indent=2)

        with open(ARCHIVE_METADATA_FILE, 'w') as f:
            json.dump(archive_metadata, f, indent=2)

        logger.info(f'Archived {archived_count} images')
        return jsonify({'status': 'success', 'archived_count': archived_count})

    except Exception as e:
        logger.error(f'Archive images error: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/delete_images', methods=['POST'])
def delete_images():
    """Delete selected images permanently"""
    global image_metadata
    try:
        data = request.get_json()
        filenames = data.get('filenames', [])

        if not filenames:
            return jsonify({'error': 'No filenames provided'}), 400

        deleted_count = 0

        for filename in filenames:
            # Find and delete the image
            for entry in image_metadata:
                if entry['filename'] == filename:
                    filepath = os.path.join(IMAGES_DIR, entry['filepath'])

                    if os.path.exists(filepath):
                        os.remove(filepath)
                        deleted_count += 1

                    break

        # Remove deleted entries from metadata
        image_metadata = [entry for entry in image_metadata if entry['filename'] not in filenames]

        # Save updated metadata
        with open(METADATA_FILE, 'w') as f:
            json.dump(image_metadata, f, indent=2)

        logger.info(f'Deleted {deleted_count} images')
        return jsonify({'status': 'success', 'deleted_count': deleted_count})

    except Exception as e:
        logger.error(f'Delete images error: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/gallery')
def gallery():
    """Image gallery page"""
    return render_template('gallery.html')


@app.route('/archived_images', methods=['GET'])
def get_archived_images():
    """Get list of archived images"""
    try:
        return jsonify({'images': archive_metadata})
    except Exception as e:
        logger.error(f'Get archived images error: {e}')
        return jsonify({'error': str(e)}), 500


# ML Model Training Endpoints

@app.route('/train_model', methods=['POST'])
def train_model():
    """Train VGG16 model on captured images"""
    global direction_model
    try:
        from model_trainer import DirectionModel

        data = request.get_json() or {}
        epochs = data.get('epochs', 10)
        batch_size = data.get('batch_size', 32)
        model_name = data.get('model_name', 'direction_model')

        logger.info(f'Starting model training: {model_name} with epochs={epochs}, batch_size={batch_size}')

        # Initialize model with custom name
        direction_model = DirectionModel(model_name=model_name)

        # Train in a separate thread to avoid blocking
        def train_async():
            try:
                history = direction_model.train(epochs=epochs, batch_size=batch_size)
                logger.info(f'Model training completed successfully: {model_name}')
                flask_socketio.emit('training_complete', history)
            except Exception as e:
                logger.error(f'Training error: {e}')
                flask_socketio.emit('training_error', {'error': str(e)})

        training_thread = threading.Thread(target=train_async)
        training_thread.start()

        return jsonify({'status': 'training_started', 'model_name': model_name, 'epochs': epochs, 'batch_size': batch_size})

    except Exception as e:
        logger.error(f'Train model error: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/model_status', methods=['GET'])
def model_status():
    """Get model training status and info"""
    try:
        model_name = request.args.get('model_name', 'direction_model')
        model_path = f'models/{model_name}.h5'
        history_path = f'models/{model_name}_history.json'

        model_exists = os.path.exists(model_path)
        history_exists = os.path.exists(history_path)

        result = {
            'model_exists': model_exists,
            'model_name': model_name,
            'model_path': model_path if model_exists else None
        }

        if history_exists:
            with open(history_path, 'r') as f:
                history = json.load(f)
                result['training_history'] = history

        return jsonify(result)

    except Exception as e:
        logger.error(f'Model status error: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/list_models', methods=['GET'])
def list_models():
    """List all available trained models"""
    try:
        models_dir = 'models'
        if not os.path.exists(models_dir):
            return jsonify({'models': []})

        # Find all .h5 model files
        model_files = [f for f in os.listdir(models_dir) if f.endswith('.h5')]

        models = []
        for model_file in model_files:
            model_name = model_file.replace('.h5', '')
            model_path = os.path.join(models_dir, model_file)
            history_path = os.path.join(models_dir, f'{model_name}_history.json')

            model_info = {
                'name': model_name,
                'path': model_path,
                'size': os.path.getsize(model_path),
                'modified': os.path.getmtime(model_path)
            }

            # Add training history if available
            if os.path.exists(history_path):
                with open(history_path, 'r') as f:
                    history = json.load(f)
                    if 'val_accuracy' in history and len(history['val_accuracy']) > 0:
                        model_info['accuracy'] = history['val_accuracy'][-1]
                    if 'class_counts' in history:
                        model_info['class_counts'] = history['class_counts']

            models.append(model_info)

        # Sort by modified date (newest first)
        models.sort(key=lambda x: x['modified'], reverse=True)

        return jsonify({'models': models})

    except Exception as e:
        logger.error(f'List models error: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/predict_direction', methods=['POST'])
def predict_direction():
    """Predict direction from current camera frame"""
    global latest_frame, direction_model
    try:
        if latest_frame is None:
            return jsonify({'error': 'No camera frame available'}), 400

        if direction_model is None:
            from model_trainer import DirectionModel
            direction_model = DirectionModel()
            if not direction_model.load_model():
                return jsonify({'error': 'Model not trained yet'}), 400

        # Convert frame to image
        img = Image.open(io.BytesIO(latest_frame))

        # Predict
        prediction = direction_model.predict(img)

        return jsonify(prediction)

    except Exception as e:
        logger.error(f'Predict direction error: {e}')
        return jsonify({'error': str(e)}), 500


# Autonomous Driving Endpoints

@app.route('/start_autonomous', methods=['POST'])
def start_autonomous():
    """Start autonomous driving mode"""
    global autonomous_mode, autonomous_thread, direction_model
    try:
        if not is_connected or not sio.connected:
            return jsonify({'error': 'Not connected to car server'}), 503

        if autonomous_mode:
            return jsonify({'error': 'Autonomous mode already running'}), 400

        # Get model name from request
        data = request.get_json() or {}
        model_name = data.get('model_name', 'direction_model')

        # Load or reload the selected model
        from model_trainer import DirectionModel
        direction_model = DirectionModel(model_name=model_name)
        if not direction_model.load_model():
            return jsonify({'error': f'Model "{model_name}" not found. Please train the model first.'}), 400

        logger.info(f'Starting autonomous driving mode with model: {model_name}')
        autonomous_mode = True

        def autonomous_drive():
            global autonomous_mode, latest_frame, current_speed
            logger.info('Autonomous driving thread started')

            try:
                while autonomous_mode:
                    try:
                        if latest_frame is not None:
                            # Predict direction - pass bytes directly
                            prediction = direction_model.predict(latest_frame)

                            direction = prediction['direction']
                            confidence = prediction['confidence']

                            # Only act if confidence is above threshold
                            if confidence > 0.6:
                                # Map direction to command
                                direction_map = {
                                    'Forward': 'F',
                                    'Backward': 'B',
                                    'Left': 'L',
                                    'Right': 'R'
                                }

                                cmd = direction_map.get(direction, 'S')

                                # Log prediction
                                probs = prediction.get('probabilities', {})
                                logger.info(f'🤖 AUTONOMOUS: {direction} ({confidence*100:.1f}%) → {cmd}')

                                # Send command exactly like manual controls (just direction, no speed/turn)
                                sio.emit('command', {'dir': cmd})
                                logger.info(f'[cmd] {cmd}')

                                # Broadcast prediction to UI
                                flask_socketio.emit('autonomous_prediction', {
                                    'direction': direction,
                                    'confidence': confidence,
                                    'command': cmd
                                })
                            else:
                                logger.info(f'⚠️  Low confidence ({confidence*100:.1f}%)')
                                sio.emit('command', {'dir': 'S'})
                                logger.info(f'[cmd] S (low confidence stop)')

                        time.sleep(0.5)  # Update every 500ms

                    except Exception as e:
                        logger.error(f'Autonomous drive error: {e}')
                        time.sleep(1)

            except Exception as e:
                logger.error(f'Autonomous drive thread fatal error: {e}')
            finally:
                # Ensure car is stopped and mode is reset even on errors
                try:
                    sio.emit('command', {'dir': 'S'})
                    logger.info('Sent final STOP command')
                except:
                    pass
                autonomous_mode = False
                logger.info('Autonomous driving thread stopped')

        autonomous_thread = threading.Thread(target=autonomous_drive)
        autonomous_thread.start()

        return jsonify({'status': 'autonomous_mode_started'})

    except Exception as e:
        logger.error(f'Start autonomous error: {e}')
        autonomous_mode = False
        return jsonify({'error': str(e)}), 500


@app.route('/stop_autonomous', methods=['POST'])
def stop_autonomous():
    """Stop autonomous driving mode"""
    global autonomous_mode, autonomous_thread
    try:
        logger.info(f'Stop autonomous requested. Current state: {autonomous_mode}')

        # Force stop even if state is inconsistent
        autonomous_mode = False

        # Wait for thread to finish
        if autonomous_thread and autonomous_thread.is_alive():
            logger.info('Waiting for autonomous thread to finish...')
            autonomous_thread.join(timeout=2)
            logger.info('Autonomous thread stopped')

        return jsonify({'status': 'autonomous_mode_stopped'})

    except Exception as e:
        logger.error(f'Stop autonomous error: {e}')
        autonomous_mode = False  # Force reset on error
        return jsonify({'error': str(e)}), 500


@app.route('/autonomous_status', methods=['GET'])
def autonomous_status():
    """Get autonomous driving status"""
    return jsonify({'autonomous_mode': autonomous_mode})


@app.route('/ml_dashboard')
def ml_dashboard():
    """ML training and autonomous driving dashboard"""
    return render_template('ml_dashboard.html')


def connect_to_server():
    """Connect to the car server via Socket.IO"""
    global is_connected, am_i_controlling
    try:
        if sio.connected:
            logger.info('Already connected to car server')
            return True

        logger.info(f'Connecting to car server at {SERVER_URL}...')
        # Use polling transport as per API specification
        sio.connect(SERVER_URL, transports=['polling'])
        logger.info('Successfully connected to car server')

        # Wait for connection_list event to arrive (like in sample code)
        logger.info('Waiting for connection_list event...')
        time.sleep(0.5)

        # Check if we got control
        if am_i_controlling:
            logger.info(f'✅ Successfully acquired control of the car!')
        else:
            logger.warning('⚠️  Connected but did not get control automatically.')
            logger.warning('⚠️  Another client may be controlling. Click "Take Control" to request it.')

        return True
    except Exception as e:
        logger.error(f'Failed to connect to car server: {e}')
        is_connected = False
        return False


def disconnect_from_server():
    """Disconnect from the car server"""
    global is_connected, my_session_id, am_i_controlling
    try:
        if sio.connected:
            logger.info('Disconnecting from car server...')
            # Release control before disconnecting (stops the car)
            sio.emit('release_control')
            sio.disconnect()
            is_connected = False
            my_session_id = None
            am_i_controlling = False
            logger.info('Disconnected from car server')
            return True
        else:
            logger.info('Not connected to car server')
            return True
    except Exception as e:
        logger.error(f'Failed to disconnect from car server: {e}')
        return False


def get_server_address():
    """Get car server address from command line arguments or environment variable"""
    global SERVER_URL, SERVER_HOST
    import argparse

    parser = argparse.ArgumentParser(description='Car FPV Client')
    parser.add_argument(
        '--server',
        type=str,
        default=os.environ.get('CAR_SERVER', '192.168.12.147'),
        help='Car server IP address or hostname (default: 192.168.12.147, or CAR_SERVER env var)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=int(os.environ.get('CAR_PORT', '5000')),
        help='Car server port (default: 5000, or CAR_PORT env var)'
    )
    parser.add_argument(
        '--client-port',
        type=int,
        default=5001,
        help='Flask client port (default: 5001)'
    )

    args = parser.parse_args()

    SERVER_HOST = f"{args.server}:{args.port}"
    SERVER_URL = f"http://{SERVER_HOST}"

    print("\n" + "="*70)
    print("Car FPV Client - Configuration")
    print("="*70)
    print(f"Car Server:    {SERVER_URL}")
    print(f"Client Port:   {args.client_port}")
    print(f"\nTo change server: python app.py --server <IP> --port <PORT>")
    print(f"Or set environment variables: CAR_SERVER and CAR_PORT")
    print("="*70 + "\n")

    return args.client_port


if __name__ == '__main__':
    # Get server address from arguments (sets default values)
    client_port = get_server_address()

    # Note: Connection is now initiated from the UI, not automatically on startup
    logger.info("Server not connected. Use the UI to connect.")

    # Run Flask app
    flask_socketio.run(app, host='0.0.0.0', port=client_port, debug=True, allow_unsafe_werkzeug=True)
