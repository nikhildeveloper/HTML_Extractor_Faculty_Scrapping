# Deployment Guide - HTML Extractor API

## Prerequisites

- EC2 instance (Ubuntu 22.04 recommended)
- MongoDB Atlas account (free tier available)
- Python 3.8+

## Step 1: Setup Redis (Local on EC2)

```bash
# Run setup script
chmod +x setup_redis.sh
./setup_redis.sh

# Or manually:
sudo apt update
sudo apt install -y redis-server
sudo systemctl start redis-server
sudo systemctl enable redis-server

# Test Redis
redis-cli ping
# Should return: PONG
```

## Step 2: Setup MongoDB Atlas

1. **Create MongoDB Atlas account**: https://www.mongodb.com/cloud/atlas
2. **Create free cluster** (M0 - 512MB)
3. **Create database user**:
   - Go to Database Access → Add New Database User
   - Username: `extractor_user`
   - Password: (generate secure password)
4. **Whitelist IP address**:
   - Go to Network Access → Add IP Address
   - Add your EC2 IP or `0.0.0.0/0` for all IPs (less secure)
5. **Get connection string**:
   - Go to Database → Connect → Connect your application
   - Copy connection string
   - Format: `mongodb+srv://username:password@cluster0.xxxxx.mongodb.net/extractions?retryWrites=true&w=majority`

## Step 3: Install Dependencies

```bash
cd html_extractor

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements_api.txt

# Install Playwright browsers
playwright install chromium
playwright install-deps chromium
```

## Step 4: Configure Environment Variables

```bash
# Copy example file
cp env.example .env

# Edit .env file
nano .env
```

Add your MongoDB Atlas connection string:
```bash
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

MONGO_ATLAS_URI=mongodb+srv://extractor_user:your_password@cluster0.xxxxx.mongodb.net/extractions?retryWrites=true&w=majority
```

## Step 5: Test the Setup

```bash
# Test Redis
redis-cli ping

# Test MongoDB connection (Python)
python3 -c "
from pymongo import MongoClient
import os
from dotenv import load_dotenv
load_dotenv()
client = MongoClient(os.getenv('MONGO_ATLAS_URI'))
client.admin.command('ping')
print('✅ MongoDB connection successful')
"

# Start API server
python api.py
```

## Step 6: Run as Service (Production)

Create systemd service:

```bash
sudo nano /etc/systemd/system/html-extractor-api.service
```

Add this content:

```ini
[Unit]
Description=HTML Extractor API Service
After=network.target redis.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/html_extractor
Environment="PATH=/home/ubuntu/html_extractor/venv/bin"
EnvironmentFile=/home/ubuntu/html_extractor/.env
ExecStart=/home/ubuntu/html_extractor/venv/bin/python /home/ubuntu/html_extractor/api.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable html-extractor-api
sudo systemctl start html-extractor-api

# Check status
sudo systemctl status html-extractor-api

# View logs
sudo journalctl -u html-extractor-api -f
```

## Step 7: Configure Firewall

```bash
# Allow port 8000
sudo ufw allow 8000/tcp
sudo ufw enable
```

## Step 8: Test API

```bash
# Health check
curl http://localhost:8000/health

# Create extraction job
curl -X POST "http://localhost:8000/extract" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "selector": "main"
  }'

# Check status (use job_id from above)
curl "http://localhost:8000/extract/status/{job_id}"

# Get result (when completed)
curl "http://localhost:8000/extract/result/{job_id}"
```

## Troubleshooting

### Redis Connection Failed
```bash
# Check if Redis is running
sudo systemctl status redis-server

# Start Redis
sudo systemctl start redis-server

# Check Redis port
sudo netstat -tlnp | grep 6379
```

### MongoDB Connection Failed
- Check connection string format
- Verify IP is whitelisted in MongoDB Atlas
- Check username/password
- Verify cluster is running

### API Not Starting
```bash
# Check logs
sudo journalctl -u html-extractor-api -n 50

# Check if port is in use
sudo lsof -i :8000

# Test manually
cd /home/ubuntu/html_extractor
source venv/bin/activate
python api.py
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `REDIS_HOST` | Redis host | `localhost` |
| `REDIS_PORT` | Redis port | `6379` |
| `REDIS_DB` | Redis database number | `0` |
| `MONGO_ATLAS_URI` | MongoDB Atlas connection string | Required |

## Security Notes

1. **Never commit `.env` file** - Add to `.gitignore`
2. **Use strong MongoDB password**
3. **Restrict MongoDB IP whitelist** to your EC2 IP
4. **Use HTTPS** in production (Nginx reverse proxy)
5. **Set up rate limiting** if needed

## Monitoring

```bash
# Check Redis memory
redis-cli info memory

# Check MongoDB connection
# Use MongoDB Atlas dashboard

# Check API logs
sudo journalctl -u html-extractor-api -f

# Monitor system resources
htop
df -h  # Check disk space
```

