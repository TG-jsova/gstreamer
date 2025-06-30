#!/usr/bin/env python3
"""
Desktop Streamer Test Runner
Run the desktop streamer directly from terminal for testing purposes
"""

import os
import sys
import json
import signal
import time
import subprocess
from pathlib import Path
import argparse

def create_test_config():
    """Create a test configuration file optimized for real-time streaming"""
    config = {
        "fps": 30,  # Minimum 30fps for real-time sync
        "width": 1920,  # 1080p native resolution
        "height": 1080,
        "bitrate": 8000,  # Higher bitrate for 1080p quality
        "keyframe_interval": 1,  # More frequent keyframes for real-time
        "segment_duration": 1,  # 1-second segments for minimal latency
        "output_dir": "/tmp/hls_test",
        "max_restarts": 5,
        "restart_delay": 30,
        "max_errors": 5,
        "error_window": 300,
        "encoder": "auto",
        "screen": 1,  # Capture second screen (index 1)
        "real_time": {
            "enabled": True,
            "min_fps": 30,
            "target_latency_ms": 100,  # Target 100ms latency
            "buffer_size": 0.1,  # 100ms buffer
            "drop_frames": True,  # Drop frames to maintain sync
            "sync_tolerance_ms": 50  # 50ms sync tolerance
        },
        "live_streaming": {
            "enabled": True,
            "max_segments": 3,  # Fewer segments for lower latency
            "emergency_segments": 1,
            "cleanup_threshold_percent": 70,
            "emergency_cleanup_threshold_percent": 85
        },
        "unity_optimization": {
            "enabled": True,
            "gpu_memory_limit_mb": 2048,  # More GPU memory for 1080p
            "cpu_quota_percent": 50,  # More CPU for real-time encoding
            "memory_limit_mb": 1200,
            "disk_cleanup_threshold_percent": 70,
            "emergency_cleanup_threshold_percent": 85
        }
    }
    
    config_path = Path("test-config.json")
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    
    return config_path

def detect_screens():
    """Detect available screens and their properties"""
    print("🖥️  Detecting screens...")
    
    try:
        result = subprocess.run(['xrandr', '--listmonitors'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            screens = []
            
            for line in lines[1:]:  # Skip header
                if line.strip():
                    parts = line.strip().split()
                    if len(parts) >= 4:
                        screen_info = {
                            'index': len(screens),
                            'name': parts[0],
                            'resolution': parts[3],
                            'primary': '*' in line
                        }
                        screens.append(screen_info)
                        print(f"   Screen {screen_info['index']}: {screen_info['name']} "
                              f"({screen_info['resolution']}) "
                              f"{'[PRIMARY]' if screen_info['primary'] else ''}")
            
            return screens
        else:
            print("❌ Failed to detect screens")
            return []
            
    except Exception as e:
        print(f"❌ Error detecting screens: {e}")
        return []

def check_dependencies():
    """Check if required dependencies are available"""
    print("🔍 Checking dependencies...")
    
    # Check Python modules
    try:
        import gi
        gi.require_version('Gst', '1.0')
        from gi.repository import Gst
        print("✅ GStreamer Python bindings available")
    except ImportError as e:
        print(f"❌ GStreamer Python bindings not available: {e}")
        return False
    
    # Check GStreamer plugins
    plugins_to_check = ['ximagesrc', 'x264enc', 'h264parse', 'mpegtsmux', 'hlssink2']
    for plugin in plugins_to_check:
        try:
            result = subprocess.run(['gst-inspect-1.0', plugin], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                print(f"✅ GStreamer plugin '{plugin}' available")
            else:
                print(f"❌ GStreamer plugin '{plugin}' not available")
                return False
        except Exception as e:
            print(f"❌ Error checking plugin '{plugin}': {e}")
            return False
    
    # Check MediaMTX
    try:
        result = subprocess.run(['mediamtx', '--version'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print("✅ MediaMTX available")
        else:
            print("❌ MediaMTX not available")
            return False
    except Exception as e:
        print(f"❌ MediaMTX not available: {e}")
        return False
    
    # Check X11 and detect screens
    try:
        result = subprocess.run(['xrandr', '--listmonitors'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print("✅ X11 display available")
            screens = detect_screens()
            if len(screens) < 2:
                print(f"⚠️  Only {len(screens)} screen(s) detected. Second screen capture may not work.")
            return True
        else:
            print("❌ X11 display not available")
            return False
    except Exception as e:
        print(f"❌ X11 display not available: {e}")
        return False

def start_mediamtx():
    """Start MediaMTX server for testing"""
    print("🚀 Starting MediaMTX server...")
    
    # Create MediaMTX config
    mediamtx_config = {
        "paths": {
            "desktop": {
                "source": "publisher",
                "sourceOnDemand": True,
                "publishUser": "admin",
                "publishPass": "admin123"
            }
        },
        "hls": {
            "enabled": True,
            "address": "0.0.0.0",
            "port": 8888,
            "path": "/hls"
        },
        "rtmp": {
            "enabled": False
        },
        "webrtc": {
            "enabled": False
        }
    }
    
    config_path = Path("mediamtx-test.yml")
    with open(config_path, 'w') as f:
        import yaml
        yaml.dump(mediamtx_config, f)
    
    # Start MediaMTX
    try:
        process = subprocess.Popen([
            'mediamtx', config_path
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Wait a moment for MediaMTX to start
        time.sleep(2)
        
        if process.poll() is None:
            print("✅ MediaMTX started successfully")
            return process
        else:
            print("❌ MediaMTX failed to start")
            return None
            
    except Exception as e:
        print(f"❌ Failed to start MediaMTX: {e}")
        return None

def start_web_monitor():
    """Start web monitor for testing"""
    print("🌐 Starting web monitor...")
    
    try:
        # Import and start web monitor
        sys.path.insert(0, '.')
        from web_monitor import app
        import uvicorn
        
        # Start in a separate thread
        import threading
        def run_monitor():
            uvicorn.run(app, host="0.0.0.0", port=8080, log_level="error")
        
        monitor_thread = threading.Thread(target=run_monitor, daemon=True)
        monitor_thread.start()
        
        # Wait a moment for the server to start
        time.sleep(3)
        print("✅ Web monitor started at http://localhost:8080")
        return True
        
    except Exception as e:
        print(f"❌ Failed to start web monitor: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Desktop Streamer Test Runner')
    parser.add_argument('--no-mediamtx', action='store_true', 
                       help='Skip starting MediaMTX server')
    parser.add_argument('--no-monitor', action='store_true', 
                       help='Skip starting web monitor')
    parser.add_argument('--config', type=str, default=None,
                       help='Path to custom configuration file')
    parser.add_argument('--output-dir', type=str, default='/tmp/hls_test',
                       help='Output directory for HLS segments')
    parser.add_argument('--screen', type=int, default=1,
                       help='Screen to capture (0=primary, 1=secondary, etc.)')
    parser.add_argument('--fps', type=int, default=30,
                       help='Target FPS (default: 30)')
    parser.add_argument('--resolution', type=str, default='1920x1080',
                       help='Capture resolution (default: 1920x1080)')
    parser.add_argument('--bitrate', type=int, default=8000,
                       help='Video bitrate in kbps (default: 8000)')
    parser.add_argument('--latency', type=int, default=100,
                       help='Target latency in ms (default: 100)')
    parser.add_argument('--list-screens', action='store_true',
                       help='List available screens and exit')
    
    args = parser.parse_args()
    
    print("🎬 Desktop Streamer Test Runner")
    print("=" * 40)
    
    # List screens if requested
    if args.list_screens:
        detect_screens()
        return
    
    # Check dependencies
    if not check_dependencies():
        print("\n❌ Dependency check failed. Please install missing dependencies.")
        sys.exit(1)
    
    # Parse resolution
    try:
        width, height = map(int, args.resolution.split('x'))
    except ValueError:
        print(f"❌ Invalid resolution format: {args.resolution}. Use format: WIDTHxHEIGHT")
        sys.exit(1)
    
    # Create test configuration
    if args.config:
        config_path = Path(args.config)
        if not config_path.exists():
            print(f"❌ Configuration file not found: {args.config}")
            sys.exit(1)
    else:
        config_path = create_test_config()
        print(f"✅ Created test configuration: {config_path}")
        
        # Override with command line arguments
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        config.update({
            'fps': args.fps,
            'width': width,
            'height': height,
            'bitrate': args.bitrate,
            'screen': args.screen,
            'real_time': {
                'enabled': True,
                'min_fps': args.fps,
                'target_latency_ms': args.latency,
                'buffer_size': args.latency / 1000.0,  # Convert ms to seconds
                'drop_frames': True,
                'sync_tolerance_ms': args.latency // 2
            }
        })
        
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        print(f"✅ Updated configuration:")
        print(f"   Screen: {args.screen}")
        print(f"   Resolution: {width}x{height}")
        print(f"   FPS: {args.fps}")
        print(f"   Bitrate: {args.bitrate} kbps")
        print(f"   Target Latency: {args.latency}ms")
    
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"✅ Output directory: {output_dir}")
    
    # Start MediaMTX if requested
    mediamtx_process = None
    if not args.no_mediamtx:
        mediamtx_process = start_mediamtx()
        if not mediamtx_process:
            print("❌ Failed to start MediaMTX. Exiting.")
            sys.exit(1)
    
    # Start web monitor if requested
    if not args.no_monitor:
        if not start_web_monitor():
            print("⚠️  Web monitor failed to start, continuing without it...")
    
    # Set up signal handler for graceful shutdown
    def signal_handler(signum, frame):
        print("\n🛑 Shutting down...")
        if mediamtx_process:
            mediamtx_process.terminate()
            try:
                mediamtx_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                mediamtx_process.kill()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start the desktop streamer
    print("\n🎥 Starting Desktop Streamer...")
    print("Press Ctrl+C to stop")
    print("=" * 40)
    
    try:
        # Import and run the desktop streamer
        sys.path.insert(0, '.')
        from desktop_streamer import DesktopStreamer
        
        # Load configuration
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Override output directory if specified
        config['output_dir'] = str(output_dir)
        
        # Create and start streamer
        streamer = DesktopStreamer(config)
        
        # Start health API
        streamer.start_health_api()
        time.sleep(2)
        
        # Start streaming
        streamer.start_streaming()
        
    except KeyboardInterrupt:
        print("\n🛑 Received interrupt signal")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n🧹 Cleaning up...")
        if mediamtx_process:
            mediamtx_process.terminate()
            try:
                mediamtx_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                mediamtx_process.kill()
        
        # Clean up test files
        try:
            if Path("test-config.json").exists():
                Path("test-config.json").unlink()
            if Path("mediamtx-test.yml").exists():
                Path("mediamtx-test.yml").unlink()
        except:
            pass
        
        print("✅ Cleanup completed")

if __name__ == "__main__":
    main() 