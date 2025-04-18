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
import gi
import time
import threading
from datetime import datetime

# Configure GStreamer
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

# Initialize GStreamer
Gst.init(None)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Store active streams
active_streams = {}
UPLOAD_DIR = "/app/uploads"
MULTICAST_IP = "239.255.1.1"  # Default multicast IP
MULTICAST_PORT = 5004  # Default multicast port
BUFFER_DURATION = 0.5  # Default buffer duration in seconds

class StreamRequest(BaseModel):
    multicast_ip: Optional[str] = MULTICAST_IP
    multicast_port: Optional[int] = MULTICAST_PORT
    buffer_duration: Optional[float] = BUFFER_DURATION

class GStreamerMulticastStreamer:
    def __init__(self, file_path, multicast_address, port, buffer_duration=0.5):
        self.file_path = file_path
        self.multicast_address = multicast_address
        self.port = port
        self.buffer_duration = buffer_duration
        self.pipeline = None
        self.loop = None
        self.buffer_filled = False
        self.buffer_start_time = None
        self.is_playing = False
        self.is_finished = False
        self.thread = None
        
    def on_message(self, bus, message):
        mtype = message.type
        if mtype == Gst.MessageType.EOS:
            logger.info("End of stream")
            self.is_finished = True
            self.loop.quit()
        elif mtype == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            logger.error(f"Error: {err}, {debug}")
            self.is_finished = True
            self.loop.quit()
        elif mtype == Gst.MessageType.STATE_CHANGED:
            old_state, new_state, pending_state = message.parse_state_changed()
            logger.info(f"State changed from {old_state.value_name} to {new_state.value_name}")
            
            # When pipeline is ready, start buffering
            if new_state == Gst.State.PAUSED and not self.buffer_filled:
                self.buffer_start_time = time.time()
                logger.info(f"Starting buffer of {self.buffer_duration} seconds...")
                
            # When buffer is filled, start playing
            if new_state == Gst.State.PAUSED and self.buffer_start_time:
                elapsed = time.time() - self.buffer_start_time
                if elapsed >= self.buffer_duration and not self.buffer_filled:
                    self.buffer_filled = True
                    logger.info("Buffer filled, starting playback...")
                    self.pipeline.set_state(Gst.State.PLAYING)
                    self.is_playing = True
    
    def create_pipeline(self):
        # Create the pipeline for MPEG-TS streaming
        pipeline_str = (
            f"filesrc location={self.file_path} ! "
            "decodebin ! "
            "audioconvert ! "
            "audioresample ! "
            "audio/x-raw,format=S16LE,rate=44100,channels=2 ! "
            "queue max-size-buffers=0 max-size-bytes=0 max-size-time=0 ! "
            "lamemp3enc bitrate=192 ! "
            "mpegtsmux ! "
            f"udpsink host={self.multicast_address} port={self.port} sync=false"
        )
        
        logger.info(f"Creating pipeline: {pipeline_str}")
        self.pipeline = Gst.parse_launch(pipeline_str)
        
        # Create a loop
        self.loop = GLib.MainLoop()
        
        # Add message handler
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_message, self.loop)
    
    def run(self):
        # Start in PAUSED state to fill buffer
        self.pipeline.set_state(Gst.State.PAUSED)
        logger.info(f"Starting multicast stream on {self.multicast_address}:{self.port}")
        logger.info("Buffering audio before starting playback...")
        
        try:
            self.loop.run()
        except Exception as e:
            logger.error(f"Error in GStreamer loop: {str(e)}")
        finally:
            self.pipeline.set_state(Gst.State.NULL)
            self.loop.quit()
    
    def start(self):
        # Create and start the pipeline in a separate thread
        self.create_pipeline()
        self.thread = threading.Thread(target=self.run)
        self.thread.daemon = True
        self.thread.start()
    
    def stop(self):
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
        if self.loop:
            self.loop.quit()
        if self.thread:
            self.thread.join(timeout=2.0)
        self.is_playing = False
        self.is_finished = True

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
    buffer_duration = request.buffer_duration
    
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
        # Create a GStreamerMulticastStreamer instance
        streamer = GStreamerMulticastStreamer(
            file_path=file_path,
            multicast_address=multicast_ip,
            port=multicast_port,
            buffer_duration=buffer_duration
        )
        
        # Start the streamer
        streamer.start()
        
        # Store the streamer
        active_streams[bay_id] = streamer
        
        return JSONResponse(content={
            "message": f"Started streaming for bay {bay_id} to {multicast_ip}:{multicast_port}",
            "vlc_url": f"udp://@{multicast_ip}:{multicast_port}"
        })
    except Exception as e:
        logger.error(f"Error starting GStreamer pipeline: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/stop/{bay_id}")
async def stop_stream(bay_id: str):
    if bay_id not in active_streams:
        raise HTTPException(status_code=404, detail=f"No active stream found for bay {bay_id}")
    
    streamer = active_streams[bay_id]
    logger.info(f"Stopping GStreamer process for bay {bay_id}")
    streamer.stop()
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
    for streamer in active_streams.values():
        streamer.stop()
    active_streams.clear() 