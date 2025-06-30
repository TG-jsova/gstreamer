#!/usr/bin/env python3
"""
Desktop Streamer - Captures second monitor and streams via HLS
A service for kiosk configurations to display a single screen over the network
Enhanced with self-healing capabilities and health monitoring
"""

import os
import sys
import time
import signal
import logging
import subprocess
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List
import json
import psutil
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import queue

# GStreamer imports
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstVideo', '1.0')
gi.require_version('GstApp', '1.0')
from gi.repository import Gst, GstVideo, GstApp, GLib, GObject

# FastAPI for health endpoint
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn
from threading import Thread

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

@dataclass
class HealthMetrics:
    """Health metrics for monitoring stream health"""
    timestamp: float
    pipeline_state: str
    mediamtx_running: bool
    stream_active: bool
    error_count: int
    restart_count: int
    last_error: Optional[str] = None
    stream_duration: Optional[float] = None
    buffer_level: Optional[float] = None
    fps: Optional[float] = None
    bitrate: Optional[float] = None

@dataclass
class ErrorEvent:
    """Error event tracking"""
    timestamp: float
    error_type: str
    error_message: str
    pipeline_state: str
    recovery_action: str

class HealthMonitor:
    """Health monitoring and self-healing system"""
    
    def __init__(self, max_errors: int = 5, error_window: int = 300):
        self.max_errors = max_errors
        self.error_window = error_window  # seconds
        self.error_events: List[ErrorEvent] = []
        self.health_metrics: List[HealthMetrics] = []
        self.max_metrics_history = 1000
        self.monitoring_active = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        
    def add_error_event(self, error_type: str, error_message: str, 
                       pipeline_state: str, recovery_action: str):
        """Add an error event to the tracking system"""
        event = ErrorEvent(
            timestamp=time.time(),
            error_type=error_type,
            error_message=error_message,
            pipeline_state=pipeline_state,
            recovery_action=recovery_action
        )
        self.error_events.append(event)
        
        # Clean old events
        cutoff_time = time.time() - self.error_window
        self.error_events = [e for e in self.error_events if e.timestamp > cutoff_time]
        
        logger.warning(f"Error event: {error_type} - {error_message} (Recovery: {recovery_action})")
    
    def add_health_metrics(self, metrics: HealthMetrics):
        """Add health metrics to the tracking system"""
        self.health_metrics.append(metrics)
        
        # Keep only recent metrics
        if len(self.health_metrics) > self.max_metrics_history:
            self.health_metrics = self.health_metrics[-self.max_metrics_history:]
    
    def should_restart(self) -> bool:
        """Determine if a restart is needed based on error patterns"""
        if len(self.error_events) >= self.max_errors:
            logger.error(f"Too many errors ({len(self.error_events)}) in {self.error_window}s, restart needed")
            return True
        return False
    
    def get_recent_errors(self, minutes: int = 10) -> List[ErrorEvent]:
        """Get recent error events"""
        cutoff_time = time.time() - (minutes * 60)
        return [e for e in self.error_events if e.timestamp > cutoff_time]
    
    def get_health_summary(self) -> Dict[str, Any]:
        """Get health summary for monitoring"""
        recent_metrics = self.health_metrics[-10:] if self.health_metrics else []
        
        return {
            'monitoring_active': self.monitoring_active,
            'total_errors': len(self.error_events),
            'recent_errors': len(self.get_recent_errors(5)),
            'current_state': recent_metrics[-1].pipeline_state if recent_metrics else 'unknown',
            'stream_active': recent_metrics[-1].stream_active if recent_metrics else False,
            'mediamtx_running': recent_metrics[-1].mediamtx_running if recent_metrics else False,
            'restart_count': recent_metrics[-1].restart_count if recent_metrics else 0,
            'last_error': recent_metrics[-1].last_error if recent_metrics else None,
            'uptime_minutes': (time.time() - recent_metrics[0].timestamp) / 60 if recent_metrics else 0
        }

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
        self.restart_count = 0
        self.max_restarts = config.get('max_restarts', 10)
        self.restart_delay = config.get('restart_delay', 30)
        
        # Health monitoring
        self.health_monitor = HealthMonitor(
            max_errors=config.get('max_errors', 5),
            error_window=config.get('error_window', 300)
        )
        
        # Initialize GStreamer
        Gst.init(None)
        
        # Create output directory
        self.output_dir = Path(config.get('output_dir', '/tmp/hls'))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Start health monitoring
        self.health_monitor.monitoring_active = True
        self.start_health_monitoring()
        
        # Initialize FastAPI for health endpoint
        self.app = FastAPI(title="Desktop Streamer Health API", version="1.0.0")
        self.setup_health_endpoints()
        
        logger.info(f"Desktop Streamer initialized with output directory: {self.output_dir}")
    
    def setup_health_endpoints(self):
        """Setup FastAPI health endpoints"""
        
        @self.app.get("/api/health")
        async def get_health():
            """Get current health metrics"""
            return self.health_monitor.get_health_summary()
        
        @self.app.get("/api/status")
        async def get_status():
            """Get current streaming status"""
            return self.get_status()
        
        @self.app.get("/api/health/detailed")
        async def get_detailed_health():
            """Get detailed health information"""
            return {
                "health_summary": self.health_monitor.get_health_summary(),
                "recent_errors": [asdict(e) for e in self.health_monitor.get_recent_errors(10)],
                "metrics_history": [asdict(m) for m in self.health_monitor.health_metrics[-20:]]
            }
    
    def start_health_api(self):
        """Start the health API server in a separate thread"""
        def run_api():
            uvicorn.run(self.app, host="0.0.0.0", port=8888, log_level="error")
        
        api_thread = Thread(target=run_api, daemon=True)
        api_thread.start()
        logger.info("Health API started on port 8888")
    
    def start_health_monitoring(self):
        """Start the health monitoring thread"""
        self.health_monitor.monitor_thread = threading.Thread(
            target=self._health_monitor_loop,
            daemon=True
        )
        self.health_monitor.monitor_thread.start()
        logger.info("Health monitoring started")
    
    def _health_monitor_loop(self):
        """Health monitoring loop"""
        while not self.health_monitor.stop_event.is_set():
            try:
                # Collect health metrics
                metrics = self._collect_health_metrics()
                self.health_monitor.add_health_metrics(metrics)
                
                # Check if restart is needed
                if self.health_monitor.should_restart() and self.restart_count < self.max_restarts:
                    logger.warning("Health monitor detected critical issues, initiating restart")
                    self._schedule_restart()
                
                # Check for stuck pipeline
                if self._is_pipeline_stuck():
                    logger.warning("Pipeline appears to be stuck, initiating recovery")
                    self._recover_stuck_pipeline()
                
                time.sleep(10)  # Check every 10 seconds
                
            except Exception as e:
                logger.error(f"Error in health monitoring loop: {e}")
                time.sleep(30)  # Wait longer on error
    
    def _collect_health_metrics(self) -> HealthMetrics:
        """Collect current health metrics"""
        pipeline_state = 'unknown'
        stream_active = False
        buffer_level = None
        fps = None
        bitrate = None
        
        if self.pipeline:
            state = self.pipeline.get_state(0)[1]
            pipeline_state = state.value_name
            stream_active = state == Gst.State.PLAYING
        
        mediamtx_running = False
        if self.mediamtx_process:
            mediamtx_running = self.mediamtx_process.poll() is None
        
        return HealthMetrics(
            timestamp=time.time(),
            pipeline_state=pipeline_state,
            mediamtx_running=mediamtx_running,
            stream_active=stream_active,
            error_count=len(self.health_monitor.error_events),
            restart_count=self.restart_count,
            last_error=self.health_monitor.error_events[-1].error_message if self.health_monitor.error_events else None,
            buffer_level=buffer_level,
            fps=fps,
            bitrate=bitrate
        )
    
    def _is_pipeline_stuck(self) -> bool:
        """Check if pipeline is stuck in a bad state"""
        if not self.pipeline:
            return False
        
        state = self.pipeline.get_state(0)[1]
        
        # Check if pipeline is stuck in PAUSED state for too long
        if state == Gst.State.PAUSED:
            # Get recent metrics to see how long it's been paused
            recent_metrics = self.health_monitor.health_metrics[-6:]  # Last minute (6 * 10s)
            if len(recent_metrics) >= 6:
                paused_count = sum(1 for m in recent_metrics if m.pipeline_state == 'PAUSED')
                if paused_count >= 5:  # Stuck for 50+ seconds
                    return True
        
        return False
    
    def _recover_stuck_pipeline(self):
        """Recover from a stuck pipeline"""
        try:
            logger.info("Attempting to recover stuck pipeline")
            
            # Try to restart the pipeline
            if self.pipeline:
                self.pipeline.set_state(Gst.State.NULL)
                time.sleep(1)
                self.pipeline.set_state(Gst.State.PLAYING)
            
            self.health_monitor.add_error_event(
                'pipeline_stuck',
                'Pipeline was stuck in PAUSED state',
                'PAUSED',
                'pipeline_restart'
            )
            
        except Exception as e:
            logger.error(f"Failed to recover stuck pipeline: {e}")
            self.health_monitor.add_error_event(
                'recovery_failed',
                str(e),
                'UNKNOWN',
                'full_restart'
            )
    
    def _schedule_restart(self):
        """Schedule a full service restart"""
        def delayed_restart():
            time.sleep(self.restart_delay)
            logger.info(f"Performing scheduled restart (attempt {self.restart_count + 1}/{self.max_restarts})")
            self.restart_count += 1
            self.cleanup()
            os._exit(1)  # Force exit to trigger systemd restart
        
        restart_thread = threading.Thread(target=delayed_restart, daemon=True)
        restart_thread.start()
    
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
            self.health_monitor.add_error_event(
                'mediamtx_start_failed',
                str(e),
                'UNKNOWN',
                'retry_mediamtx'
            )
    
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
            self.health_monitor.add_error_event(
                'stream_start_failed',
                str(e),
                'UNKNOWN',
                'full_restart'
            )
            self.cleanup()
            raise
    
    def on_message(self, bus, message, loop):
        """Handle GStreamer bus messages"""
        t = message.type
        
        if t == Gst.MessageType.EOS:
            logger.info("End of stream")
            self.health_monitor.add_error_event(
                'end_of_stream',
                'Stream ended unexpectedly',
                'PLAYING',
                'restart_stream'
            )
            loop.quit()
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            error_msg = f"GStreamer error: {err}, {debug}"
            logger.error(error_msg)
            self.health_monitor.add_error_event(
                'gstreamer_error',
                error_msg,
                'ERROR',
                'pipeline_restart'
            )
            loop.quit()
        elif t == Gst.MessageType.WARNING:
            err, debug = message.parse_warning()
            warning_msg = f"GStreamer warning: {err}, {debug}"
            logger.warning(warning_msg)
            self.health_monitor.add_error_event(
                'gstreamer_warning',
                warning_msg,
                'WARNING',
                'monitor'
            )
        elif t == Gst.MessageType.STATE_CHANGED:
            old_state, new_state, pending_state = message.parse_state_changed()
            if message.src == self.pipeline:
                logger.info(f"Pipeline state changed: {old_state.value_name} -> {new_state.value_name}")
                
                # Track problematic state transitions
                if new_state == Gst.State.PAUSED and old_state == Gst.State.PLAYING:
                    self.health_monitor.add_error_event(
                        'pipeline_paused',
                        'Pipeline paused unexpectedly',
                        'PAUSED',
                        'monitor'
                    )
    
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
        self.health_monitor.stop_event.set()
        if self.health_monitor.monitor_thread and self.health_monitor.monitor_thread.is_alive():
            self.health_monitor.monitor_thread.join(timeout=5)
        
        self.stop_streaming()
    
    def get_status(self) -> Dict[str, Any]:
        """Get current streaming status with health information"""
        status = {
            'running': self.running,
            'pipeline_state': 'unknown',
            'mediamtx_running': False,
            'output_files': [],
            'restart_count': self.restart_count,
            'health': self.health_monitor.get_health_summary()
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
        'output_dir': '/tmp/hls',
        'max_restarts': 10,
        'restart_delay': 30,
        'max_errors': 5,
        'error_window': 300  # 5 minutes
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
        
        # Start health API first
        streamer.start_health_api()
        time.sleep(2)  # Give API time to start
        
        # Start streaming
        streamer.start_streaming()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    finally:
        streamer.cleanup()

if __name__ == "__main__":
    main() 