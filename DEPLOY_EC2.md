# Deploying HTML Extractor API on EC2

This guide walks you through deploying the HTML Extractor API on an Amazon EC2 instance.

## Prerequisites

- AWS account with EC2 access
- SSH key pair for EC2 access
- Basic knowledge of Linux commands

## Step 1: Launch EC2 Instance

1. **Go to EC2 Console** → Launch Instance
2. **Choose Instance Type**: `t3.medium` or larger (Playwright needs memory)
3. **Choose AMI**: Ubuntu 22.04 LTS (recommended)
4. **Storage**: 20GB+ (for browser binaries and outputs)
5. **Security Group**: 
   - Allow SSH (port 22) from your IP
   - Allow HTTP (port 8000) from anywhere (or specific IPs)
6. **Key Pair**: Select or create a key pair
7. **Launch Instance**

## Step 2: Connect to EC2 Instance

```bash
ssh -i your-key.pem ubuntu@your-ec2-ip
```

## Step 3: Initial Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3 and pip
sudo apt install -y python3 python3-pip python3-venv git

# Install system dependencies for Playwright
sudo apt install -y \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    libatspi2.0-0 \
    libxshmfence1
```

## Step 4: Deploy Your Code

### Option A: Using SCP (from your local machine)

```bash
# From your local machine
scp -i your-key.pem -r html_extractor/* ubuntu@your-ec2-ip:~/html_extractor/
```

### Option B: Using Git

```bash
# On EC2 instance
cd ~
git clone your-repo-url
cd html_extractor
```

## Step 5: Set Up Python Environment

```bash
cd ~/html_extractor

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

## Step 6: Test the API

```bash
# Start the API server
python api.py
```

In another terminal, test it:
```bash
curl http://localhost:8000/health
```

## Step 7: Run as a Service (Optional but Recommended)

Create a systemd service file:

```bash
sudo nano /etc/systemd/system/html-extractor-api.service
```

Add this content:

```ini
[Unit]
Description=HTML Extractor API Service
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/html_extractor
Environment="PATH=/home/ubuntu/html_extractor/venv/bin"
ExecStart=/home/ubuntu/html_extractor/venv/bin/python /home/ubuntu/html_extractor/api.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable html-extractor-api
sudo systemctl start html-extractor-api

# Check status
sudo systemctl status html-extractor-api

# View logs
sudo journalctl -u html-extractor-api -f
```

## Step 8: Configure Firewall

```bash
# Allow port 8000
sudo ufw allow 8000/tcp
sudo ufw enable
```

## Step 9: Use Nginx as Reverse Proxy (Optional)

For production, use Nginx as a reverse proxy:

```bash
# Install Nginx
sudo apt install -y nginx

# Create Nginx config
sudo nano /etc/nginx/sites-available/html-extractor-api
```

Add this configuration:

```nginx
server {
    listen 80;
    server_name your-domain.com;  # or your EC2 IP

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable and restart:

```bash
sudo ln -s /etc/nginx/sites-available/html-extractor-api /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

## Step 10: Test the API

From your local machine or browser:

```bash
# Health check
curl http://your-ec2-ip:8000/health

# Extract content
curl -X POST "http://your-ec2-ip:8000/extract" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/faculty",
    "selector": ".content",
    "include_links": true,
    "use_js": true
  }'
```

## API Documentation

Once deployed, access:
- Swagger UI: `http://your-ec2-ip:8000/docs`
- ReDoc: `http://your-ec2-ip:8000/redoc`

## Troubleshooting

### Playwright browsers not found
```bash
playwright install chromium --force
playwright install-deps chromium
```

### Service won't start
```bash
# Check logs
sudo journalctl -u html-extractor-api -n 50

# Check if port is in use
sudo lsof -i :8000
```

### Out of memory
- Upgrade to larger instance type (t3.large or larger)
- Or limit concurrent requests in your application

### Permission errors
```bash
sudo chown -R ubuntu:ubuntu ~/html_extractor
chmod +x ~/html_extractor/api.py
```

## Monitoring

### View API logs
```bash
sudo journalctl -u html-extractor-api -f
```

### Check resource usage
```bash
htop
df -h  # Check disk space
```

## Security Considerations

1. **Use HTTPS**: Set up SSL certificate with Let's Encrypt
2. **Restrict Access**: Use security groups to limit API access
3. **Rate Limiting**: Consider adding rate limiting to prevent abuse
4. **Authentication**: Add API key authentication for production use

## Quick Setup Script

Save this as `setup_ec2.sh` and run it on your EC2 instance:

```bash
#!/bin/bash
set -e

echo "Setting up HTML Extractor API on EC2..."

# Install system dependencies
sudo apt update
sudo apt install -y python3 python3-pip python3-venv \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libdbus-1-3 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libasound2 libpango-1.0-0 libcairo2 \
    libatspi2.0-0 libxshmfence1

# Create venv and install dependencies
cd ~/html_extractor
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements_api.txt
playwright install chromium
playwright install-deps chromium

echo "✅ Setup complete!"
echo "Start API with: source venv/bin/activate && python api.py"
```

Make it executable and run:
```bash
chmod +x setup_ec2.sh
./setup_ec2.sh
```

## Next Steps

- Set up monitoring (CloudWatch, etc.)
- Configure auto-scaling if needed
- Set up CI/CD pipeline
- Add authentication/authorization
- Set up backup for extracted content

