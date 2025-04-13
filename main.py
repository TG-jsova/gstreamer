import os
import subprocess
from typing import Optional
from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import asyncio
import signal
import json
import socket
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Store active streams
active_streams = {}
UPLOAD_DIR = "/app/uploads"
MULTICAST_IP = "239.255.1.1"  # Default multicast IP
MULTICAST_PORT = 5004  # Default multicast port

class StreamRequest(BaseModel):
    multicast_ip: Optional[str] = MULTICAST_IP
    multicast_port: Optional[int] = MULTICAST_PORT

@app.on_event("startup")
async def startup_event():
    logger.info(f"Multicast streaming service started. Will send streams to {MULTICAST_IP}:{MULTICAST_PORT}")

@app.post("/upload/{bay_id}")
async def upload_file(bay_id: str, file: UploadFile):
    if not file.filename.endswith('.mp3'):
        raise HTTPException(status_code=400, detail="Only MP3 files are allowed")
    
    # Create bay-specific directory
    bay_dir = os.path.join(UPLOAD_DIR, bay_id)
    os.makedirs(bay_dir, exist_ok=True)
    
    # Rename the file to match the bayID
    new_filename = f"{bay_id}.mp3"
    file_path = os.path.join(bay_dir, new_filename)
    
    # Save the file
    try:
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        logger.info(f"File uploaded and renamed to {new_filename} for bay {bay_id}")
        return JSONResponse(content={"message": f"File uploaded successfully for bay {bay_id}"})
    except Exception as e:
        logger.error(f"Error uploading file: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/play/{bay_id}")
async def play_stream(bay_id: str, request: StreamRequest = None):
    if request is None:
        request = StreamRequest()
    
    multicast_ip = request.multicast_ip
    multicast_port = request.multicast_port
    
    # Check if there's already an active stream
    if active_streams:
        return JSONResponse(
            status_code=400,
            content={"message": "Another stream is currently active. Please stop it first."}
        )
    
    # Find the MP3 file for the given bay_id
    bay_dir = os.path.join(UPLOAD_DIR, bay_id)
    if not os.path.exists(bay_dir):
        raise HTTPException(status_code=404, detail=f"No files found for bay {bay_id}")
    
    # Use the bayID as the filename
    file_path = os.path.join(bay_dir, f"{bay_id}.mp3")
    
    # Check if the file exists
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"No MP3 file found for bay {bay_id}")
    
    logger.info(f"Found MP3 file: {file_path}")
    
    try:
        # Create GStreamer pipeline for streaming using MPEG-TS format
        # This format is directly playable by VLC
        cmd = [
            "gst-launch-1.0", "-v",
            "filesrc", f"location={file_path}",
            "!", "decodebin",
            "!", "audioconvert",
            "!", "audioresample",
            "!", "audio/x-raw,format=S16LE,rate=44100,channels=2",
            "!", "lamemp3enc", "bitrate=192",
            "!", "mpegtsmux",
            "!", "udpsink", f"host={multicast_ip}", f"port={multicast_port}"
        ]
        
        # Run the pipeline with output capture
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        
        # Store the process
        active_streams[bay_id] = process
        
        # Start a background task to monitor the process output
        asyncio.create_task(monitor_process_output(process, bay_id))
        
        return JSONResponse(content={
            "message": f"Started streaming for bay {bay_id} to {multicast_ip}:{multicast_port}",
            "vlc_url": f"udp://@{multicast_ip}:{multicast_port}"
        })
    except Exception as e:
        logger.error(f"Error starting GStreamer pipeline: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

async def monitor_process_output(process, bay_id):
    """Monitor the output of the GStreamer process and log it."""
    try:
        while True:
            # Read stdout
            stdout_line = process.stdout.readline()
            if stdout_line:
                logger.info(f"GStreamer [{bay_id}] stdout: {stdout_line.strip()}")
            
            # Read stderr
            stderr_line = process.stderr.readline()
            if stderr_line:
                logger.error(f"GStreamer [{bay_id}] stderr: {stderr_line.strip()}")
            
            # Check if process has terminated
            if process.poll() is not None:
                logger.info(f"GStreamer process for bay {bay_id} terminated with code {process.returncode}")
                if bay_id in active_streams:
                    del active_streams[bay_id]
                break
            
            # Small delay to prevent CPU hogging
            await asyncio.sleep(0.1)
    except Exception as e:
        logger.error(f"Error monitoring GStreamer process: {str(e)}")

@app.post("/stop/{bay_id}")
async def stop_stream(bay_id: str):
    if bay_id not in active_streams:
        raise HTTPException(status_code=404, detail=f"No active stream found for bay {bay_id}")
    
    process = active_streams[bay_id]
    logger.info(f"Stopping GStreamer process for bay {bay_id}")
    process.terminate()
    process.wait()
    del active_streams[bay_id]
    
    return JSONResponse(content={"message": f"Stopped streaming for bay {bay_id}"})

@app.get("/status")
async def get_status():
    return {
        "active_streams": list(active_streams.keys()),
        "total_bays": len([d for d in os.listdir(UPLOAD_DIR) if os.path.isdir(os.path.join(UPLOAD_DIR, d))])
    }

# Cleanup on shutdown
@app.on_event("shutdown")
async def shutdown_event():
    for process in active_streams.values():
        process.terminate()
        process.wait()
    active_streams.clear() 