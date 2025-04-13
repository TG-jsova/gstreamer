# GStreamer Audio Streaming Service

A Docker-based audio streaming service that uses GStreamer to stream MP3 files over UDP. The service includes both a sender (FastAPI-based) and a listener component.

## Features

- Stream MP3 files over UDP
- Record streams as WAV files
- Play streams directly in VLC player
- REST API for managing streams
- Docker-based deployment
- Support for multiple audio bays

## Prerequisites

- Docker and Docker Compose
- VLC Media Player (for direct playback)
- Python 3.9+ (for local development)

## Project Structure

```
.
├── Dockerfile              # Sender container configuration
├── Dockerfile.listener     # Listener container configuration
├── main.py                # FastAPI sender application
├── listen.py              # GStreamer listener application
├── requirements.txt       # Python dependencies for sender
├── listener_requirements.txt  # Python dependencies for listener
├── run.sh                 # Script to run the sender
├── run_listener.sh        # Script to run the listener
└── uploads/              # Directory for uploaded MP3 files
```

## Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd gstreamer
```

2. Create necessary directories:
```bash
mkdir -p uploads recordings
```

## Running the Service

### Starting the Sender

```bash
./run.sh
```

This will:
- Build the sender container
- Start the FastAPI service on port 8000
- Set up the necessary network configurations

### Starting the Listener

```bash
./run_listener.sh
```

This will:
- Build the listener container
- Start listening for UDP streams
- Save received streams as WAV files in the recordings directory

## API Endpoints

### Upload MP3 File
```bash
curl -X POST -F "file=@your_song.mp3" http://localhost:8000/upload/bay1
```

### Start Streaming
```bash
curl -X POST http://localhost:8000/play/bay1
```

### Stop Streaming
```bash
curl -X POST http://localhost:8000/stop/bay1
```

### Check Status
```bash
curl http://localhost:8000/status
```

## Listening to Streams

### Using VLC Player

1. Open VLC Media Player
2. Go to Media -> Open Network Stream (or press Cmd+N on Mac)
3. Enter the stream URL:
```
udp://@239.255.1.1:5004
```

### Using the Listener

The listener will automatically save streams as WAV files in the `recordings` directory with timestamps in the filenames.

## Network Configuration

- Default multicast IP: 239.255.1.1
- Default port: 5004
- The sender uses host networking for multicast support
- The listener uses host networking to receive streams

## Docker Configuration

### Sender Container
- Uses Python 3.9 slim image
- Includes GStreamer and necessary plugins
- Exposes port 8000 for the API
- Mounts the uploads directory for MP3 files

### Listener Container
- Uses Python 3.9 slim image
- Includes GStreamer and necessary plugins
- Mounts the recordings directory for WAV files
- Uses host networking for stream reception

## Troubleshooting

1. If streams aren't being received:
   - Check if the sender is running: `docker ps | grep mp3-streamer`
   - Verify the multicast IP and port match in both sender and listener
   - Ensure no firewall is blocking UDP traffic

2. If VLC can't play the stream:
   - Verify the stream is active using the status endpoint
   - Check if the correct IP and port are being used
   - Try restarting VLC

3. If the listener isn't saving files:
   - Check if the recordings directory is properly mounted
   - Verify the listener has write permissions
   - Check the listener logs for errors

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

