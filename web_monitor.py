#!/usr/bin/env python3
"""
Web Monitor for Desktop Streamer
Enhanced web interface to monitor and control the desktop stream with self-healing capabilities
"""

import os
import json
import time
import subprocess
import requests
import psutil
from pathlib import Path
from typing import Dict, Any, List, Optional
import logging
from datetime import datetime, timedelta
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global WebSocket connections for real-time updates
websocket_connections: List[WebSocket] = []

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Desktop Streamer Monitor...")
    yield
    # Shutdown
    logger.info("Shutting down Desktop Streamer Monitor...")

app = FastAPI(
    title="Desktop Streamer Monitor", 
    version="2.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")

class StreamMonitor:
    def __init__(self):
        self.config_path = Path("/etc/desktop-streamer/config.json")
        self.hls_dir = Path("/tmp/hls")
        self.stream_url = "http://0.0.0.0:8888/hls/desktop/playlist.m3u8"
        self.service_name = "desktop-streamer.service"
        self.last_status_check = 0
        self.status_cache = {}
        self.cache_duration = 5  # seconds
    
    def get_service_status(self) -> Dict[str, Any]:
        """Get the status of the desktop-streamer service"""
        try:
            result = subprocess.run(
                ["systemctl", "is-active", self.service_name],
                capture_output=True,
                text=True,
                timeout=5
            )
            is_active = result.stdout.strip() == "active"
            
            # Get service logs
            log_result = subprocess.run(
                ["journalctl", "-u", self.service_name, "--no-pager", "-n", "20"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            # Get service details
            status_result = subprocess.run(
                ["systemctl", "show", self.service_name, "--property=ActiveState,SubState,LoadState,UnitFileState"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            service_details = {}
            if status_result.stdout:
                for line in status_result.stdout.strip().split('\n'):
                    if '=' in line:
                        key, value = line.split('=', 1)
                        service_details[key] = value
            
            return {
                "active": is_active,
                "logs": log_result.stdout.split('\n')[-10:] if log_result.stdout else [],
                "details": service_details
            }
        except Exception as e:
            logger.error(f"Error getting service status: {e}")
            return {"active": False, "logs": [f"Error: {e}"], "details": {}}
    
    def get_stream_info(self) -> Dict[str, Any]:
        """Get information about the HLS stream"""
        try:
            # Check if playlist exists
            playlist_exists = (self.hls_dir / "playlist.m3u8").exists()
            
            # Count TS segments
            ts_files = list(self.hls_dir.glob("*.ts"))
            
            # Get file sizes and timestamps
            total_size = 0
            file_info = []
            for f in ts_files:
                stat = f.stat()
                total_size += stat.st_size
                file_info.append({
                    'name': f.name,
                    'size': stat.st_size,
                    'modified': stat.st_mtime
                })
            
            # Sort by modification time
            file_info.sort(key=lambda x: x['modified'], reverse=True)
            
            # Check if stream is actively updating
            stream_active = False
            if file_info:
                latest_file_time = file_info[0]['modified']
                stream_active = (time.time() - latest_file_time) < 30  # Active if file updated in last 30s
            
            return {
                "playlist_exists": playlist_exists,
                "segment_count": len(ts_files),
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "stream_url": self.stream_url,
                "stream_active": stream_active,
                "latest_segment": file_info[0]['name'] if file_info else None,
                "latest_update": file_info[0]['modified'] if file_info else None
            }
        except Exception as e:
            logger.error(f"Error getting stream info: {e}")
            return {
                "playlist_exists": False,
                "segment_count": 0,
                "total_size_mb": 0,
                "stream_url": self.stream_url,
                "stream_active": False,
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
    
    def get_health_metrics(self) -> Dict[str, Any]:
        """Get health metrics from the streamer service"""
        try:
            # Try to get health metrics from the streamer's internal API
            response = requests.get("http://0.0.0.0:8888/api/health", timeout=5)
            if response.status_code == 200:
                return response.json()
        except:
            pass
        
        # Fallback: analyze logs for health information
        try:
            log_result = subprocess.run(
                ["journalctl", "-u", self.service_name, "--no-pager", "-n", "50"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            logs = log_result.stdout.split('\n') if log_result.stdout else []
            
            # Analyze logs for health patterns
            error_count = sum(1 for log in logs if 'ERROR' in log or 'error' in log.lower())
            warning_count = sum(1 for log in logs if 'WARNING' in log or 'warning' in log.lower())
            restart_count = sum(1 for log in logs if 'restart' in log.lower())
            
            return {
                "error_count": error_count,
                "warning_count": warning_count,
                "restart_count": restart_count,
                "last_error": next((log for log in reversed(logs) if 'ERROR' in log), None),
                "health_status": "unknown"
            }
        except Exception as e:
            logger.error(f"Error getting health metrics: {e}")
            return {"error": str(e)}
    
    def get_comprehensive_status(self) -> Dict[str, Any]:
        """Get comprehensive status information"""
        current_time = time.time()
        
        # Use cached status if recent
        if (current_time - self.last_status_check) < self.cache_duration and self.status_cache:
            return self.status_cache
        
        status = {
            "service": self.get_service_status(),
            "stream": self.get_stream_info(),
            "config": self.get_config(),
            "health": self.get_health_metrics(),
            "timestamp": current_time,
            "system": self.get_system_info()
        }
        
        self.status_cache = status
        self.last_status_check = current_time
        
        return status
    
    def get_system_info(self) -> Dict[str, Any]:
        """Get system information"""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            
            # Disk usage for HLS directory
            disk_usage = psutil.disk_usage(self.hls_dir)
            
            # Network interfaces
            network = psutil.net_io_counters()
            
            return {
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_available_gb": round(memory.available / (1024**3), 2),
                "disk_usage_percent": (disk_usage.used / disk_usage.total) * 100,
                "disk_free_gb": round(disk_usage.free / (1024**3), 2),
                "network_bytes_sent": network.bytes_sent,
                "network_bytes_recv": network.bytes_recv
            }
        except Exception as e:
            logger.error(f"Error getting system info: {e}")
            return {"error": str(e)}

monitor = StreamMonitor()

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main dashboard page"""
    status = monitor.get_comprehensive_status()
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "status": status
    })

@app.get("/api/status")
async def get_status():
    """API endpoint to get current status"""
    return monitor.get_comprehensive_status()

@app.get("/api/health")
async def get_health():
    """API endpoint to get health metrics"""
    return monitor.get_health_metrics()

@app.get("/api/service/start")
async def start_service():
    """Start the desktop-streamer service"""
    try:
        result = subprocess.run(
            ["systemctl", "start", monitor.service_name],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            # Clear cache to get fresh status
            monitor.last_status_check = 0
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
            ["systemctl", "stop", monitor.service_name],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            # Clear cache to get fresh status
            monitor.last_status_check = 0
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
            ["systemctl", "restart", monitor.service_name],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            # Clear cache to get fresh status
            monitor.last_status_check = 0
            return {"success": True, "message": "Service restarted successfully"}
        else:
            return {"success": False, "message": result.stderr}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/service/enable")
async def enable_service():
    """Enable the desktop-streamer service to start on boot"""
    try:
        result = subprocess.run(
            ["systemctl", "enable", monitor.service_name],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return {"success": True, "message": "Service enabled successfully"}
        else:
            return {"success": False, "message": result.stderr}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/service/disable")
async def disable_service():
    """Disable the desktop-streamer service from starting on boot"""
    try:
        result = subprocess.run(
            ["systemctl", "disable", monitor.service_name],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return {"success": True, "message": "Service disabled successfully"}
        else:
            return {"success": False, "message": result.stderr}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/logs")
async def get_logs(lines: int = 50):
    """Get recent service logs"""
    try:
        result = subprocess.run(
            ["journalctl", "-u", monitor.service_name, "--no-pager", "-n", str(lines)],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return {"logs": result.stdout.split('\n')}
        else:
            return {"logs": [], "error": result.stderr}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/logs/follow")
async def follow_logs():
    """Stream live logs"""
    async def log_generator():
        try:
            process = await asyncio.create_subprocess_exec(
                "journalctl", "-u", monitor.service_name, "-f",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                yield f"data: {line.decode().strip()}\n\n"
                
        except Exception as e:
            yield f"data: Error: {str(e)}\n\n"
    
    return StreamingResponse(log_generator(), media_type="text/plain")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates"""
    await websocket.accept()
    websocket_connections.append(websocket)
    
    try:
        while True:
            # Send status updates every 5 seconds
            status = monitor.get_comprehensive_status()
            await websocket.send_text(json.dumps(status))
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        websocket_connections.remove(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if websocket in websocket_connections:
            websocket_connections.remove(websocket)

@app.get("/api/stream/cleanup")
async def cleanup_stream():
    """Clean up old HLS segments"""
    try:
        # Remove old TS files (keep last 10)
        ts_files = list(monitor.hls_dir.glob("*.ts"))
        ts_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        removed_count = 0
        for ts_file in ts_files[10:]:  # Keep only the 10 most recent
            ts_file.unlink()
            removed_count += 1
        
        return {
            "success": True, 
            "message": f"Cleaned up {removed_count} old segments",
            "remaining_segments": len(ts_files) - removed_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/system/restart")
async def restart_system():
    """Restart the entire system (requires confirmation)"""
    # This is a dangerous operation, should require confirmation
    return {
        "warning": "System restart is a dangerous operation",
        "message": "Use POST /api/system/restart with confirmation=true to actually restart"
    }

@app.post("/api/system/restart")
async def restart_system_confirmed(confirmation: bool = False):
    """Restart the system with confirmation"""
    if not confirmation:
        raise HTTPException(status_code=400, detail="Confirmation required")
    
    try:
        # Schedule restart in 1 minute
        subprocess.run(["shutdown", "-r", "+1"], check=True)
        return {"success": True, "message": "System will restart in 1 minute"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    # Create templates directory if it doesn't exist
    templates_dir = Path("templates")
    templates_dir.mkdir(exist_ok=True)
    
    # Create static directory if it doesn't exist
    static_dir = Path("static")
    static_dir.mkdir(exist_ok=True)
    
    # Create the enhanced HTML template
    html_template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Desktop Streamer Monitor - Enhanced</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: #333;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }
        
        .header {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
        }
        
        .header h1 {
            color: #2c3e50;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .status-indicator {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            display: inline-block;
            margin-right: 10px;
        }
        
        .status-active { background-color: #27ae60; }
        .status-inactive { background-color: #e74c3c; }
        .status-warning { background-color: #f39c12; }
        
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        
        .card {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 20px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }
        
        .card:hover {
            transform: translateY(-5px);
            box-shadow: 0 12px 40px rgba(0, 0, 0, 0.15);
        }
        
        .card h3 {
            color: #2c3e50;
            margin-bottom: 15px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .metric {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px 0;
            border-bottom: 1px solid #ecf0f1;
        }
        
        .metric:last-child {
            border-bottom: none;
        }
        
        .metric-label {
            font-weight: 500;
            color: #7f8c8d;
        }
        
        .metric-value {
            font-weight: 600;
            color: #2c3e50;
        }
        
        .controls {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            margin-top: 15px;
        }
        
        .btn {
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.3s ease;
            text-decoration: none;
            display: inline-block;
            text-align: center;
        }
        
        .btn-primary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        
        .btn-success {
            background: linear-gradient(135deg, #27ae60 0%, #2ecc71 100%);
            color: white;
        }
        
        .btn-danger {
            background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%);
            color: white;
        }
        
        .btn-warning {
            background: linear-gradient(135deg, #f39c12 0%, #e67e22 100%);
            color: white;
        }
        
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.2);
        }
        
        .logs {
            background: #2c3e50;
            color: #ecf0f1;
            padding: 15px;
            border-radius: 8px;
            font-family: 'Courier New', monospace;
            font-size: 12px;
            max-height: 300px;
            overflow-y: auto;
            white-space: pre-wrap;
        }
        
        .health-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-top: 15px;
        }
        
        .health-item {
            text-align: center;
            padding: 15px;
            border-radius: 10px;
            background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
        }
        
        .health-value {
            font-size: 24px;
            font-weight: bold;
            margin-bottom: 5px;
        }
        
        .health-label {
            font-size: 12px;
            color: #6c757d;
            text-transform: uppercase;
        }
        
        .stream-player {
            width: 100%;
            height: 300px;
            border-radius: 10px;
            overflow: hidden;
            background: #000;
        }
        
        .refresh-btn {
            position: fixed;
            bottom: 20px;
            right: 20px;
            width: 60px;
            height: 60px;
            border-radius: 50%;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            cursor: pointer;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.2);
            transition: all 0.3s ease;
        }
        
        .refresh-btn:hover {
            transform: rotate(180deg);
        }
        
        @media (max-width: 768px) {
            .grid {
                grid-template-columns: 1fr;
            }
            
            .controls {
                flex-direction: column;
            }
            
            .btn {
                width: 100%;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>
                <span class="status-indicator" id="overall-status"></span>
                Desktop Streamer Monitor
                <small style="font-size: 14px; color: #7f8c8d;">Enhanced v2.0</small>
            </h1>
            <p>Real-time monitoring and control for the desktop streaming service</p>
        </div>
        
        <div class="grid">
            <!-- Service Status -->
            <div class="card">
                <h3>🔄 Service Status</h3>
                <div id="service-status">
                    <div class="metric">
                        <span class="metric-label">Status:</span>
                        <span class="metric-value" id="service-active">Loading...</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">State:</span>
                        <span class="metric-value" id="service-state">Loading...</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Auto-start:</span>
                        <span class="metric-value" id="service-enabled">Loading...</span>
                    </div>
                </div>
                <div class="controls">
                    <button class="btn btn-success" onclick="startService()">Start</button>
                    <button class="btn btn-danger" onclick="stopService()">Stop</button>
                    <button class="btn btn-warning" onclick="restartService()">Restart</button>
                </div>
            </div>
            
            <!-- Stream Health -->
            <div class="card">
                <h3>💓 Stream Health</h3>
                <div id="stream-health">
                    <div class="metric">
                        <span class="metric-label">Stream Active:</span>
                        <span class="metric-value" id="stream-active">Loading...</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Segments:</span>
                        <span class="metric-value" id="segment-count">Loading...</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Total Size:</span>
                        <span class="metric-value" id="total-size">Loading...</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Latest Update:</span>
                        <span class="metric-value" id="latest-update">Loading...</span>
                    </div>
                </div>
                <div class="health-grid" id="health-metrics">
                    <!-- Health metrics will be populated here -->
                </div>
            </div>
            
            <!-- System Resources -->
            <div class="card">
                <h3>💻 System Resources</h3>
                <div id="system-resources">
                    <div class="metric">
                        <span class="metric-label">CPU Usage:</span>
                        <span class="metric-value" id="cpu-usage">Loading...</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Memory Usage:</span>
                        <span class="metric-value" id="memory-usage">Loading...</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Disk Usage:</span>
                        <span class="metric-value" id="disk-usage">Loading...</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Network Sent:</span>
                        <span class="metric-value" id="network-sent">Loading...</span>
                    </div>
                </div>
            </div>
            
            <!-- Stream Player -->
            <div class="card">
                <h3>📺 Stream Player</h3>
                <div class="stream-player">
                    <video id="stream-video" width="100%" height="100%" controls>
                        <source src="/hls/desktop/playlist.m3u8" type="application/x-mpegURL">
                        Your browser does not support HLS video.
                    </video>
                </div>
                <div class="controls">
                    <button class="btn btn-primary" onclick="refreshStream()">Refresh Stream</button>
                    <button class="btn btn-warning" onclick="cleanupStream()">Cleanup Segments</button>
                </div>
            </div>
        </div>
        
        <!-- Logs Section -->
        <div class="card">
            <h3>📋 Recent Logs</h3>
            <div class="controls">
                <button class="btn btn-primary" onclick="refreshLogs()">Refresh Logs</button>
                <button class="btn btn-warning" onclick="followLogs()">Follow Logs</button>
            </div>
            <div class="logs" id="logs-content">
                Loading logs...
            </div>
        </div>
    </div>
    
    <button class="refresh-btn" onclick="refreshAll()" title="Refresh All">🔄</button>
    
    <script>
        let ws = null;
        let logsFollowing = false;
        
        // Initialize WebSocket connection
        function initWebSocket() {
            ws = new WebSocket(`ws://${window.location.host}/ws`);
            ws.onmessage = function(event) {
                const data = JSON.parse(event.data);
                updateDashboard(data);
            };
            ws.onclose = function() {
                console.log('WebSocket closed, attempting to reconnect...');
                setTimeout(initWebSocket, 5000);
            };
        }
        
        // Update dashboard with new data
        function updateDashboard(data) {
            // Service status
            const serviceActive = data.service?.active || false;
            document.getElementById('service-active').textContent = serviceActive ? 'Active' : 'Inactive';
            document.getElementById('service-active').className = 'metric-value ' + (serviceActive ? 'status-active' : 'status-inactive');
            
            document.getElementById('service-state').textContent = data.service?.details?.ActiveState || 'Unknown';
            document.getElementById('service-enabled').textContent = data.service?.details?.UnitFileState === 'enabled' ? 'Enabled' : 'Disabled';
            
            // Overall status indicator
            const overallStatus = document.getElementById('overall-status');
            if (serviceActive && data.stream?.stream_active) {
                overallStatus.className = 'status-indicator status-active';
            } else if (serviceActive) {
                overallStatus.className = 'status-indicator status-warning';
            } else {
                overallStatus.className = 'status-indicator status-inactive';
            }
            
            // Stream health
            document.getElementById('stream-active').textContent = data.stream?.stream_active ? 'Yes' : 'No';
            document.getElementById('segment-count').textContent = data.stream?.segment_count || 0;
            document.getElementById('total-size').textContent = data.stream?.total_size_mb + ' MB' || '0 MB';
            
            const latestUpdate = data.stream?.latest_update;
            if (latestUpdate) {
                const date = new Date(latestUpdate * 1000);
                document.getElementById('latest-update').textContent = date.toLocaleTimeString();
            } else {
                document.getElementById('latest-update').textContent = 'Never';
            }
            
            // Health metrics
            updateHealthMetrics(data.health);
            
            // System resources
            if (data.system) {
                document.getElementById('cpu-usage').textContent = data.system.cpu_percent + '%';
                document.getElementById('memory-usage').textContent = data.system.memory_percent + '%';
                document.getElementById('disk-usage').textContent = data.system.disk_usage_percent.toFixed(1) + '%';
                document.getElementById('network-sent').textContent = formatBytes(data.system.network_bytes_sent);
            }
        }
        
        function updateHealthMetrics(health) {
            const container = document.getElementById('health-metrics');
            container.innerHTML = '';
            
            if (health) {
                const metrics = [
                    { label: 'Errors', value: health.error_count || 0, color: '#e74c3c' },
                    { label: 'Warnings', value: health.warning_count || 0, color: '#f39c12' },
                    { label: 'Restarts', value: health.restart_count || 0, color: '#9b59b6' },
                    { label: 'Uptime', value: Math.round(health.uptime_minutes || 0) + 'm', color: '#27ae60' }
                ];
                
                metrics.forEach(metric => {
                    const div = document.createElement('div');
                    div.className = 'health-item';
                    div.innerHTML = `
                        <div class="health-value" style="color: ${metric.color}">${metric.value}</div>
                        <div class="health-label">${metric.label}</div>
                    `;
                    container.appendChild(div);
                });
            }
        }
        
        function formatBytes(bytes) {
            if (bytes === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        }
        
        // Service control functions
        async function startService() {
            try {
                const response = await fetch('/api/service/start');
                const result = await response.json();
                if (result.success) {
                    alert('Service started successfully');
                    refreshAll();
                } else {
                    alert('Failed to start service: ' + result.message);
                }
            } catch (error) {
                alert('Error starting service: ' + error);
            }
        }
        
        async function stopService() {
            if (confirm('Are you sure you want to stop the service?')) {
                try {
                    const response = await fetch('/api/service/stop');
                    const result = await response.json();
                    if (result.success) {
                        alert('Service stopped successfully');
                        refreshAll();
                    } else {
                        alert('Failed to stop service: ' + result.message);
                    }
                } catch (error) {
                    alert('Error stopping service: ' + error);
                }
            }
        }
        
        async function restartService() {
            if (confirm('Are you sure you want to restart the service?')) {
                try {
                    const response = await fetch('/api/service/restart');
                    const result = await response.json();
                    if (result.success) {
                        alert('Service restarted successfully');
                        refreshAll();
                    } else {
                        alert('Failed to restart service: ' + result.message);
                    }
                } catch (error) {
                    alert('Error restarting service: ' + error);
                }
            }
        }
        
        async function refreshStream() {
            const video = document.getElementById('stream-video');
            video.src = video.src;
            video.load();
        }
        
        async function cleanupStream() {
            try {
                const response = await fetch('/api/stream/cleanup');
                const result = await response.json();
                if (result.success) {
                    alert('Stream cleanup completed: ' + result.message);
                    refreshAll();
                } else {
                    alert('Failed to cleanup stream: ' + result.message);
                }
            } catch (error) {
                alert('Error cleaning up stream: ' + error);
            }
        }
        
        async function refreshLogs() {
            try {
                const response = await fetch('/api/logs');
                const result = await response.json();
                document.getElementById('logs-content').textContent = result.logs.join('\\n');
            } catch (error) {
                document.getElementById('logs-content').textContent = 'Error loading logs: ' + error;
            }
        }
        
        async function followLogs() {
            if (logsFollowing) {
                logsFollowing = false;
                return;
            }
            
            logsFollowing = true;
            try {
                const response = await fetch('/api/logs/follow');
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                
                while (logsFollowing) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    
                    const text = decoder.decode(value);
                    const lines = text.split('\\n');
                    
                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            const logLine = line.substring(6);
                            const logsContent = document.getElementById('logs-content');
                            logsContent.textContent += logLine + '\\n';
                            logsContent.scrollTop = logsContent.scrollHeight;
                        }
                    }
                }
            } catch (error) {
                console.error('Error following logs:', error);
                logsFollowing = false;
            }
        }
        
        async function refreshAll() {
            try {
                const response = await fetch('/api/status');
                const data = await response.json();
                updateDashboard(data);
                refreshLogs();
            } catch (error) {
                console.error('Error refreshing data:', error);
            }
        }
        
        // Initialize on page load
        document.addEventListener('DOMContentLoaded', function() {
            initWebSocket();
            refreshAll();
            
            // Auto-refresh every 30 seconds
            setInterval(refreshAll, 30000);
        });
    </script>
</body>
</html>"""
    
    # Write the template
    with open(templates_dir / "index.html", "w") as f:
        f.write(html_template)
    
    # Create a simple CSS file for additional styling
    css_content = """
/* Additional styles for enhanced UI */
.loading {
    opacity: 0.6;
    pointer-events: none;
}

.error {
    color: #e74c3c;
    font-weight: bold;
}

.success {
    color: #27ae60;
    font-weight: bold;
}

.warning {
    color: #f39c12;
    font-weight: bold;
}

.pulse {
    animation: pulse 2s infinite;
}

@keyframes pulse {
    0% { opacity: 1; }
    50% { opacity: 0.5; }
    100% { opacity: 1; }
}
"""
    
    with open(static_dir / "style.css", "w") as f:
        f.write(css_content)
    
    logger.info("Enhanced web monitor started")
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info") 