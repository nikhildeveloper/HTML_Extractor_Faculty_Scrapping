# HTML Content Extractor API

FastAPI-based service for extracting HTML content from URLs with CSS selector support, pagination handling, and async job processing.

## Features

- **Async Job Processing**: Non-blocking extraction with job ID tracking
- **CSS Selector Support**: Target specific content areas
- **Pagination Handling**: Automatic detection and extraction of paginated content
- **JavaScript Rendering**: Uses Playwright for dynamic content
- **User-Controlled Pagination**: Specify pagination limits per link
- **Real-time Progress**: Track page extraction progress
- **Redis Status Tracking**: Fast job status updates
- **MongoDB Storage**: Persistent storage of extracted content
- **Job Cancellation**: Cancel individual or group extractions

## Tech Stack

- **FastAPI**: Modern Python web framework
- **Playwright**: Browser automation for JS rendering
- **Redis**: Job status and progress tracking
- **MongoDB Atlas**: Content storage
- **BeautifulSoup4**: HTML parsing

## Quick Start

### Prerequisites

- Python 3.11+
- Redis (local or remote)
- MongoDB Atlas connection string
- Playwright browsers installed

### Installation

```bash
# Clone repository
cd html_extractor

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements_api.txt

# Install Playwright browsers
playwright install chromium
playwright install-deps chromium
```

### Configuration

Create a `.env` file:

```env
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
MONGO_ATLAS_URI=mongodb+srv://user:password@cluster.mongodb.net/extractions?retryWrites=true&w=majority
```

### Run Locally

```bash
# Activate virtual environment
source venv/bin/activate

# Start the API
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

Or use the provided script:

```bash
chmod +x start_api.sh
./start_api.sh
```

### Docker

```bash
# Build and run with docker-compose
docker-compose up -d

# Or build manually
docker build -t html-extractor .
docker run -p 8000:8000 --env-file .env html-extractor
```

## API Endpoints

### Health Check
```bash
GET /health
```

### Create Extraction Job
```bash
POST /extract
Content-Type: application/json

{
  "url": "https://example.com/faculty",
  "selector": ".content",
  "include_links": true,
  "use_js": true,
  "wait_time": 5.0,
  "has_pagination": true,
  "max_pages": 10
}
```

### Check Job Status
```bash
GET /extract/status/{job_id}
```

### Get Results
```bash
GET /extract/result/{job_id}
```

### Cancel Job
```bash
DELETE /extract/{job_id}
```

## API Documentation

Once running, access:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Deployment

### EC2 Deployment

See [DEPLOY_EC2.md](./DEPLOY_EC2.md) for detailed EC2 deployment instructions.

### Docker Deployment

```bash
# Build image
docker build -t html-extractor .

# Run container
docker run -d \
  -p 8000:8000 \
  --env-file .env \
  --name html-extractor-api \
  html-extractor
```

### GitHub Actions CI/CD

The repository includes a GitHub Actions workflow (`.github/workflows/deploy.yml`) that:
- Builds and tests on push to main/master
- Builds Docker image and pushes to GitHub Container Registry
- Deploys to server via SSH (if configured)

**Required Secrets:**
- `DEPLOY_HOST`: Server IP/hostname
- `DEPLOY_USER`: SSH username
- `DEPLOY_SSH_KEY`: SSH private key

## Project Structure

```
html_extractor/
├── api.py                 # FastAPI application
├── extract_html_content.py # Core extraction logic
├── requirements_api.txt    # Python dependencies
├── Dockerfile             # Docker image definition
├── docker-compose.yml     # Local development setup
├── .github/
│   └── workflows/
│       └── deploy.yml    # CI/CD pipeline
└── README.md             # This file
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `REDIS_HOST` | Redis server host | `localhost` |
| `REDIS_PORT` | Redis server port | `6379` |
| `REDIS_DB` | Redis database number | `0` |
| `MONGO_ATLAS_URI` | MongoDB Atlas connection string | **Required** |

## Development

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run tests
pytest tests/ -v
```

### Code Style

```bash
# Install formatter
pip install black isort

# Format code
black .
isort .
```

## Troubleshooting

### Playwright browsers not found
```bash
playwright install chromium --force
playwright install-deps chromium
```

### Redis connection failed
- Check Redis is running: `redis-cli ping`
- Verify `REDIS_HOST` and `REDIS_PORT` in `.env`

### MongoDB connection failed
- Verify `MONGO_ATLAS_URI` is correct
- Check network access to MongoDB Atlas
- Ensure IP whitelist includes your server IP

## License

[Your License Here]

## Support

For issues and questions, please open an issue on GitHub.
