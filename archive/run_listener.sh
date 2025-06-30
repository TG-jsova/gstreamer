#!/bin/bash

# Create recordings directory if it doesn't exist
mkdir -p recordings

# Build the listener container
echo "Building listener container..."
docker build -t multicast-listener -f Dockerfile.listener .

# Stop any existing container
echo "Cleaning up existing container..."
docker stop multicast-listener 2>/dev/null || true
docker rm multicast-listener 2>/dev/null || true

# Run the container with host network and required capabilities
echo "Starting listener..."
docker run -it --rm \
  --name multicast-listener \
  --network host \
  --cap-add=NET_ADMIN \
  --cap-add=NET_RAW \
  -v $(pwd)/recordings:/app/recordings \
  multicast-listener 