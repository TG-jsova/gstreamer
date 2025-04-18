#!/usr/bin/env python3
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import sys
import signal
import os
import time
from datetime import datetime

class GStreamerMulticastStreamer:
    def __init__(self, multicast_address, port, buffer_duration=0.5):
        self.multicast_address = multicast_address
        self.port = port
        self.buffer_duration = buffer_duration
        self.pipeline = None
        self.loop = None
        self.buffer_filled = False
        self.buffer_start_time = None
        
        # Initialize GStreamer
        Gst.init(None)
        
    def on_message(self, bus, message):
        mtype = message.type
        if mtype == Gst.MessageType.EOS:
            print("End of stream")
            self.loop.quit()
        elif mtype == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"Error: {err}, {debug}")
            self.loop.quit()
        elif mtype == Gst.MessageType.STATE_CHANGED:
            old_state, new_state, pending_state = message.parse_state_changed()
            print(f"State changed from {old_state.value_name} to {new_state.value_name}")
            
            # When pipeline is ready, start buffering
            if new_state == Gst.State.PAUSED and not self.buffer_filled:
                self.buffer_start_time = time.time()
                print(f"Starting buffer of {self.buffer_duration} seconds...")
                
            # When buffer is filled, start playing
            if new_state == Gst.State.PAUSED and self.buffer_start_time:
                elapsed = time.time() - self.buffer_start_time
                if elapsed >= self.buffer_duration and not self.buffer_filled:
                    self.buffer_filled = True
                    print("Buffer filled, starting playback...")
                    self.pipeline.set_state(Gst.State.PLAYING)
    
    def create_pipeline(self):
        # Create the pipeline for MPEG-TS streaming
        pipeline_str = (
            f"udpsrc port={self.port} ! "
            "tsdemux ! "
            "mpegaudioparse ! "
            "avdec_mp3 ! "
            "audioconvert ! "
            "audioresample ! "
            "audio/x-raw,format=S16LE,rate=44100,channels=2 ! "
            "queue max-size-buffers=0 max-size-bytes=0 max-size-time=0 ! "
            "mp3enc ! "
            "mpegtsmux ! "
            f"udpsink host={self.multicast_address} port={self.port} sync=false"
        )
        
        print(f"Creating pipeline: {pipeline_str}")
        self.pipeline = Gst.parse_launch(pipeline_str)
        
        # Create a loop
        self.loop = GLib.MainLoop()
        
        # Add message handler
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_message, self.loop)
    
    def start(self):
        # Start in PAUSED state to fill buffer
        self.pipeline.set_state(Gst.State.PAUSED)
        print(f"Starting multicast stream on {self.multicast_address}:{self.port}")
        print("Buffering audio before starting playback...")
        
        try:
            self.loop.run()
        except KeyboardInterrupt:
            print("\nInterrupted by user")
        finally:
            self.pipeline.set_state(Gst.State.NULL)
            self.loop.quit()

def main():
    # Get configuration from environment variables
    multicast_address = os.environ.get('MULTICAST_ADDRESS', '239.255.1.1')
    port = int(os.environ.get('UDP_PORT', '5004'))
    buffer_duration = float(os.environ.get('BUFFER_DURATION', '0.5'))
    
    # Create and start the streamer
    streamer = GStreamerMulticastStreamer(multicast_address, port, buffer_duration)
    streamer.create_pipeline()
    streamer.start()

if __name__ == "__main__":
    main() 