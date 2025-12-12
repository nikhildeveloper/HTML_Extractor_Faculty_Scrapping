#!/bin/bash
# Script to fix the HTML Extractor container on EC2
# Run this on your EC2 instance if the container is missing REDIS_HOST

set -e

echo "🔧 Fixing HTML Extractor container..."

# Get EC2 private IP
PRIVATE_IP=$(curl -s http://169.254.169.254/latest/meta-data/local-ipv4)
if [ -z "$PRIVATE_IP" ]; then
    echo "❌ Failed to get EC2 private IP"
    exit 1
fi
echo "✅ EC2 Private IP: $PRIVATE_IP"

# Check if MongoDB URI is provided
if [ -z "$MONGO_ATLAS_URI" ]; then
    echo "⚠️  MONGO_ATLAS_URI not set. Please set it:"
    echo "   export MONGO_ATLAS_URI='your_mongodb_uri_here'"
    echo ""
    read -p "Enter MongoDB Atlas URI (or press Enter to skip): " MONGO_URI
    if [ -n "$MONGO_URI" ]; then
        MONGO_ATLAS_URI="$MONGO_URI"
    else
        echo "❌ MongoDB URI is required"
        exit 1
    fi
fi

# Stop and remove existing container
echo "🛑 Stopping existing container..."
docker stop html_extractor_faculty_scrapping 2>/dev/null || true
docker rm html_extractor_faculty_scrapping 2>/dev/null || true

# Verify Redis is running
echo "🔍 Checking Redis..."
if ! redis-cli ping > /dev/null 2>&1; then
    echo "⚠️  Redis is not responding. Starting Redis..."
    sudo systemctl start redis-server
    sleep 2
    if ! redis-cli ping > /dev/null 2>&1; then
        echo "❌ Redis failed to start"
        exit 1
    fi
fi
echo "✅ Redis is running"

# Check Redis binding
REDIS_BIND=$(sudo grep "^bind" /etc/redis/redis.conf | grep -v "^#" | awk '{print $2}' | head -1)
if [ "$REDIS_BIND" = "127.0.0.1" ] || [ -z "$REDIS_BIND" ]; then
    echo "🔧 Configuring Redis to accept connections from Docker..."
    sudo sed -i 's/^bind 127.0.0.1 ::1/bind 0.0.0.0/' /etc/redis/redis.conf || true
    sudo sed -i 's/^bind 127.0.0.1/bind 0.0.0.0/' /etc/redis/redis.conf || true
    sudo sed -i 's/^protected-mode yes/protected-mode no/' /etc/redis/redis.conf || true
    sudo systemctl restart redis-server
    sleep 2
    echo "✅ Redis reconfigured"
fi

# Pull latest image
echo "📥 Pulling latest Docker image..."
docker pull nikhilsaijaddu/html_extractor_faculty_scrapping:latest

# Run container with correct environment variables
echo "🚀 Starting container with correct environment variables..."
docker run -d \
  --name html_extractor_faculty_scrapping \
  -p 8000:8000 \
  -e REDIS_HOST="$PRIVATE_IP" \
  -e REDIS_PORT="6379" \
  -e REDIS_DB="0" \
  -e MONGO_ATLAS_URI="$MONGO_ATLAS_URI" \
  --restart unless-stopped \
  nikhilsaijaddu/html_extractor_faculty_scrapping:latest

# Wait a moment for container to start
sleep 5

# Verify container is running
if docker ps | grep -q html_extractor_faculty_scrapping; then
    echo "✅ Container is running"
    
    # Verify environment variables
    echo "🔍 Verifying environment variables..."
    CONTAINER_REDIS_HOST=$(docker exec html_extractor_faculty_scrapping printenv REDIS_HOST || echo "")
    if [ -n "$CONTAINER_REDIS_HOST" ]; then
        echo "✅ REDIS_HOST is set to: $CONTAINER_REDIS_HOST"
    else
        echo "❌ REDIS_HOST is not set in container!"
    fi
    
    # Show logs
    echo ""
    echo "📋 Container logs (last 20 lines):"
    docker logs html_extractor_faculty_scrapping --tail 20
    
    echo ""
    echo "✅ Container fixed and running!"
    echo "🌐 API should be available at: http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4):8000"
else
    echo "❌ Container failed to start"
    echo "📋 Container logs:"
    docker logs html_extractor_faculty_scrapping --tail 50
    exit 1
fi

