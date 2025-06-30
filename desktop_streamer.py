#!/usr/bin/env python3
"""
Desktop Streamer - Captures second monitor and streams via HLS
A service for kiosk configurations to display a single screen over the network
"""

import os
import sys
import time
import signal
import logging
import subprocess
import threading
from pathlib import Path
from typing import Optional, Dict, Any
import json
import psutil

# GStreamer imports
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstVideo', '1.0')
gi.require_version('GstApp', '1.0')
from gi.repository import Gst, GstVideo, GstApp, GLib, GObject

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/desktop-streamer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class DesktopStreamer:
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the desktop streamer
        
        Args:
            config: Configuration dictionary containing stream settings
        """
        self.config = config
        self.pipeline: Optional[Gst.Pipeline] = None
        self.loop: Optional[GLib.MainLoop] = None
        self.running = False
        self.mediamtx_process: Optional[subprocess.Popen] = None
        
        # Initialize GStreamer
        Gst.init(None)
        
        # Create output directory
        self.output_dir = Path(config.get('output_dir', '/tmp/hls'))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Desktop Streamer initialized with output directory: {self.output_dir}")
    
    def get_monitor_info(self) -> Dict[str, Any]:
        """Get information about available monitors"""
        try:
            # Use xrandr to get monitor information
            result = subprocess.run(['xrandr', '--listmonitors'], 
                                  capture_output=True, text=True, check=True)
            
            monitors = []
            for line in result.stdout.strip().split('\n')[1:]:  # Skip header
                if line.strip():
                    parts = line.strip().split()
                    if len(parts) >= 4:
                        monitor_name = parts[0]
                        resolution = parts[3]
                        monitors.append({
                            'name': monitor_name,
                            'resolution': resolution
                        })
            
            logger.info(f"Found {len(monitors)} monitors: {monitors}")
            return {'monitors': monitors}
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get monitor info: {e}")
            return {'monitors': []}
    
    def create_capture_pipeline(self) -> str:
        """Create GStreamer pipeline for desktop capture and HLS streaming"""
        
        # Get monitor info
        monitor_info = self.get_monitor_info()
        if len(monitor_info['monitors']) < 2:
            logger.warning("Less than 2 monitors detected, using primary monitor")
            monitor_index = 0
        else:
            monitor_index = 1  # Use second monitor
        
        # Pipeline configuration
        fps = self.config.get('fps', 30)
        width = self.config.get('width', 1920)
        height = self.config.get('height', 1080)
        bitrate = self.config.get('bitrate', 5000)  # kbps
        keyframe_interval = self.config.get('keyframe_interval', 2)  # seconds
        
        # Create HLS playlist path
        playlist_path = self.output_dir / "playlist.m3u8"
        segment_path = self.output_dir / "segment_%05d.ts"
        segment_duration = self.config.get('segment_duration', 2)  # seconds
        
        pipeline_str = (
            f"ximagesrc monitor={monitor_index} ! "
            f"video/x-raw,framerate={fps}/1,width={width},height={height} ! "
            "videoconvert ! "
            "videoscale ! "
            f"video/x-raw,format=I420,width={width},height={height},framerate={fps}/1 ! "
            f"x264enc bitrate={bitrate} speed-preset=ultrafast key-int-max={fps * keyframe_interval} ! "
            "video/x-h264,profile=baseline ! "
            "h264parse ! "
            "mpegtsmux ! "
            f"hlssink2 location={segment_path} playlist-location={playlist_path} "
            f"target-duration={segment_duration} max-files=10"
        )
        
        logger.info(f"Created pipeline: {pipeline_str}")
        return pipeline_str
    
    def start_mediamtx(self):
        """Start MediaMTX server for HLS streaming"""
        try:
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
            
            config_path = Path("/tmp/mediamtx.yml")
            with open(config_path, 'w') as f:
                import yaml
                yaml.dump(mediamtx_config, f)
            
            # Start MediaMTX
            self.mediamtx_process = subprocess.Popen([
                'mediamtx', config_path
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            logger.info("MediaMTX started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start MediaMTX: {e}")
    
    def start_streaming(self):
        """Start the desktop capture and streaming"""
        try:
            # Start MediaMTX first
            self.start_mediamtx()
            time.sleep(2)  # Give MediaMTX time to start
            
            # Create and start GStreamer pipeline
            pipeline_str = self.create_capture_pipeline()
            self.pipeline = Gst.parse_launch(pipeline_str)
            
            if not self.pipeline:
                raise RuntimeError("Failed to create GStreamer pipeline")
            
            # Create main loop
            self.loop = GLib.MainLoop()
            
            # Add message handler
            bus = self.pipeline.get_bus()
            bus.add_signal_watch()
            bus.connect("message", self.on_message, self.loop)
            
            # Set pipeline state to playing
            ret = self.pipeline.set_state(Gst.State.PLAYING)
            if ret == Gst.StateChangeReturn.FAILURE:
                raise RuntimeError("Failed to set pipeline to PLAYING state")
            
            self.running = True
            logger.info("Desktop streaming started successfully")
            
            # Run the main loop
            self.loop.run()
            
        except Exception as e:
            logger.error(f"Failed to start streaming: {e}")
            self.cleanup()
            raise
    
    def on_message(self, bus, message, loop):
        """Handle GStreamer bus messages"""
        t = message.type
        
        if t == Gst.MessageType.EOS:
            logger.info("End of stream")
            loop.quit()
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            logger.error(f"GStreamer error: {err}, {debug}")
            loop.quit()
        elif t == Gst.MessageType.WARNING:
            err, debug = message.parse_warning()
            logger.warning(f"GStreamer warning: {err}, {debug}")
        elif t == Gst.MessageType.STATE_CHANGED:
            old_state, new_state, pending_state = message.parse_state_changed()
            if message.src == self.pipeline:
                logger.info(f"Pipeline state changed: {old_state.value_name} -> {new_state.value_name}")
    
    def stop_streaming(self):
        """Stop the streaming"""
        logger.info("Stopping desktop streaming...")
        self.running = False
        
        if self.loop and self.loop.is_running():
            self.loop.quit()
        
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
        
        if self.mediamtx_process:
            self.mediamtx_process.terminate()
            try:
                self.mediamtx_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.mediamtx_process.kill()
        
        logger.info("Desktop streaming stopped")
    
    def cleanup(self):
        """Clean up resources"""
        self.stop_streaming()
    
    def get_status(self) -> Dict[str, Any]:
        """Get current streaming status"""
        status = {
            'running': self.running,
            'pipeline_state': 'unknown',
            'mediamtx_running': False,
            'output_files': []
        }
        
        if self.pipeline:
            state = self.pipeline.get_state(0)[1]
            status['pipeline_state'] = state.value_name
        
        if self.mediamtx_process:
            status['mediamtx_running'] = self.mediamtx_process.poll() is None
        
        # Check for output files
        if self.output_dir.exists():
            status['output_files'] = [f.name for f in self.output_dir.glob("*.ts")]
            status['output_files'].extend([f.name for f in self.output_dir.glob("*.m3u8")])
        
        return status

def signal_handler(signum, frame):
    """Handle system signals"""
    logger.info(f"Received signal {signum}, shutting down...")
    if hasattr(signal_handler, 'streamer'):
        signal_handler.streamer.cleanup()
    sys.exit(0)

def main():
    """Main function"""
    # Default configuration
    config = {
        'fps': 30,
        'width': 1920,
        'height': 1080,
        'bitrate': 5000,  # kbps
        'keyframe_interval': 2,  # seconds
        'segment_duration': 2,  # seconds
        'output_dir': '/tmp/hls'
    }
    
    # Load config from file if it exists
    config_file = Path('/etc/desktop-streamer/config.json')
    if config_file.exists():
        try:
            with open(config_file, 'r') as f:
                file_config = json.load(f)
                config.update(file_config)
        except Exception as e:
            logger.warning(f"Failed to load config file: {e}")
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create and start streamer
    streamer = DesktopStreamer(config)
    signal_handler.streamer = streamer
    
    try:
        logger.info("Starting Desktop Streamer service...")
        streamer.start_streaming()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    finally:
        streamer.cleanup()

if __name__ == "__main__":
    main() 