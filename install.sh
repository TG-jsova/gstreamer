#!/bin/bash

# Desktop Streamer Installation Script with Kiosk Optimizations
# Enhanced for 24/7 operation with Unity workloads

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored status
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}================================${NC}"
    echo -e "${BLUE} $1${NC}"
    echo -e "${BLUE}================================${NC}"
}

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   print_error "This script must be run as root"
   exit 1
fi

print_header "Desktop Streamer Installation with Kiosk Optimizations"

# Update system
print_status "Updating system packages..."
apt update

# Install system dependencies
print_status "Installing system dependencies..."
apt install -y python3 python3-pip python3-gi python3-gi-cairo gir1.2-gstreamer-1.0 \
    gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav \
    gstreamer1.0-x gstreamer1.0-alsa gstreamer1.0-gl gstreamer1.0-gtk3 \
    gstreamer1.0-qt5 gstreamer1.0-pulseaudio libgirepository1.0-dev \
    libcairo2-dev pkg-config python3-dev build-essential xrandr \
    curl wget git htop iotop lshw logrotate

# Install VAAPI for hardware acceleration (AMD SOC)
print_status "Installing VAAPI for hardware acceleration..."
apt install -y vainfo intel-media-va-driver-non-free mesa-va-drivers mesa-vdpau-drivers

# Install Python dependencies
print_status "Installing Python dependencies..."
pip3 install -r desktop_streamer_requirements.txt

# Install MediaMTX
print_status "Installing MediaMTX..."
if ! command -v mediamtx &> /dev/null; then
    wget https://github.com/bluenviron/mediamtx/releases/latest/download/mediamtx_linux_amd64.tar.gz
    tar -xzf mediamtx_linux_amd64.tar.gz
    mv mediamtx /usr/local/bin/
    chmod +x /usr/local/bin/mediamtx
    rm mediamtx_linux_amd64.tar.gz
    print_status "MediaMTX installed successfully"
else
    print_status "MediaMTX already installed"
fi

# Create application directory
print_status "Setting up application directory..."
mkdir -p /opt/desktop-streamer
cp desktop_streamer.py /opt/desktop-streamer/
cp monitor_watchdog.py /opt/desktop-streamer/
cp web_monitor.py /opt/desktop-streamer/
chmod +x /opt/desktop-streamer/*.py

# Create configuration directory
print_status "Setting up configuration..."
mkdir -p /etc/desktop-streamer

# Copy kiosk-optimized configuration
if [ -f "kiosk-config.json" ]; then
    cp kiosk-config.json /etc/desktop-streamer/config.json
    print_status "Using kiosk-optimized configuration"
else
    # Create default configuration
    cat > /etc/desktop-streamer/config.json << 'EOF'
{
    "fps": 15,
    "width": 1280,
    "height": 720,
    "bitrate": 2000,
    "keyframe_interval": 2,
    "segment_duration": 2,
    "output_dir": "/tmp/hls",
    "max_restarts": 15,
    "restart_delay": 60,
    "max_errors": 10,
    "error_window": 600,
    "encoder": "auto",
    "unity_optimization": {
        "enabled": true,
        "gpu_memory_limit_mb": 1024,
        "cpu_quota_percent": 30,
        "memory_limit_mb": 800,
        "disk_cleanup_threshold_percent": 70,
        "emergency_cleanup_threshold_percent": 85
    }
}
EOF
fi

# Create watchdog configuration
cat > /etc/desktop-streamer/watchdog-config.json << 'EOF'
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

# Setup systemd services
print_status "Setting up systemd services..."
cp desktop-streamer.service /etc/systemd/system/
cp desktop-streamer-watchdog.service /etc/systemd/system/

# Setup log rotation
print_status "Setting up log rotation..."
cp desktop-streamer-logrotate /etc/logrotate.d/desktop-streamer

# Create log files
touch /var/log/desktop-streamer.log
touch /var/log/desktop-streamer-watchdog.log
chmod 644 /var/log/desktop-streamer*.log

# Create HLS directory
mkdir -p /tmp/hls
chmod 755 /tmp/hls

# Reload systemd and enable services
print_status "Enabling services..."
systemctl daemon-reload
systemctl enable desktop-streamer.service
systemctl enable desktop-streamer-watchdog.service

# Setup Unity workload optimizations
print_status "Setting up Unity workload optimizations..."

# Create systemd drop-in for resource limits
mkdir -p /etc/systemd/system/desktop-streamer.service.d/
cat > /etc/systemd/system/desktop-streamer.service.d/limits.conf << 'EOF'
[Service]
# Resource limits for Unity workload coexistence
MemoryMax=2G
CPUQuota=30%
LimitNOFILE=65536
LimitNPROC=4096
# GPU memory limit (if supported)
# MemoryHigh=1.5G
EOF

# Create systemd drop-in for watchdog resource limits
mkdir -p /etc/systemd/system/desktop-streamer-watchdog.service.d/
cat > /etc/systemd/system/desktop-streamer-watchdog.service.d/limits.conf << 'EOF'
[Service]
# Resource limits for watchdog
MemoryMax=512M
CPUQuota=10%
LimitNOFILE=65536
LimitNPROC=1024
EOF

# Setup periodic cleanup cron job
print_status "Setting up periodic cleanup..."
cat > /etc/cron.daily/desktop-streamer-cleanup << 'EOF'
#!/bin/bash
# Daily cleanup for desktop streamer (live streaming optimized)

# Clean up old HLS segments (keep only last 5 for live feed)
find /tmp/hls -name "*.ts" -type f -mtime +0 -delete 2>/dev/null || true

# Force cleanup to keep only 5 most recent segments
cd /tmp/hls
if [ -d "/tmp/hls" ] && [ "$(ls -1 *.ts 2>/dev/null | wc -l)" -gt 5 ]; then
    ls -t *.ts | tail -n +6 | xargs -r rm -f
fi

# Clean up old log files
find /var/log -name "desktop-streamer*.log.old" -type f -mtime +3 -delete 2>/dev/null || true

# Clean up systemd journal logs older than 3 days (more aggressive for live streaming)
journalctl --vacuum-time=3d --unit=desktop-streamer.service >/dev/null 2>&1 || true
journalctl --vacuum-time=3d --unit=desktop-streamer-watchdog.service >/dev/null 2>&1 || true

# Check disk space and alert if low
DISK_USAGE=$(df /tmp | tail -1 | awk '{print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -gt 70 ]; then
    echo "WARNING: Disk usage is ${DISK_USAGE}%" | logger -t desktop-streamer-cleanup
fi
EOF

chmod +x /etc/cron.daily/desktop-streamer-cleanup

# Setup monitoring script
print_status "Setting up monitoring script..."
cat > /usr/local/bin/desktop-streamer-monitor << 'EOF'
#!/bin/bash
# Quick monitoring script for desktop streamer

echo "=== Desktop Streamer Status ==="
systemctl status desktop-streamer.service --no-pager -l
echo ""
echo "=== Watchdog Status ==="
systemctl status desktop-streamer-watchdog.service --no-pager -l
echo ""
echo "=== Resource Usage ==="
echo "Memory:"
free -h
echo ""
echo "Disk Usage:"
df -h /tmp
echo ""
echo "Recent Logs:"
journalctl -u desktop-streamer.service --no-pager -n 10
EOF

chmod +x /usr/local/bin/desktop-streamer-monitor

# Test hardware acceleration
print_status "Testing hardware acceleration..."
if command -v vainfo &> /dev/null; then
    if vainfo 2>/dev/null | grep -q "vainfo"; then
        print_status "VAAPI hardware acceleration available"
    else
        print_warning "VAAPI hardware acceleration not available - will use software encoding"
    fi
else
    print_warning "vainfo not available - cannot test hardware acceleration"
fi

# Test GStreamer plugins
print_status "Testing GStreamer plugins..."
if gst-inspect-1.0 x264enc >/dev/null 2>&1; then
    print_status "x264enc plugin available"
else
    print_error "x264enc plugin not available - installation may be incomplete"
fi

if gst-inspect-1.0 vaapih264enc >/dev/null 2>&1; then
    print_status "vaapih264enc plugin available"
else
    print_warning "vaapih264enc plugin not available - will use software encoding"
fi

print_header "Installation Complete!"

print_status "Desktop Streamer has been installed with kiosk optimizations"
print_status "Configuration files:"
echo "  - Main config: /etc/desktop-streamer/config.json"
echo "  - Watchdog config: /etc/desktop-streamer/watchdog-config.json"
echo ""
print_status "Services:"
echo "  - desktop-streamer.service (enabled)"
echo "  - desktop-streamer-watchdog.service (enabled)"
echo ""
print_status "Logs:"
echo "  - /var/log/desktop-streamer.log"
echo "  - /var/log/desktop-streamer-watchdog.log"
echo ""
print_status "Monitoring:"
echo "  - Web dashboard: http://0.0.0.0:8080"
echo "  - Health API: http://0.0.0.0:8888/api/health"
echo "  - HLS stream: http://0.0.0.0:8888/hls/desktop/playlist.m3u8"
echo "  - Quick status: desktop-streamer-monitor"
echo ""
print_status "To start the services:"
echo "  sudo systemctl start desktop-streamer.service"
echo "  sudo systemctl start desktop-streamer-watchdog.service"
echo ""
print_warning "For Unity workload coexistence:"
echo "  - Reduced quality settings (15fps, 720p, 2Mbps)"
echo "  - Hardware acceleration enabled if available"
echo "  - Resource limits configured"
echo "  - Automatic cleanup enabled"
echo ""
print_status "Installation completed successfully!" 