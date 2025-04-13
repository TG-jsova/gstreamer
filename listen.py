#!/usr/bin/env python3
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import sys
import signal
import os
from datetime import datetime

def on_message(bus, message, loop):
    mtype = message.type
    if mtype == Gst.MessageType.EOS:
        print("End of stream")
        loop.quit()
    elif mtype == Gst.MessageType.ERROR:
        err, debug = message.parse_error()
        print(f"Error: {err}, {debug}")
        loop.quit()
    elif mtype == Gst.MessageType.STATE_CHANGED:
        old_state, new_state, pending_state = message.parse_state_changed()
        print(f"State changed from {old_state.value_name} to {new_state.value_name}")

def main():
    # Initialize GStreamer
    Gst.init(None)
    
    # Create output directory if it doesn't exist
    output_dir = "/app/recordings"
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate output filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(output_dir, f"stream_{timestamp}.wav")
    
    # Create the pipeline for MPEG-TS streaming and recording
    pipeline_str = (
        "udpsrc port=5004 ! "
        "tsdemux ! "
        "mpegaudioparse ! "
        "avdec_mp3 ! "
        "audioconvert ! "
        "audioresample ! "
        "audio/x-raw,format=S16LE,rate=44100,channels=2 ! "
        "wavenc ! "
        f"filesink location={output_file} sync=false"
    )
    
    print(f"Starting pipeline: {pipeline_str}")
    print(f"Recording to: {output_file}")
    pipeline = Gst.parse_launch(pipeline_str)
    
    # Create a loop
    loop = GLib.MainLoop()
    
    # Add message handler
    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect("message", on_message, loop)
    
    # Start playing
    pipeline.set_state(Gst.State.PLAYING)
    print("Listening to UDP stream... Press Ctrl+C to stop")
    print("You can also play this stream in VLC using: udp://@239.255.1.1:5004")
    
    try:
        loop.run()
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    finally:
        pipeline.set_state(Gst.State.NULL)
        loop.quit()

if __name__ == "__main__":
    main() 