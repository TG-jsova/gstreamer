# Desktop Streamer with Self-Healing

A robust, self-healing GStreamer-based desktop streaming service with comprehensive monitoring and automated recovery capabilities. This system captures your second monitor and streams it via HLS (HTTP Live Streaming) with built-in health monitoring, automatic recovery, and real-time alerts. **Optimized for 24/7 kiosk operation with Unity workloads.**

## 🚀 Features

### Core Streaming
- **Multi-Monitor Support**: Automatically detects and captures second monitor
- **HLS Streaming**: HTTP Live Streaming for broad device compatibility
- **Configurable Quality**: Adjustable resolution, bitrate, and frame rate
- **Low Latency**: Optimized for real-time streaming
- **Live Streaming Optimized**: Minimal segment storage for live feeds

### Self-Healing & Monitoring
- **Health Monitoring**: Continuous monitoring of pipeline state and performance
- **Automatic Recovery**: Detects and recovers from stuck pipelines and failures
- **Error Tracking**: Intelligent error pattern detection with configurable thresholds
- **Real-time Dashboard**: Beautiful web interface with live updates
- **Watchdog Service**: Independent monitoring service with alert capabilities
- **Resource Monitoring**: CPU, memory, and disk usage tracking

### Kiosk & 24/7 Operation
- **Unity Workload Coexistence**: Optimized settings to not compete with Unity applications
- **AMD SOC Optimization**: Hardware acceleration and GPU memory management
- **Live Streaming**: Aggressive file cleanup keeping only recent segments
- **Resource Limits**: CPU and memory quotas to prevent resource exhaustion
- **Automatic Maintenance**: Self-cleaning to prevent disk space and memory issues

### Alert System
- **Email Alerts**: Configurable SMTP-based email notifications
- **Webhook Alerts**: Integration with Slack, Discord, and other platforms
- **Alert Cooldown**: Prevents alert spam with intelligent rate limiting
- **Severity Levels**: Warning, critical, and info alert levels

### External Access
- **Network Accessible**: All services bind to `0.0.0.0` for external access
- **Web Dashboard**: Accessible from any device on the network
- **Health API**: RESTful API for monitoring and integration
- **HLS Stream**: Compatible with any HLS-capable player

## 📋 Requirements

### System Requirements
- Ubuntu 20.04+ or Debian 10+
- Python 3.8+
- GStreamer 1.0 with development packages
- X11 display server
- At least 2 monitors (primary + secondary)

### Hardware Requirements
- **CPU**: Multi-core processor (2+ cores recommended)
- **RAM**: 4GB+ (8GB+ recommended for high-quality streaming)
- **Storage**: 10GB+ free space for HLS segments
- **Network**: Stable network connection for streaming
- **GPU**: AMD SOC with hardware acceleration support (optional)

## 🛠️ Installation

### Quick Install (Recommended)
```bash
# Clone the repository
git clone <repository-url>
cd gstreamer

# Run the installation script with kiosk optimizations
chmod +x install.sh
sudo ./install.sh
```

The installation script will:
- Install all dependencies including VAAPI for hardware acceleration
- Set up kiosk-optimized configuration
- Configure resource limits for Unity workload coexistence
- Set up log rotation and automatic cleanup
- Enable systemd services with proper resource constraints

### Manual Installation

1. **Install System Dependencies**:
```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-gi python3-gi-cairo gir1.2-gstreamer-1.0 \
    gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav \
    gstreamer1.0-x gstreamer1.0-alsa gstreamer1.0-gl gstreamer1.0-gtk3 \
    gstreamer1.0-qt5 gstreamer1.0-pulseaudio libgirepository1.0-dev \
    libcairo2-dev pkg-config python3-dev build-essential xrandr \
    curl wget git htop iotop lshw logrotate

# Install VAAPI for hardware acceleration (AMD SOC)
sudo apt install -y vainfo intel-media-va-driver-non-free mesa-va-drivers mesa-vdpau-drivers
```

2. **Install Python Dependencies**:
```bash
pip3 install -r desktop_streamer_requirements.txt
```

3. **Install MediaMTX**:
```bash
# Download and install MediaMTX
wget https://github.com/bluenviron/mediamtx/releases/latest/download/mediamtx_linux_amd64.tar.gz
tar -xzf mediamtx_linux_amd64.tar.gz
sudo mv mediamtx /usr/local/bin/
sudo chmod +x /usr/local/bin/mediamtx
```

4. **Setup Services**:
```bash
# Copy service files
sudo cp desktop-streamer.service /etc/systemd/system/
sudo cp desktop-streamer-watchdog.service /etc/systemd/system/

# Create configuration directory
sudo mkdir -p /etc/desktop-streamer

# Copy kiosk-optimized configuration
sudo cp kiosk-config.json /etc/desktop-streamer/config.json

# Create watchdog configuration
sudo tee /etc/desktop-streamer/watchdog-config.json > /dev/null <<EOF
{
    "check_interval": 30,
    "max_alerts": 10,
    "alert_cooldown": 300,
    "auto_recovery": {
        "service_restart": true,
        "stream_restart": true,
        "resource_monitoring": true
    },
    "email_alerts": {
        "enabled": false,
        "smtp_server": "localhost",
        "smtp_port": 587,
        "use_tls": true,
        "from_email": "watchdog@example.com",
        "to_email": "admin@example.com"
    },
    "webhook_alerts": {
        "enabled": false,
        "url": "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
    }
}
EOF

# Setup log rotation
sudo cp desktop-streamer-logrotate /etc/logrotate.d/desktop-streamer

# Reload systemd and enable services
sudo systemctl daemon-reload
sudo systemctl enable desktop-streamer.service
sudo systemctl enable desktop-streamer-watchdog.service
```

## 🚀 Usage

### Starting Services
```bash
# Start the main streaming service
sudo systemctl start desktop-streamer.service

# Start the watchdog monitoring service
sudo systemctl start desktop-streamer-watchdog.service

# Check service status
sudo systemctl status desktop-streamer.service
sudo systemctl status desktop-streamer-watchdog.service

# Quick status check
desktop-streamer-monitor
```

### Accessing the System

1. **Web Dashboard** (Primary Interface):
   ```
   http://<server-ip>:8080
   ```
   - Real-time monitoring dashboard
   - Service control (start/stop/restart)
   - Live logs and health metrics
   - Stream player and management
   - Live stream cleanup tools

2. **Health API** (For Integration):
   ```
   http://<server-ip>:8888/api/health
   http://<server-ip>:8888/api/status
   http://<server-ip>:8888/api/health/detailed
   ```

3. **HLS Stream** (For Players):
   ```
   http://<server-ip>:8888/hls/desktop/playlist.m3u8
   ```

### Web Dashboard Features

The web dashboard provides comprehensive monitoring and control:

- **Service Status**: Real-time service state and control buttons
- **Stream Health**: Live stream status, segment count, and activity
- **System Resources**: CPU, memory, and disk usage monitoring
- **Health Metrics**: Error counts, restart history, and uptime
- **Live Logs**: Real-time log streaming with filtering
- **Stream Player**: Built-in HLS player for testing
- **Management Tools**: Cleanup segments, refresh streams
- **Live Streaming**: Optimized for live feed management

### API Endpoints

#### Health API (`/api/health`)
```json
{
    "monitoring_active": true,
    "total_errors": 2,
    "recent_errors": 1,
    "current_state": "PLAYING",
    "stream_active": true,
    "mediamtx_running": true,
    "restart_count": 0,
    "last_error": "Pipeline paused unexpectedly",
    "uptime_minutes": 45.2,
    "memory_usage_mb": 245.6,
    "system_memory_percent": 45.2
}
```

#### Status API (`/api/status`)
```json
{
    "service": {
        "active": true,
        "details": {
            "ActiveState": "active",
            "SubState": "running"
        }
    },
    "stream": {
        "playlist_exists": true,
        "segment_count": 5,
        "total_size_mb": 2.5,
        "stream_active": true
    },
    "health": { ... },
    "system": {
        "cpu_percent": 25.3,
        "memory_percent": 45.2,
        "disk_usage_percent": 12.5
    }
}
```

## 🔧 Configuration

### Main Service Configuration (`/etc/desktop-streamer/config.json`)

```json
{
    "fps": 15,                    // Frame rate (optimized for Unity)
    "width": 1280,                // Stream width (720p for performance)
    "height": 720,                // Stream height
    "bitrate": 2000,              // Bitrate in kbps (2Mbps for live)
    "keyframe_interval": 2,       // Keyframe interval in seconds
    "segment_duration": 2,        // HLS segment duration
    "output_dir": "/tmp/hls",     // HLS output directory
    "max_restarts": 15,           // Maximum restart attempts
    "restart_delay": 60,          // Delay between restarts
    "max_errors": 10,             // Error threshold for restart
    "error_window": 600,          // Error window in seconds
    "encoder": "auto",            // Auto-detect hardware acceleration
    "live_streaming": {
        "enabled": true,
        "max_segments": 5,        // Keep only 5 segments for live feed
        "emergency_segments": 2,  // Emergency cleanup threshold
        "cleanup_threshold_percent": 70,
        "emergency_cleanup_threshold_percent": 85
    },
    "unity_optimization": {
        "enabled": true,
        "gpu_memory_limit_mb": 1024,
        "cpu_quota_percent": 30,
        "memory_limit_mb": 800,
        "disk_cleanup_threshold_percent": 70,
        "emergency_cleanup_threshold_percent": 85
    }
}
```

### Watchdog Configuration (`/etc/desktop-streamer/watchdog-config.json`)

```json
{
    "check_interval": 30,         // Monitoring check interval
    "max_alerts": 10,             // Maximum alerts per cooldown period
    "alert_cooldown": 300,        // Alert cooldown period
    "auto_recovery": {
        "service_restart": true,   // Auto-restart service on failure
        "stream_restart": true,    // Auto-restart on stream issues
        "resource_monitoring": true // Monitor resource usage
    },
    "email_alerts": {
        "enabled": false,          // Enable email alerts
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587,
        "use_tls": true,
        "from_email": "watchdog@example.com",
        "to_email": "admin@example.com",
        "username": "your-email@gmail.com",
        "password": "your-app-password"
    },
    "webhook_alerts": {
        "enabled": false,          // Enable webhook alerts
        "url": "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
    }
}
```

## 🔍 Monitoring & Self-Healing

### Health Monitoring

The system continuously monitors:

1. **Pipeline State**: GStreamer pipeline status and transitions
2. **Stream Activity**: HLS segment generation and updates
3. **Service Status**: Systemd service state and health
4. **Resource Usage**: CPU, memory, and disk utilization
5. **Error Patterns**: Error frequency and types
6. **MediaMTX Status**: Streaming server health
7. **GPU Memory**: AMD SOC GPU memory usage
8. **Live Streaming**: Segment count and cleanup status

### Automatic Recovery

The system automatically recovers from:

1. **Stuck Pipelines**: Detects and restarts frozen GStreamer pipelines
2. **Service Failures**: Restarts failed systemd services
3. **Stream Issues**: Detects inactive streams and triggers recovery
4. **High Resource Usage**: Monitors and alerts on resource exhaustion
5. **Error Thresholds**: Restarts when error counts exceed limits
6. **Disk Space Issues**: Automatic cleanup of old segments and logs
7. **Memory Leaks**: Garbage collection and memory cleanup

### Live Streaming Optimizations

- **Minimal Storage**: Keeps only 5 most recent segments (~10 seconds)
- **Aggressive Cleanup**: Automatic removal of old segments
- **Emergency Mode**: Keeps only 2 segments when disk space is critical
- **Low Latency**: Shorter playlist for faster startup
- **Daily Maintenance**: Automated cleanup via cron jobs

### Alert System

Alerts are triggered for:

- **Service Down**: Critical alert when service stops
- **Stream Inactive**: Warning when stream stops producing content
- **High Error Count**: Warning when errors exceed threshold
- **Frequent Restarts**: Critical alert for excessive restarts
- **High Resource Usage**: Warning for CPU/memory issues
- **High Disk Usage**: Warning when disk space is low
- **High GPU Memory**: Warning for GPU memory issues
- **Monitoring Errors**: Critical alert for watchdog failures

## 🎯 Kiosk & Unity Workload Optimizations

### Performance Settings
- **Reduced Quality**: 15fps, 720p, 2Mbps for Unity coexistence
- **Hardware Acceleration**: VAAPI support for AMD SOC
- **Resource Limits**: CPU (30%) and memory (2GB) quotas
- **Thread Optimization**: Limited to 2 threads for encoding

### Unity Workload Coexistence
- **GPU Memory Management**: Monitors and manages GPU memory usage
- **CPU Quota**: Prevents streaming from consuming all CPU resources
- **Memory Limits**: Prevents memory exhaustion
- **Automatic Cleanup**: Prevents disk space issues

### 24/7 Operation Features
- **Log Rotation**: Automatic log file management
- **Resource Monitoring**: Continuous resource tracking
- **Self-Healing**: Automatic recovery from failures
- **Watchdog Service**: Independent monitoring and alerting

## 🐛 Troubleshooting

### Common Issues

1. **Service Won't Start**:
   ```bash
   # Check logs
   sudo journalctl -u desktop-streamer.service -f
   
   # Check dependencies
   sudo systemctl status desktop-streamer.service
   
   # Check X11 permissions
   xhost +local:root
   ```

2. **Stream Not Working**:
   ```bash
   # Check if MediaMTX is running
   ps aux | grep mediamtx
   
   # Check HLS directory
   ls -la /tmp/hls/
   
   # Check network access
   curl -f http://0.0.0.0:8888/hls/desktop/playlist.m3u8
   ```

3. **High Resource Usage**:
   ```bash
   # Check system resources
   htop
   
   # Check GStreamer processes
   ps aux | grep gst
   
   # Check logs for errors
   sudo journalctl -u desktop-streamer.service --since "1 hour ago"
   ```

4. **Web Dashboard Not Accessible**:
   ```bash
   # Check if web monitor is running
   ps aux | grep web_monitor
   
   # Check firewall
   sudo ufw status
   
   # Test local access
   curl http://localhost:8080
   ```

5. **Live Streaming Issues**:
   ```bash
   # Check segment count
   ls -la /tmp/hls/*.ts | wc -l
   
   # Manual cleanup
   curl http://localhost:8080/api/stream/cleanup
   
   # Check disk space
   df -h /tmp
   ```

### Log Locations

- **Main Service**: `/var/log/desktop-streamer.log`
- **Watchdog**: `/var/log/desktop-streamer-watchdog.log`
- **Systemd**: `sudo journalctl -u desktop-streamer.service`
- **Systemd Watchdog**: `sudo journalctl -u desktop-streamer-watchdog.service`

### Performance Tuning

1. **For Better Unity Performance**:
   ```json
   {
       "fps": 10,
       "width": 960,
       "height": 540,
       "bitrate": 1000
   }
   ```

2. **For Higher Quality Streaming**:
   ```json
   {
       "fps": 30,
       "width": 1920,
       "height": 1080,
       "bitrate": 5000
   }
   ```

3. **For More Aggressive Cleanup**:
   ```json
   {
       "live_streaming": {
           "max_segments": 3,
           "emergency_segments": 1
       }
   }
   ```

## 🔒 Security Considerations

1. **Network Security**: The services bind to `0.0.0.0` - ensure proper firewall rules
2. **Service Permissions**: Services run as root for X11 access - consider security implications
3. **API Access**: Health API is publicly accessible - implement authentication if needed
4. **Log Security**: Logs may contain sensitive information - secure log files appropriately
5. **Resource Limits**: Configured to prevent resource exhaustion attacks

## 📊 Performance Metrics

The system provides comprehensive performance metrics:

- **Stream Quality**: Resolution, bitrate, frame rate
- **System Performance**: CPU, memory, disk usage
- **Network Performance**: Bytes sent/received
- **Error Rates**: Error frequency and types
- **Uptime**: Service availability and restart frequency
- **Recovery Time**: Time to recover from failures
- **Live Streaming**: Segment count and cleanup frequency
- **Unity Coexistence**: Resource usage and conflicts

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For issues and questions:

1. Check the troubleshooting section
2. Review the logs for error messages
3. Check the web dashboard for health metrics
4. Use the monitoring script: `desktop-streamer-monitor`
5. Open an issue on GitHub with detailed information

---

**Note**: This system is designed for production use with comprehensive monitoring and self-healing capabilities. The kiosk optimizations ensure stable 24/7 operation with Unity workloads, while the live streaming optimizations maintain minimal resource usage for real-time feeds.