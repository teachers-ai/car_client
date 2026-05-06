# Car FPV Client Application

A Flask-based web client for controlling a remote car through a RasCar server. This application provides a real-time camera feed, intuitive controls, and multi-client connection management.

## Features

- **Live Camera Feed**: Real-time video streaming from the car's camera
- **Intuitive Controls**: Web-based and keyboard controls for car movement
- **Speed Management**: Adjustable movement and rotation speeds
- **Multi-Client Support**: View and manage multiple connected clients
- **Real-time Updates**: WebSocket-based communication for instant feedback
- **Responsive Design**: Modern, gradient-based UI that works on various screen sizes

## Prerequisites

- Python 3.7 or higher
- Network access to the RasCar server (192.168.12.147:5000)
- Both client and server must be on the same network

## Installation

1. Clone or download this repository:
```bash
cd car_client
```

2. Create a virtual environment (recommended):
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install required dependencies:
```bash
pip install -r requirements.txt
```

## Configuration

The application supports three ways to configure the car server address:

### 1. Command-Line Arguments (Recommended)

```bash
# Use default server (192.168.12.147:5000)
python app.py

# Specify custom server and port
python app.py --server 192.168.1.100 --port 5000

# Change client port
python app.py --client-port 8080

# View all options
python app.py --help
```

### 2. Environment Variables

```bash
# Set environment variables
export CAR_SERVER=192.168.1.100
export CAR_PORT=5000

# Run app
python app.py
```

### 3. Default Configuration

If no configuration is provided, the app uses:
- Car Server: `192.168.12.147:5000`
- Client Port: `5001`

## Running the Application

1. Start the Flask application:
```bash
# With default server
python app.py

# With custom server
python app.py --server YOUR_SERVER_IP --port SERVER_PORT
```

2. The app will display the configuration:
```
======================================================================
Car FPV Client - Configuration
======================================================================
Car Server:    http://192.168.12.147:5000
Client Port:   5001
======================================================================
```

3. Open your web browser and navigate to:
```
http://localhost:5001
```

Or from another device on the same network:
```
http://YOUR_COMPUTER_IP:5001
```

## Usage Guide

### Taking Control

1. Click the **"Take Control"** button in the Control Panel
2. Wait for confirmation (the control status will update when successful)
3. Only one client can control the car at a time
4. If another client has control, your request will be silently rejected

### Controlling the Car

**Web Interface:**
- Use the arrow buttons (↑ ↓ ← →) for directional movement
- Click **STOP** button to halt the car

**Keyboard Controls:**
- Arrow Keys or WASD for movement:
  - ↑ / W: Forward
  - ↓ / S: Backward
  - ← / A: Left
  - → / D: Right
  - Space: Stop
- Auto-stop on key release

### Adjusting Speed

1. Use the **Movement Speed** slider to adjust forward/backward speed (0-100%)
2. Use the **Rotation Speed** slider to adjust turning speed (0-100%)
3. Click **"Apply Speed Settings"** to send changes to the server
4. Speed changes affect all connected clients

### Releasing Control

Click the **"Release Control"** button when finished. The car will automatically stop.

### Managing Connections

- View all active connections in the **Active Connections** panel
- Connections marked with **[CONTROLLING]** have car control
- Click **"Drop"** next to a connection to disconnect that client (requires appropriate permissions)

## API Endpoints

The Flask server exposes the following endpoints:

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Main web interface |
| GET | `/camera` | Camera stream proxy (MJPEG) |
| POST | `/take_control` | Request car control |
| POST | `/release_control` | Release car control |
| POST | `/command` | Send movement command (F/B/L/R/S) |
| POST | `/speed` | Set speed parameters |
| POST | `/drop/<sid>` | Drop client by session ID |
| GET | `/connections` | Get active connections list |
| GET | `/status` | Get client connection status |

## WebSocket Events

### Client Emits (to car server)
- `take_control` - Request vehicle control
- `release_control` - Release vehicle control
- `command` - Send movement command
- `drop_client` - Disconnect another client
- `set_speed` - Update speed parameters

### Client Receives (from car server)
- `connection_list` - Active client list and control status
- `speed_update` - Speed parameter updates

## Project Structure

```
car_client/
├── app.py                  # Main Flask application
├── requirements.txt        # Python dependencies
├── README.md              # This file
├── templates/
│   └── index.html         # Web interface
└── static/
    └── js/
        └── control.js     # Client-side JavaScript
```

## Troubleshooting

### Cannot connect to server
- Verify the car server is running at 192.168.12.147:5000
- Ensure both devices are on the same network
- Check firewall settings on both machines

### Camera feed not loading
- The camera endpoint requires the server's `/video_feed` to be active
- Check browser console for errors
- Verify network connectivity to the server

### Controls not responding
- Ensure you have taken control first
- Check if another client has control (only one client can control at a time)
- Verify WebSocket connection status (should show "Connected")

### WebSocket connection issues
- Check that the server supports Socket.IO
- Ensure no firewall is blocking WebSocket connections
- Try refreshing the page

## Development

To modify the server address or port:

1. Edit `app.py` and update `SERVER_URL` and `SERVER_HOST`
2. To change the client port, modify the last line:
```python
flask_socketio.run(app, host='0.0.0.0', port=YOUR_PORT, debug=True)
```

## Security Notes

- This application is designed for local network use
- No authentication is implemented by default
- Be cautious when exposing to public networks
- Consider adding authentication for production use

## Dependencies

- **Flask**: Web framework
- **flask-socketio**: WebSocket support for Flask
- **python-socketio**: Socket.IO client library
- **requests**: HTTP library for API calls

## License

This project is provided as-is for educational and development purposes.

## Support

For issues or questions:
1. Check the troubleshooting section
2. Verify all prerequisites are met
3. Ensure server and client configurations match
4. Check server logs for connection issues

## Credits

Based on the RasCar server protocol. Designed for remote car control and FPV streaming.
