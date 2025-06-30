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
        
    def on_message(self, bus, message, loop):
        mtype = message.type
        if mtype == Gst.MessageType.EOS:
            logger.info("End of stream")
            self.is_finished = True
            # Remove from active streams
            for bay_id, streamer in list(active_streams.items()):
                if streamer == self:
                    logger.info(f"Removing completed stream for bay {bay_id}")
                    del active_streams[bay_id]
            # Quit the loop to stop the stream
            self.loop.quit()
        elif mtype == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            logger.error(f"Error: {err}, {debug}")
            # Get more detailed information about the error
            element = message.src.get_name()
            logger.error(f"Error occurred in element: {element}")
            self.is_finished = True
            # Remove from active streams
            for bay_id, streamer in list(active_streams.items()):
                if streamer == self:
                    logger.info(f"Removing error stream for bay {bay_id}")
                    del active_streams[bay_id]
            # Quit the loop to stop the stream
            self.loop.quit()
        elif mtype == Gst.MessageType.STATE_CHANGED:
            old_state, new_state, pending_state = message.parse_state_changed()
            element = message.src.get_name()
            logger.info(f"State changed in {element} from {old_state.value_name} to {new_state.value_name}")
            
            # When pipeline is ready, start buffering
            if new_state == Gst.State.PAUSED and not self.buffer_filled and element == "pipeline0":
                self.buffer_start_time = time.time()
                logger.info(f"Starting buffer of {self.buffer_duration} seconds...")
                
            # When buffer is filled, start playing
            if new_state == Gst.State.PAUSED and self.buffer_start_time and element == "pipeline0":
                elapsed = time.time() - self.buffer_start_time
                if elapsed >= self.buffer_duration and not self.buffer_filled:
                    self.buffer_filled = True
                    logger.info("Buffer filled, starting playback...")
                    self.pipeline.set_state(Gst.State.PLAYING)
                    self.is_playing = True
        elif mtype == Gst.MessageType.DURATION_CHANGED:
            # Log the duration of the stream
            duration = self.pipeline.query_duration(Gst.Format.TIME)[1] / Gst.SECOND
            logger.info(f"Stream duration: {duration:.3f} seconds")
        elif mtype == Gst.MessageType.STREAM_START:
            logger.info("Stream started")
        elif mtype == Gst.MessageType.NEW_CLOCK:
            logger.info("New clock selected")
    
    def create_pipeline(self):
        # Create the pipeline for MP3 streaming over UDP
        pipeline_str = (
            f"filesrc location={self.file_path} ! "
            "decodebin ! "
            "audioconvert ! "
            "audioresample ! "
            "audio/x-raw,format=S16LE,rate=44100,channels=2 ! "
            "lamemp3enc bitrate=192 ! "
            "queue max-size-buffers=100 ! "
            f"udpsink host={self.multicast_address} port={self.port} sync=true"
        )
        
        logger.info(f"Creating pipeline: {pipeline_str}")
        self.pipeline = Gst.parse_launch(pipeline_str)
        
        # Create a loop
        self.loop = GLib.MainLoop()
        
        # Add message handler
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_message, self.loop)
        
        # Add a probe to the sink pad of the udpsink to monitor data flow
        sink = self.pipeline.get_by_name("udpsink0")
        if sink:
            sinkpad = sink.get_static_pad("sink")
            if sinkpad:
                sinkpad.add_probe(Gst.PadProbeType.BUFFER, self.on_buffer_probe, None)
                logger.info("Added buffer probe to udpsink")
            else:
                logger.warning("Could not get sink pad from udpsink")
        else:
            logger.warning("Could not find udpsink element in pipeline")
    
    def on_buffer_probe(self, pad, info, user_data):
        # Log buffer information
        buffer = info.get_buffer()
        pts = buffer.pts / Gst.SECOND if buffer.pts != Gst.CLOCK_TIME_NONE else 0
        duration = buffer.duration / Gst.SECOND if buffer.duration != Gst.CLOCK_TIME_NONE else 0
        size = buffer.get_size()
        logger.info(f"Buffer: pts={pts:.3f}s, duration={duration:.3f}s, size={size} bytes")
        return Gst.PadProbeReturn.OK
    
    def run(self):
        # Start in PAUSED state to fill buffer
        ret = self.pipeline.set_state(Gst.State.PAUSED)
        if ret == Gst.StateChangeReturn.FAILURE:
            logger.error("Failed to set pipeline to PAUSED state")
            self.is_finished = True
            return
        
        logger.info(f"Starting multicast stream on {self.multicast_address}:{self.port}")
        logger.info("Buffering audio before starting playback...")
        
        # Set a timer to transition to PLAYING state after buffer_duration + 1 second
        # This is a fallback in case the state change message is not received
        def start_playback():
            if not self.is_playing and not self.is_finished:
                logger.info("Fallback: Transitioning to PLAYING state")
                self.pipeline.set_state(Gst.State.PLAYING)
                self.is_playing = True
        
        # Schedule the playback start after buffer_duration + 1 second
        GLib.timeout_add(int((self.buffer_duration + 1) * 1000), start_playback)
        
        # Log the start time
        start_time = time.time()
        logger.info(f"Playback started at {start_time}")
        
        try:
            self.loop.run()
        except Exception as e:
            logger.error(f"Error in GStreamer loop: {str(e)}")
            self.is_finished = True
        finally:
            # Log the end time and total duration
            end_time = time.time()
            total_duration = end_time - start_time
            logger.info(f"Playback ended at {end_time}, total duration: {total_duration:.3f} seconds")
            self.pipeline.set_state(Gst.State.NULL)
            self.loop.quit()
    
    def start(self):
        # Create and start the pipeline in a separate thread
        self.create_pipeline()
        self.thread = threading.Thread(target=self.run)
        self.thread.daemon = True
        self.thread.start()
    
    def stop(self):
        logger.info("Stopping GStreamer stream")
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
        if self.loop:
            self.loop.quit()
        # Don't try to join the thread if we're in the same thread
        if self.thread and self.thread != threading.current_thread():
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