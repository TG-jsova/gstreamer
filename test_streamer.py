#!/usr/bin/env python3
"""
Test script for Desktop Streamer
Verifies that all components are working correctly
"""

import os
import sys
import time
import subprocess
import requests
import json
from pathlib import Path

def print_status(message, status="INFO"):
    """Print a status message with color coding"""
    colors = {
        "INFO": "\033[94m",    # Blue
        "SUCCESS": "\033[92m", # Green
        "WARNING": "\033[93m", # Yellow
        "ERROR": "\033[91m",   # Red
    }
    color = colors.get(status, colors["INFO"])
    print(f"{color}[{status}]{'\033[0m'} {message}")

def test_system_dependencies():
    """Test if required system dependencies are installed"""
    print_status("Testing system dependencies...")
    
    dependencies = [
        ("python3", "Python 3"),
        ("gst-launch-1.0", "GStreamer"),
        ("xrandr", "X11 utilities"),
        ("mediamtx", "MediaMTX"),
    ]
    
    all_installed = True
    for cmd, name in dependencies:
        try:
            result = subprocess.run([cmd, "--version"], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                print_status(f"✓ {name} is installed", "SUCCESS")
            else:
                print_status(f"✗ {name} is not working properly", "ERROR")
                all_installed = False
        except FileNotFoundError:
            print_status(f"✗ {name} is not installed", "ERROR")
            all_installed = False
        except subprocess.TimeoutExpired:
            print_status(f"✗ {name} timed out", "ERROR")
            all_installed = False
    
    return all_installed

def test_python_dependencies():
    """Test if required Python packages are installed"""
    print_status("Testing Python dependencies...")
    
    try:
        import gi
        gi.require_version('Gst', '1.0')
        from gi.repository import Gst
        print_status("✓ PyGObject and GStreamer bindings are available", "SUCCESS")
        
        import psutil
        print_status("✓ psutil is available", "SUCCESS")
        
        import yaml
        print_status("✓ PyYAML is available", "SUCCESS")
        
        return True
    except ImportError as e:
        print_status(f"✗ Missing Python dependency: {e}", "ERROR")
        return False
    except Exception as e:
        print_status(f"✗ Error testing Python dependencies: {e}", "ERROR")
        return False

def test_x11_environment():
    """Test X11 environment and monitor configuration"""
    print_status("Testing X11 environment...")
    
    # Check DISPLAY variable
    display = os.environ.get('DISPLAY')
    if display:
        print_status(f"✓ DISPLAY is set to: {display}", "SUCCESS")
    else:
        print_status("✗ DISPLAY environment variable is not set", "ERROR")
        return False
    
    # Check monitor configuration
    try:
        result = subprocess.run(['xrandr', '--listmonitors'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            monitors = result.stdout.strip().split('\n')[1:]  # Skip header
            monitor_count = len([m for m in monitors if m.strip()])
            print_status(f"✓ Found {monitor_count} monitor(s)", "SUCCESS")
            
            if monitor_count >= 2:
                print_status("✓ Second monitor detected - ready for capture", "SUCCESS")
                return True
            else:
                print_status("⚠ Only one monitor detected - will use primary monitor", "WARNING")
                return True
        else:
            print_status("✗ Failed to get monitor information", "ERROR")
            return False
    except Exception as e:
        print_status(f"✗ Error testing X11: {e}", "ERROR")
        return False

def test_gstreamer_pipeline():
    """Test if GStreamer can create a simple pipeline"""
    print_status("Testing GStreamer pipeline creation...")
    
    try:
        import gi
        gi.require_version('Gst', '1.0')
        from gi.repository import Gst
        
        Gst.init(None)
        
        # Test a simple pipeline
        pipeline_str = "videotestsrc ! videoconvert ! fakesink"
        pipeline = Gst.parse_launch(pipeline_str)
        
        if pipeline:
            print_status("✓ GStreamer pipeline creation successful", "SUCCESS")
            pipeline.set_state(Gst.State.NULL)
            return True
        else:
            print_status("✗ Failed to create GStreamer pipeline", "ERROR")
            return False
    except Exception as e:
        print_status(f"✗ Error testing GStreamer: {e}", "ERROR")
        return False

def test_service_status():
    """Test if the desktop-streamer service is running"""
    print_status("Testing service status...")
    
    try:
        result = subprocess.run(['systemctl', 'is-active', 'desktop-streamer.service'],
                              capture_output=True, text=True, timeout=5)
        
        if result.returncode == 0 and result.stdout.strip() == "active":
            print_status("✓ Desktop streamer service is running", "SUCCESS")
            return True
        else:
            print_status("✗ Desktop streamer service is not running", "ERROR")
            return False
    except Exception as e:
        print_status(f"✗ Error checking service status: {e}", "ERROR")
        return False

def test_web_monitor():
    """Test if the web monitor is accessible"""
    print_status("Testing web monitor...")
    
    try:
        response = requests.get("http://0.0.0.0:8080", timeout=5)
        if response.status_code == 200:
            print_status("✓ Web monitor is accessible", "SUCCESS")
            return True
        else:
            print_status(f"✗ Web monitor returned status code: {response.status_code}", "ERROR")
            return False
    except requests.exceptions.RequestException as e:
        print_status(f"✗ Web monitor is not accessible: {e}", "ERROR")
        return False

def test_hls_stream():
    """Test if the HLS stream is available"""
    print_status("Testing HLS stream...")
    
    try:
        response = requests.get("http://0.0.0.0:8888/hls/desktop/playlist.m3u8", timeout=5)
        if response.status_code == 200:
            print_status("✓ HLS stream is available", "SUCCESS")
            return True
        else:
            print_status(f"✗ HLS stream returned status code: {response.status_code}", "ERROR")
            return False
    except requests.exceptions.RequestException as e:
        print_status(f"✗ HLS stream is not accessible: {e}", "ERROR")
        return False

def test_configuration():
    """Test if configuration file exists and is valid"""
    print_status("Testing configuration...")
    
    config_path = Path("/etc/desktop-streamer/config.json")
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            required_keys = ['fps', 'width', 'height', 'bitrate']
            missing_keys = [key for key in required_keys if key not in config]
            
            if not missing_keys:
                print_status("✓ Configuration file is valid", "SUCCESS")
                return True
            else:
                print_status(f"✗ Configuration missing keys: {missing_keys}", "ERROR")
                return False
        except json.JSONDecodeError:
            print_status("✗ Configuration file is not valid JSON", "ERROR")
            return False
    else:
        print_status("✗ Configuration file does not exist", "ERROR")
        return False

def main():
    """Run all tests"""
    print_status("Starting Desktop Streamer tests...", "INFO")
    print("=" * 50)
    
    tests = [
        ("System Dependencies", test_system_dependencies),
        ("Python Dependencies", test_python_dependencies),
        ("X11 Environment", test_x11_environment),
        ("GStreamer Pipeline", test_gstreamer_pipeline),
        ("Configuration", test_configuration),
        ("Service Status", test_service_status),
        ("Web Monitor", test_web_monitor),
        ("HLS Stream", test_hls_stream),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n{test_name}:")
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print_status(f"✗ Test failed with exception: {e}", "ERROR")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 50)
    print_status("Test Summary:", "INFO")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        color = "\033[92m" if result else "\033[91m"
        print(f"{color}{status}{'\033[0m'} - {test_name}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print_status("All tests passed! Desktop Streamer is working correctly.", "SUCCESS")
        print_status("Access the web monitor at: http://0.0.0.0:8080", "INFO")
        print_status("HLS stream URL: http://0.0.0.0:8888/hls/desktop/playlist.m3u8", "INFO")
        return 0
    else:
        print_status("Some tests failed. Please check the errors above.", "ERROR")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 