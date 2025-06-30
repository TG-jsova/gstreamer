# Desktop Streamer

A high-performance desktop capture and streaming application that captures the second monitor of a Linux desktop and streams it in real-time using HLS (HTTP Live Streaming). Perfect for kiosk configurations and remote display applications.

## Features

- **High-Quality Capture**: Captures the second monitor at 30+ FPS with configurable resolution
- **HLS Streaming**: Real-time HTTP Live Streaming for broad device compatibility
- **MediaMTX Integration**: Professional-grade streaming server
- **System Service**: Runs as a systemd service for reliable operation
- **Web Monitor**: Built-in web interface for monitoring and control
- **Docker Support**: Containerized deployment option
- **Configurable**: Easy configuration via JSON files

## Requirements

- Ubuntu 20.04+ or compatible Linux distribution
- X11 display server
- At least 2 monitors connected
- Python 3.8+
- GStreamer 1.0+
- MediaMTX

## Quick Start

### Option 1: Automated Installation (Recommended)

1. Clone the repository:
```bash
git clone <repository-url>
cd gstreamer
```

2. Run the installation script:
```bash
sudo chmod +x install.sh
sudo ./install.sh
```

3. Access the web monitor:
```
http://0.0.0.0:8080
```

4. View the HLS stream:
```
http://0.0.0.0:8888/hls/desktop/playlist.m3u8
```

### Option 2: Docker Deployment

1. Build and run with Docker Compose:
```bash
docker-compose up -d
```

2. Access the web monitor:
```
http://0.0.0.0:8080
```

### Option 3: Manual Installation

1. Install system dependencies:
```bash
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-gi gstreamer1.0-plugins-* x11-apps xrandr
```

2. Install MediaMTX:
```bash
wget -O /tmp/mediamtx.tar.gz https://github.com/bluenviron/mediamtx/releases/latest/download/mediamtx_linux_amd64.tar.gz
sudo tar -xzf /tmp/mediamtx.tar.gz -C /usr/local/bin/
sudo chmod +x /usr/local/bin/mediamtx
```

3. Install Python dependencies:
```bash
pip3 install -r desktop_streamer_requirements.txt
```

4. Copy files and set up service:
```bash
sudo mkdir -p /opt/desktop-streamer /etc/desktop-streamer
sudo cp desktop_streamer.py /opt/desktop-streamer/
sudo cp desktop-streamer.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable desktop-streamer.service
sudo systemctl start desktop-streamer.service
```

## Configuration

The application can be configured by editing `/etc/desktop-streamer/config.json`:

```json
{
    "fps": 30,
    "width": 1920,
    "height": 1080,
    "bitrate": 5000,
    "keyframe_interval": 2,
    "segment_duration": 2,
    "output_dir": "/tmp/hls"
}
```

### Configuration Options

- **fps**: Frame rate (default: 30)
- **width**: Capture width in pixels (default: 1920)
- **height**: Capture height in pixels (default: 1080)
- **bitrate**: Video bitrate in kbps (default: 5000)
- **keyframe_interval**: Keyframe interval in seconds (default: 2)
- **segment_duration**: HLS segment duration in seconds (default: 2)
- **output_dir**: Directory for HLS files (default: /tmp/hls)

## Usage

### Service Management

```bash
# Check service status
sudo systemctl status desktop-streamer.service

# Start the service
sudo systemctl start desktop-streamer.service

# Stop the service
sudo systemctl stop desktop-streamer.service

# Restart the service
sudo systemctl restart desktop-streamer.service

# View logs
sudo journalctl -u desktop-streamer.service -f
```

### Web Monitor

The web monitor provides a user-friendly interface for:
- Monitoring service status
- Viewing stream information
- Controlling the service (start/stop/restart)
- Viewing recent logs
- Watching the live stream

Access it at: `http://0.0.0.0:8080`

### API Endpoints

The web monitor also provides REST API endpoints:

- `GET /api/status` - Get current status
- `GET /api/service/start` - Start the service
- `GET /api/service/stop` - Stop the service
- `GET /api/service/restart` - Restart the service

## Streaming Details

### HLS Stream URL
```
http://0.0.0.0:8888/hls/desktop/playlist.m3u8
```

### Supported Players
- Web browsers (Chrome, Firefox, Safari, Edge)
- VLC Media Player
- FFmpeg
- Any HLS-compatible player

### Network Access
To access the stream from other devices on the network, replace `localhost` with the server's IP address:

```
http://<server-ip>:8888/hls/desktop/playlist.m3u8
```

## Troubleshooting

### Common Issues

1. **Service fails to start**
   - Check logs: `sudo journalctl -u desktop-streamer.service -f`
   - Ensure X11 is running: `echo $DISPLAY`
   - Check X11 permissions: `xhost +local:root`

2. **No video output**
   - Verify monitor configuration: `xrandr --listmonitors`
   - Check if second monitor is detected
   - Ensure GStreamer plugins are installed

3. **High CPU usage**
   - Reduce bitrate in configuration
   - Lower frame rate
   - Use hardware acceleration if available

4. **Network connectivity issues**
   - Check firewall settings
   - Verify MediaMTX is running: `ps aux | grep mediamtx`
   - Test port accessibility: `netstat -tlnp | grep 8888`

### Performance Optimization

1. **Hardware Acceleration**
   Add these GStreamer elements to the pipeline for hardware acceleration:
   - Intel: `vaapih264enc` and `vaapih264dec`
   - NVIDIA: `nvh264enc` and `nvh264dec`
   - AMD: `amfh264enc` and `amfh264dec`

2. **Network Optimization**
   - Use wired network connections
   - Configure QoS for streaming traffic
   - Consider using multicast for multiple viewers

3. **System Optimization**
   - Disable unnecessary services
   - Increase file descriptor limits
   - Optimize X11 settings

## Development

### Building from Source

1. Clone the repository
2. Install development dependencies
3. Run the application directly:
```bash
python3 desktop_streamer.py
```

### Adding Features

The application is modular and can be extended:
- Add new video encoders
- Implement different streaming protocols
- Add authentication
- Create custom monitoring dashboards

## Security Considerations

- The service runs as root for X11 access
- Consider using a dedicated user with appropriate permissions
- Implement authentication for web monitor access
- Use HTTPS for production deployments
- Configure firewall rules appropriately

## License

[Add your license information here]

## Contributing

[Add contribution guidelines here]

## Support

For issues and questions:
1. Check the troubleshooting section
2. Review the logs: `sudo journalctl -u desktop-streamer.service -f`
3. Create an issue in the repository
4. Check the MediaMTX documentation for streaming server issues 