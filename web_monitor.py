#!/usr/bin/env python3
"""
Web Monitor for Desktop Streamer
Simple web interface to monitor and view the desktop stream
"""

import os
import json
import time
import subprocess
from pathlib import Path
from typing import Dict, Any
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Desktop Streamer Monitor", version="1.0.0")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")

class StreamMonitor:
    def __init__(self):
        self.config_path = Path("/etc/desktop-streamer/config.json")
        self.hls_dir = Path("/tmp/hls")
        self.stream_url = "http://0.0.0.0:8888/hls/desktop/playlist.m3u8"
    
    def get_service_status(self) -> Dict[str, Any]:
        """Get the status of the desktop-streamer service"""
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "desktop-streamer.service"],
                capture_output=True,
                text=True,
                timeout=5
            )
            is_active = result.stdout.strip() == "active"
            
            # Get service logs
            log_result = subprocess.run(
                ["journalctl", "-u", "desktop-streamer.service", "--no-pager", "-n", "20"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            return {
                "active": is_active,
                "logs": log_result.stdout.split('\n')[-10:] if log_result.stdout else []
            }
        except Exception as e:
            logger.error(f"Error getting service status: {e}")
            return {"active": False, "logs": [f"Error: {e}"]}
    
    def get_stream_info(self) -> Dict[str, Any]:
        """Get information about the HLS stream"""
        try:
            # Check if playlist exists
            playlist_exists = (self.hls_dir / "playlist.m3u8").exists()
            
            # Count TS segments
            ts_files = list(self.hls_dir.glob("*.ts"))
            
            # Get file sizes
            total_size = sum(f.stat().st_size for f in ts_files) if ts_files else 0
            
            return {
                "playlist_exists": playlist_exists,
                "segment_count": len(ts_files),
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "stream_url": self.stream_url
            }
        except Exception as e:
            logger.error(f"Error getting stream info: {e}")
            return {
                "playlist_exists": False,
                "segment_count": 0,
                "total_size_mb": 0,
                "stream_url": self.stream_url,
                "error": str(e)
            }
    
    def get_config(self) -> Dict[str, Any]:
        """Get the current configuration"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r') as f:
                    return json.load(f)
            else:
                return {"error": "Configuration file not found"}
        except Exception as e:
            logger.error(f"Error reading config: {e}")
            return {"error": str(e)}

monitor = StreamMonitor()

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main dashboard page"""
    service_status = monitor.get_service_status()
    stream_info = monitor.get_stream_info()
    config = monitor.get_config()
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "service_status": service_status,
        "stream_info": stream_info,
        "config": config
    })

@app.get("/api/status")
async def get_status():
    """API endpoint to get current status"""
    return {
        "service": monitor.get_service_status(),
        "stream": monitor.get_stream_info(),
        "config": monitor.get_config(),
        "timestamp": time.time()
    }

@app.get("/api/service/start")
async def start_service():
    """Start the desktop-streamer service"""
    try:
        result = subprocess.run(
            ["systemctl", "start", "desktop-streamer.service"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return {"success": True, "message": "Service started successfully"}
        else:
            return {"success": False, "message": result.stderr}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/service/stop")
async def stop_service():
    """Stop the desktop-streamer service"""
    try:
        result = subprocess.run(
            ["systemctl", "stop", "desktop-streamer.service"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return {"success": True, "message": "Service stopped successfully"}
        else:
            return {"success": False, "message": result.stderr}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/service/restart")
async def restart_service():
    """Restart the desktop-streamer service"""
    try:
        result = subprocess.run(
            ["systemctl", "restart", "desktop-streamer.service"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return {"success": True, "message": "Service restarted successfully"}
        else:
            return {"success": False, "message": result.stderr}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    # Create templates directory if it doesn't exist
    templates_dir = Path("templates")
    templates_dir.mkdir(exist_ok=True)
    
    # Create static directory if it doesn't exist
    static_dir = Path("static")
    static_dir.mkdir(exist_ok=True)
    
    # Create the HTML template
    html_template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Desktop Streamer Monitor</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .header {
            text-align: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 2px solid #eee;
        }
        .status-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .status-card {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid #007bff;
        }
        .status-card h3 {
            margin-top: 0;
            color: #333;
        }
        .status-indicator {
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 8px;
        }
        .status-active {
            background-color: #28a745;
        }
        .status-inactive {
            background-color: #dc3545;
        }
        .button-group {
            display: flex;
            gap: 10px;
            margin-top: 15px;
        }
        .btn {
            padding: 8px 16px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            text-decoration: none;
            display: inline-block;
            font-size: 14px;
        }
        .btn-primary {
            background-color: #007bff;
            color: white;
        }
        .btn-success {
            background-color: #28a745;
            color: white;
        }
        .btn-danger {
            background-color: #dc3545;
            color: white;
        }
        .btn-warning {
            background-color: #ffc107;
            color: #212529;
        }
        .video-container {
            margin-top: 20px;
            text-align: center;
        }
        .video-player {
            max-width: 100%;
            height: auto;
            border-radius: 8px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        }
        .logs {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 4px;
            font-family: monospace;
            font-size: 12px;
            max-height: 200px;
            overflow-y: auto;
            white-space: pre-wrap;
        }
        .refresh-btn {
            position: fixed;
            top: 20px;
            right: 20px;
            background: #007bff;
            color: white;
            border: none;
            padding: 10px 15px;
            border-radius: 4px;
            cursor: pointer;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Desktop Streamer Monitor</h1>
            <p>Real-time monitoring and control for desktop streaming service</p>
        </div>
        
        <button class="refresh-btn" onclick="location.reload()">🔄 Refresh</button>
        
        <div class="status-grid">
            <div class="status-card">
                <h3>Service Status</h3>
                <p>
                    <span class="status-indicator {% if service_status.active %}status-active{% else %}status-inactive{% endif %}"></span>
                    {% if service_status.active %}Active{% else %}Inactive{% endif %}
                </p>
                <div class="button-group">
                    <a href="/api/service/start" class="btn btn-success">Start</a>
                    <a href="/api/service/stop" class="btn btn-danger">Stop</a>
                    <a href="/api/service/restart" class="btn btn-warning">Restart</a>
                </div>
            </div>
            
            <div class="status-card">
                <h3>Stream Information</h3>
                <p><strong>Playlist:</strong> {% if stream_info.playlist_exists %}Available{% else %}Not Found{% endif %}</p>
                <p><strong>Segments:</strong> {{ stream_info.segment_count }}</p>
                <p><strong>Total Size:</strong> {{ stream_info.total_size_mb }} MB</p>
                <p><strong>Stream URL:</strong> <a href="{{ stream_info.stream_url }}" target="_blank">{{ stream_info.stream_url }}</a></p>
            </div>
            
            <div class="status-card">
                <h3>Configuration</h3>
                {% if config.error %}
                    <p style="color: red;">{{ config.error }}</p>
                {% else %}
                    <p><strong>FPS:</strong> {{ config.fps }}</p>
                    <p><strong>Resolution:</strong> {{ config.width }}x{{ config.height }}</p>
                    <p><strong>Bitrate:</strong> {{ config.bitrate }} kbps</p>
                    <p><strong>Segment Duration:</strong> {{ config.segment_duration }}s</p>
                {% endif %}
            </div>
        </div>
        
        {% if service_status.logs %}
        <div class="status-card">
            <h3>Recent Logs</h3>
            <div class="logs">
                {% for log in service_status.logs %}
                    {{ log }}
                {% endfor %}
            </div>
        </div>
        {% endif %}
        
        {% if stream_info.playlist_exists %}
        <div class="video-container">
            <h3>Live Stream</h3>
            <video class="video-player" controls autoplay muted>
                <source src="{{ stream_info.stream_url }}" type="application/x-mpegURL">
                Your browser does not support HLS video playback.
            </video>
        </div>
        {% endif %}
    </div>
    
    <script>
        // Auto-refresh every 30 seconds
        setTimeout(function() {
            location.reload();
        }, 30000);
    </script>
</body>
</html>"""
    
    with open(templates_dir / "index.html", "w") as f:
        f.write(html_template)
    
    logger.info("Starting web monitor on http://0.0.0.0:8080")
    uvicorn.run(app, host="0.0.0.0", port=8080) 