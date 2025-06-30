#!/usr/bin/env python3
"""
Desktop Streamer Watchdog
Monitors the desktop streamer service and provides alerts and automated recovery
"""

import os
import sys
import time
import json
import logging
import subprocess
import requests
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/desktop-streamer-watchdog.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class StreamerWatchdog:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.service_name = "desktop-streamer.service"
        self.health_url = "http://0.0.0.0:8888/api/health"
        self.status_url = "http://0.0.0.0:8888/api/status"
        self.alert_history: List[Dict[str, Any]] = []
        self.max_alerts = config.get('max_alerts', 10)
        self.alert_cooldown = config.get('alert_cooldown', 300)  # 5 minutes
        self.check_interval = config.get('check_interval', 30)  # 30 seconds
        
    def check_service_status(self) -> Dict[str, Any]:
        """Check if the systemd service is running"""
        try:
            result = subprocess.run(
                ["systemctl", "is-active", self.service_name],
                capture_output=True,
                text=True,
                timeout=5
            )
            is_active = result.stdout.strip() == "active"
            
            # Get service details
            status_result = subprocess.run(
                ["systemctl", "show", self.service_name, "--property=ActiveState,SubState,LoadState,UnitFileState,RestartCount"],
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
                "details": service_details,
                "timestamp": time.time()
            }
        except Exception as e:
            logger.error(f"Error checking service status: {e}")
            return {"active": False, "error": str(e), "timestamp": time.time()}
    
    def check_health_api(self) -> Optional[Dict[str, Any]]:
        """Check the health API endpoint"""
        try:
            response = requests.get(self.health_url, timeout=5)
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"Health API returned status {response.status_code}")
                return None
        except requests.exceptions.RequestException as e:
            logger.warning(f"Health API not accessible: {e}")
            return None
    
    def check_stream_activity(self) -> Dict[str, Any]:
        """Check if the stream is actively producing content"""
        try:
            hls_dir = Path("/tmp/hls")
            if not hls_dir.exists():
                return {"active": False, "reason": "HLS directory not found"}
            
            # Check for recent TS files
            ts_files = list(hls_dir.glob("*.ts"))
            if not ts_files:
                return {"active": False, "reason": "No TS segments found"}
            
            # Check if files are being updated
            latest_file = max(ts_files, key=lambda x: x.stat().st_mtime)
            latest_time = latest_file.stat().st_mtime
            time_since_update = time.time() - latest_time
            
            if time_since_update > 60:  # No updates in last minute
                return {
                    "active": False, 
                    "reason": f"Stream inactive for {time_since_update:.1f} seconds",
                    "last_update": latest_time
                }
            
            return {
                "active": True,
                "segments": len(ts_files),
                "latest_segment": latest_file.name,
                "last_update": latest_time
            }
            
        except Exception as e:
            logger.error(f"Error checking stream activity: {e}")
            return {"active": False, "reason": f"Error: {str(e)}"}
    
    def check_system_resources(self) -> Dict[str, Any]:
        """Check system resource usage"""
        try:
            import psutil
            
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/tmp')
            
            return {
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_available_gb": round(memory.available / (1024**3), 2),
                "disk_usage_percent": (disk.used / disk.total) * 100,
                "disk_free_gb": round(disk.free / (1024**3), 2)
            }
        except Exception as e:
            logger.error(f"Error checking system resources: {e}")
            return {"error": str(e)}
    
    def should_alert(self, alert_type: str, severity: str = "warning") -> bool:
        """Check if we should send an alert based on cooldown and history"""
        current_time = time.time()
        
        # Check cooldown
        recent_alerts = [
            alert for alert in self.alert_history 
            if current_time - alert['timestamp'] < self.alert_cooldown
        ]
        
        if len(recent_alerts) >= self.max_alerts:
            return False
        
        # Check if this specific alert type was recently sent
        recent_same_type = [
            alert for alert in recent_alerts 
            if alert['type'] == alert_type
        ]
        
        if recent_same_type:
            return False
        
        return True
    
    def send_alert(self, alert_type: str, message: str, severity: str = "warning", data: Dict[str, Any] = None):
        """Send an alert"""
        if not self.should_alert(alert_type, severity):
            return
        
        alert = {
            "type": alert_type,
            "message": message,
            "severity": severity,
            "timestamp": time.time(),
            "data": data or {}
        }
        
        self.alert_history.append(alert)
        
        # Keep only recent alerts
        cutoff_time = time.time() - (self.alert_cooldown * 2)
        self.alert_history = [
            alert for alert in self.alert_history 
            if alert['timestamp'] > cutoff_time
        ]
        
        logger.warning(f"ALERT [{severity.upper()}]: {message}")
        
        # Send email alert if configured
        if self.config.get('email_alerts', {}).get('enabled', False):
            self.send_email_alert(alert)
        
        # Send webhook if configured
        if self.config.get('webhook_alerts', {}).get('enabled', False):
            self.send_webhook_alert(alert)
    
    def send_email_alert(self, alert: Dict[str, Any]):
        """Send email alert"""
        try:
            email_config = self.config['email_alerts']
            
            msg = MIMEMultipart()
            msg['From'] = email_config['from_email']
            msg['To'] = email_config['to_email']
            msg['Subject'] = f"Desktop Streamer Alert: {alert['type']}"
            
            body = f"""
            Desktop Streamer Alert
            
            Type: {alert['type']}
            Severity: {alert['severity']}
            Time: {datetime.fromtimestamp(alert['timestamp'])}
            Message: {alert['message']}
            
            Data: {json.dumps(alert['data'], indent=2)}
            """
            
            msg.attach(MIMEText(body, 'plain'))
            
            with smtplib.SMTP(email_config['smtp_server'], email_config['smtp_port']) as server:
                if email_config.get('use_tls', True):
                    server.starttls()
                if email_config.get('username'):
                    server.login(email_config['username'], email_config['password'])
                server.send_message(msg)
            
            logger.info(f"Email alert sent for {alert['type']}")
            
        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")
    
    def send_webhook_alert(self, alert: Dict[str, Any]):
        """Send webhook alert"""
        try:
            webhook_config = self.config['webhook_alerts']
            
            payload = {
                "text": f"Desktop Streamer Alert: {alert['message']}",
                "attachments": [{
                    "title": f"Alert: {alert['type']}",
                    "text": alert['message'],
                    "color": "danger" if alert['severity'] == "critical" else "warning",
                    "fields": [
                        {"title": "Severity", "value": alert['severity'], "short": True},
                        {"title": "Time", "value": datetime.fromtimestamp(alert['timestamp']).isoformat(), "short": True}
                    ]
                }]
            }
            
            response = requests.post(
                webhook_config['url'],
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info(f"Webhook alert sent for {alert['type']}")
            else:
                logger.warning(f"Webhook alert failed with status {response.status_code}")
                
        except Exception as e:
            logger.error(f"Failed to send webhook alert: {e}")
    
    def perform_recovery_action(self, issue_type: str) -> bool:
        """Perform automated recovery actions"""
        try:
            if issue_type == "service_down":
                logger.info("Attempting to restart service...")
                result = subprocess.run(
                    ["systemctl", "restart", self.service_name],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if result.returncode == 0:
                    logger.info("Service restart successful")
                    return True
                else:
                    logger.error(f"Service restart failed: {result.stderr}")
                    return False
            
            elif issue_type == "stream_inactive":
                logger.info("Attempting to restart service due to inactive stream...")
                result = subprocess.run(
                    ["systemctl", "restart", self.service_name],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if result.returncode == 0:
                    logger.info("Service restart successful")
                    return True
                else:
                    logger.error(f"Service restart failed: {result.stderr}")
                    return False
            
            elif issue_type == "high_resource_usage":
                logger.info("High resource usage detected, monitoring...")
                # Just log for now, could implement more sophisticated recovery
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Recovery action failed: {e}")
            return False
    
    def run_monitoring_loop(self):
        """Main monitoring loop"""
        logger.info("Starting Desktop Streamer Watchdog...")
        
        while True:
            try:
                # Check service status
                service_status = self.check_service_status()
                
                if not service_status['active']:
                    self.send_alert(
                        "service_down",
                        f"Desktop streamer service is not active: {service_status.get('details', {}).get('ActiveState', 'unknown')}",
                        "critical",
                        service_status
                    )
                    
                    if self.config.get('auto_recovery', {}).get('service_restart', True):
                        self.perform_recovery_action("service_down")
                
                # Check health API if service is running
                if service_status['active']:
                    health_data = self.check_health_api()
                    
                    if health_data:
                        # Check for high error counts
                        error_count = health_data.get('total_errors', 0)
                        if error_count > 10:
                            self.send_alert(
                                "high_error_count",
                                f"High error count detected: {error_count} errors",
                                "warning",
                                health_data
                            )
                        
                        # Check for recent restarts
                        restart_count = health_data.get('restart_count', 0)
                        if restart_count > 5:
                            self.send_alert(
                                "frequent_restarts",
                                f"Service has restarted {restart_count} times",
                                "critical",
                                health_data
                            )
                    
                    # Check stream activity
                    stream_status = self.check_stream_activity()
                    if not stream_status['active']:
                        self.send_alert(
                            "stream_inactive",
                            f"Stream is not active: {stream_status.get('reason', 'unknown')}",
                            "warning",
                            stream_status
                        )
                        
                        if self.config.get('auto_recovery', {}).get('stream_restart', True):
                            self.perform_recovery_action("stream_inactive")
                
                # Check system resources
                system_resources = self.check_system_resources()
                if 'error' not in system_resources:
                    cpu_percent = system_resources.get('cpu_percent', 0)
                    memory_percent = system_resources.get('memory_percent', 0)
                    
                    if cpu_percent > 90:
                        self.send_alert(
                            "high_cpu_usage",
                            f"High CPU usage: {cpu_percent}%",
                            "warning",
                            system_resources
                        )
                    
                    if memory_percent > 90:
                        self.send_alert(
                            "high_memory_usage",
                            f"High memory usage: {memory_percent}%",
                            "warning",
                            system_resources
                        )
                        
                        if self.config.get('auto_recovery', {}).get('resource_monitoring', True):
                            self.perform_recovery_action("high_resource_usage")
                
                # Log status periodically
                logger.info(f"Monitoring check completed - Service: {service_status['active']}, "
                          f"Stream: {stream_status.get('active', False) if 'stream_status' in locals() else 'unknown'}")
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                self.send_alert(
                    "monitoring_error",
                    f"Watchdog monitoring error: {str(e)}",
                    "critical"
                )
            
            time.sleep(self.check_interval)

def main():
    """Main function"""
    # Default configuration
    config = {
        'check_interval': 30,  # seconds
        'max_alerts': 10,
        'alert_cooldown': 300,  # 5 minutes
        'auto_recovery': {
            'service_restart': True,
            'stream_restart': True,
            'resource_monitoring': True
        },
        'email_alerts': {
            'enabled': False,
            'smtp_server': 'localhost',
            'smtp_port': 587,
            'use_tls': True,
            'from_email': 'watchdog@example.com',
            'to_email': 'admin@example.com',
            'username': '',
            'password': ''
        },
        'webhook_alerts': {
            'enabled': False,
            'url': 'https://hooks.slack.com/services/YOUR/WEBHOOK/URL'
        }
    }
    
    # Load config from file if it exists
    config_file = Path('/etc/desktop-streamer/watchdog-config.json')
    if config_file.exists():
        try:
            with open(config_file, 'r') as f:
                file_config = json.load(f)
                config.update(file_config)
        except Exception as e:
            logger.warning(f"Failed to load watchdog config file: {e}")
    
    # Create and run watchdog
    watchdog = StreamerWatchdog(config)
    
    try:
        watchdog.run_monitoring_loop()
    except KeyboardInterrupt:
        logger.info("Watchdog stopped by user")
    except Exception as e:
        logger.error(f"Watchdog error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 