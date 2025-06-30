#!/bin/bash

# Desktop Streamer Test Launcher
# Quick script to run the desktop streamer for testing

set -e

echo "🎬 Desktop Streamer Test Launcher"
echo "=================================="

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed"
    exit 1
fi

# Check if we're in the right directory
if [ ! -f "desktop_streamer.py" ]; then
    echo "❌ Please run this script from the gstreamer directory"
    exit 1
fi

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --list-screens     List available screens and exit"
    echo "  --screen N         Capture screen N (0=primary, 1=secondary, etc.)"
    echo "  --fps N            Set FPS (default: 30)"
    echo "  --resolution WxH   Set resolution (default: 1920x1080)"
    echo "  --bitrate N        Set bitrate in kbps (default: 8000)"
    echo "  --latency N        Set target latency in ms (default: 100)"
    echo "  --no-mediamtx      Skip starting MediaMTX server"
    echo "  --no-monitor       Skip starting web monitor"
    echo "  --output-dir DIR   Set output directory (default: /tmp/hls_test)"
    echo "  --help             Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                                    # Default settings (30fps, 1080p, screen 1)"
    echo "  $0 --list-screens                     # List available screens"
    echo "  $0 --screen 0 --fps 60                # Capture primary screen at 60fps"
    echo "  $0 --resolution 1280x720 --fps 25     # 720p at 25fps"
    echo "  $0 --latency 50 --bitrate 12000       # Ultra-low latency, high quality"
    echo ""
}

# Parse command line arguments
ARGS=()
while [[ $# -gt 0 ]]; do
    case $1 in
        --help)
            show_usage
            exit 0
            ;;
        --list-screens)
            python3 run_test.py --list-screens
            exit 0
            ;;
        *)
            ARGS+=("$1")
            shift
            ;;
    esac
done

# Set default values for real-time streaming
DEFAULT_ARGS=(
    "--fps" "30"
    "--resolution" "1920x1080"
    "--bitrate" "8000"
    "--latency" "100"
    "--screen" "1"
)

# Combine default args with user args
FINAL_ARGS=("${DEFAULT_ARGS[@]}" "${ARGS[@]}")

echo "🚀 Starting Desktop Streamer with real-time optimization..."
echo "   Press Ctrl+C to stop"
echo ""

# Run the test script
python3 run_test.py "${FINAL_ARGS[@]}" 