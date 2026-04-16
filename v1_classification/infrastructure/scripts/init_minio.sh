#!/bin/bash

# Initialize MinIO bucket for image classification
# Run this after docker-compose up

echo "Waiting for MinIO to be ready..."
sleep 5

# Install mc (MinIO client) if not available
if ! command -v mc &> /dev/null; then
    echo "Installing MinIO client..."
    wget https://dl.min.io/client/mc/release/linux-amd64/mc
    chmod +x mc
    sudo mv mc /usr/local/bin/
fi

# Configure mc
mc alias set local http://localhost:9000 minioadmin minioadmin

# Create bucket
mc mb local/classify-bucket --ignore-existing

# Set anonymous read policy (for presigned URLs)
mc anonymous set download local/classify-bucket

echo "MinIO bucket 'classify-bucket' created and configured"
