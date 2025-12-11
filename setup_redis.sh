#!/bin/bash
# Setup script for Redis on EC2

echo "Setting up Redis for HTML Extractor API..."

# Install Redis
sudo apt update
sudo apt install -y redis-server

# Configure Redis
sudo sed -i 's/supervised no/supervised systemd/' /etc/redis/redis.conf

# Start Redis
sudo systemctl start redis-server
sudo systemctl enable redis-server

# Test Redis
redis-cli ping

echo "✅ Redis installed and started"
echo "   Test with: redis-cli ping"
echo "   Should return: PONG"

