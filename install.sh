#!/bin/bash

# Desktop Streamer Installation Script for Ubuntu
# This script installs the desktop streamer as a system service

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   print_error "This script must be run as root"
   exit 1
fi

print_status "Starting Desktop Streamer installation..."

# Update package list
print_status "Updating package list..."
apt-get update

# Install system dependencies
print_status "Installing system dependencies..."
apt-get install -y \
    python3 \
    python3-pip \
    python3-gi \
    python3-gi-cairo \
    gir1.2-gstreamer-1.0 \
    gir1.2-gst-plugins-base-1.0 \
    gir1.2-gst-plugins-bad-1.0 \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    gstreamer1.0-tools \
    gstreamer1.0-x \
    gstreamer1.0-alsa \
    gstreamer1.0-gl \
    gstreamer1.0-gtk3 \
    gstreamer1.0-qt5 \
    gstreamer1.0-pulseaudio \
    libgstreamer1.0-dev \
    libgstreamer-plugins-base1.0-dev \
    libgstreamer-plugins-bad1.0-dev \
    x11-apps \
    xvfb \
    x11vnc \
    xrandr \
    x11-utils \
    xauth \
    curl \
    wget \
    ca-certificates

# Install MediaMTX
print_status "Installing MediaMTX..."
if ! command -v mediamtx &> /dev/null; then
    wget -O /tmp/mediamtx.tar.gz https://github.com/bluenviron/mediamtx/releases/latest/download/mediamtx_linux_amd64.tar.gz
    tar -xzf /tmp/mediamtx.tar.gz -C /usr/local/bin/
    chmod +x /usr/local/bin/mediamtx
    rm /tmp/mediamtx.tar.gz
    print_status "MediaMTX installed successfully"
else
    print_status "MediaMTX already installed"
fi

# Create application directory
print_status "Creating application directory..."
mkdir -p /opt/desktop-streamer
mkdir -p /etc/desktop-streamer
mkdir -p /var/log
mkdir -p /tmp/hls

# Copy application files
print_status "Copying application files..."
cp desktop_streamer.py /opt/desktop-streamer/
cp desktop_streamer_requirements.txt /opt/desktop-streamer/
chmod +x /opt/desktop-streamer/desktop_streamer.py

# Install Python dependencies
print_status "Installing Python dependencies..."
pip3 install -r desktop_streamer_requirements.txt

# Create default configuration
print_status "Creating default configuration..."
cat > /etc/desktop-streamer/config.json << EOF
{
    "fps": 30,
    "width": 1920,
    "height": 1080,
    "bitrate": 5000,
    "keyframe_interval": 2,
    "segment_duration": 2,
    "output_dir": "/tmp/hls"
}
EOF

# Copy systemd service file
print_status "Installing systemd service..."
cp desktop-streamer.service /etc/systemd/system/
systemctl daemon-reload

# Set up X11 permissions
print_status "Setting up X11 permissions..."
if [ -n "$SUDO_USER" ]; then
    # If running with sudo, copy Xauthority from the user
    if [ -f "/home/$SUDO_USER/.Xauthority" ]; then
        cp "/home/$SUDO_USER/.Xauthority" /root/.Xauthority
        chown root:root /root/.Xauthority
        print_status "X11 permissions configured"
    else
        print_warning "Could not find .Xauthority file for user $SUDO_USER"
        print_warning "You may need to run 'xhost +local:root' to allow X11 access"
    fi
fi

# Enable and start the service
print_status "Enabling and starting the service..."
systemctl enable desktop-streamer.service
systemctl start desktop-streamer.service

# Wait a moment for the service to start
sleep 5

# Check service status
if systemctl is-active --quiet desktop-streamer.service; then
    print_status "Desktop Streamer service is running successfully!"
    print_status "HLS stream should be available at: http://0.0.0.0:8888/hls/desktop/playlist.m3u8"
else
    print_error "Service failed to start. Check logs with: journalctl -u desktop-streamer.service"
    exit 1
fi

# Display useful commands
print_status "Installation completed successfully!"
echo ""
echo "Useful commands:"
echo "  Check service status: systemctl status desktop-streamer.service"
echo "  View logs: journalctl -u desktop-streamer.service -f"
echo "  Stop service: systemctl stop desktop-streamer.service"
echo "  Start service: systemctl start desktop-streamer.service"
echo "  Restart service: systemctl restart desktop-streamer.service"
echo ""
echo "HLS Stream URL: http://0.0.0.0:8888/hls/desktop/playlist.m3u8"
echo "Configuration file: /etc/desktop-streamer/config.json"
echo "" 