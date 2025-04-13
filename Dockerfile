FROM python:3.9-slim

# Install system dependencies including GStreamer
RUN apt-get update && apt-get install -y \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    iputils-ping \
    net-tools \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create upload directory
RUN mkdir -p /app/uploads

# Copy application code
COPY . .

# Expose port for the API
EXPOSE 8000

# Note: This container must be run with --network host for multicast support
# Example: docker run --network host --cap-add=NET_ADMIN --cap-add=NET_RAW mp3-streamer

# Command to run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"] 