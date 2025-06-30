#!/bin/bash

# Build the container
echo "Building container..."
docker build -t mp3-streamer .

# Stop any existing container
echo "Cleaning up existing container..."
docker stop mp3-streamer 2>/dev/null || true
docker rm mp3-streamer 2>/dev/null || true

# Create uploads directory if it doesn't exist
mkdir -p uploads

# Run the container with bridge network and required capabilities
echo "Starting container..."
docker run -d \
  --name mp3-streamer \
  -p 8000:8000 \
  --cap-add=NET_ADMIN \
  --cap-add=NET_RAW \
  --sysctl net.ipv4.ip_forward=1 \
  -v $(pwd)/uploads:/app/uploads \
  mp3-streamer

# Wait for the container to start
echo "Waiting for container to start..."
sleep 5

# Check if the container is running
if docker ps | grep -q mp3-streamer; then
    echo "Container is running"
    echo "API is available at http://localhost:8000"
    echo "You can test it with: curl http://localhost:8000/status"
    
    # Show container logs
    echo "Container logs:"
    docker logs mp3-streamer
    
    # Check if port 8000 is listening
    echo "Checking if port 8000 is listening..."
    if netstat -an | grep -q ":8000 "; then
        echo "Port 8000 is listening"
    else
        echo "Warning: Port 8000 is not listening"
        echo "Trying to check inside the container..."
        docker exec mp3-streamer netstat -an | grep 8000 || echo "Port not listening inside container either"
    fi
    
    echo "Multicast stream will be sent to 239.255.1.1:5004"
else
    echo "Container failed to start"
    docker logs mp3-streamer
fi 