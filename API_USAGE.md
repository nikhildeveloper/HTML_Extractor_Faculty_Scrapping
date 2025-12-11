# API Usage Guide

## Overview

The HTML Extractor API uses an async job pattern:
1. Submit extraction request → Get `job_id` immediately
2. Poll status endpoint → Check if extraction is complete
3. Fetch result → Get full extracted content when ready

This avoids timeout issues and provides a responsive experience.

## Endpoints

### 1. Create Extraction Job

**POST** `/extract`

Creates a new extraction job and returns immediately with a `job_id`.

**Request:**
```json
{
  "url": "https://example.com/faculty",
  "selector": ".content .title,.content .meta",
  "include_links": true,
  "use_js": true,
  "wait_time": 5.0
}
```

**Response:**
```json
{
  "job_id": "abc-123-def-456",
  "status": "processing",
  "message": "Extraction job created. Poll /extract/status/{job_id} for updates."
}
```

**Time:** < 1 second

---

### 2. Check Job Status

**GET** `/extract/status/{job_id}`

Check the status of an extraction job. Poll this endpoint every 2-3 seconds.

**Response (processing):**
```json
{
  "job_id": "abc-123-def-456",
  "status": "processing",
  "pages_extracted": 0,
  "progress": 0,
  "message": "Starting extraction..."
}
```

**Response (completed):**
```json
{
  "job_id": "abc-123-def-456",
  "status": "completed",
  "pages_extracted": 12,
  "total_characters": 185000,
  "completed_at": "2024-12-10T20:00:26"
}
```

**Response (failed):**
```json
{
  "job_id": "abc-123-def-456",
  "status": "failed",
  "error": "No content extracted. The selector might not match any elements."
}
```

**Time:** < 0.1 seconds (fast, reads from Redis)

---

### 3. Get Extraction Result

**GET** `/extract/result/{job_id}`

Get the complete extracted content. Only works when status is "completed".

**Response:**
```json
{
  "job_id": "abc-123-def-456",
  "url": "https://example.com/faculty",
  "selector": ".content .title,.content .meta",
  "pages_extracted": 12,
  "total_characters": 185000,
  "total_links": 245,
  "content": "Osita Afoaku — https://...\nPhone: (812) 855-0749\n...",
  "links": [
    {"text": "Profile", "url": "https://example.com/profile1"},
    ...
  ],
  "created_at": "2024-12-10T20:00:00",
  "completed_at": "2024-12-10T20:00:26"
}
```

**Time:** 0.5-1 second (fetches from MongoDB Atlas)

---

### 4. Health Check

**GET** `/health`

Check if API, Redis, and MongoDB are healthy.

**Response:**
```json
{
  "status": "healthy",
  "redis": "healthy",
  "mongodb": "healthy",
  "timestamp": "2024-12-10T20:00:00"
}
```

---

## Frontend Integration Example

### JavaScript/TypeScript

```javascript
async function extractContent(url, selector) {
  // Step 1: Create job
  const createResponse = await fetch('http://your-ec2-ip:8000/extract', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      url: url,
      selector: selector,
      include_links: true,
      use_js: true
    })
  });
  
  const { job_id } = await createResponse.json();
  console.log('Job created:', job_id);
  
  // Step 2: Poll for status
  const pollInterval = setInterval(async () => {
    const statusResponse = await fetch(`http://your-ec2-ip:8000/extract/status/${job_id}`);
    const status = await statusResponse.json();
    
    console.log('Status:', status.status);
    
    if (status.status === 'completed') {
      clearInterval(pollInterval);
      
      // Step 3: Fetch result
      const resultResponse = await fetch(`http://your-ec2-ip:8000/extract/result/${job_id}`);
      const result = await resultResponse.json();
      
      console.log('Extraction complete!');
      console.log('Pages:', result.pages_extracted);
      console.log('Content length:', result.total_characters);
      
      // Use the extracted content
      displayContent(result.content);
      displayLinks(result.links);
      
    } else if (status.status === 'failed') {
      clearInterval(pollInterval);
      console.error('Extraction failed:', status.error);
      showError(status.error);
    } else {
      // Update progress
      updateProgress(status);
    }
  }, 2000); // Poll every 2 seconds
}
```

### Python

```python
import requests
import time

def extract_content(url, selector):
    # Step 1: Create job
    response = requests.post(
        'http://your-ec2-ip:8000/extract',
        json={
            'url': url,
            'selector': selector,
            'include_links': True,
            'use_js': True
        }
    )
    job_id = response.json()['job_id']
    print(f'Job created: {job_id}')
    
    # Step 2: Poll for status
    while True:
        status_response = requests.get(
            f'http://your-ec2-ip:8000/extract/status/{job_id}'
        )
        status = status_response.json()
        
        if status['status'] == 'completed':
            # Step 3: Fetch result
            result_response = requests.get(
                f'http://your-ec2-ip:8000/extract/result/{job_id}'
            )
            result = result_response.json()
            
            print(f'Extraction complete!')
            print(f'Pages: {result["pages_extracted"]}')
            print(f'Content: {result["content"][:100]}...')
            return result
            
        elif status['status'] == 'failed':
            print(f'Extraction failed: {status["error"]}')
            return None
        
        time.sleep(2)  # Poll every 2 seconds
```

---

## Error Handling

### Job Not Found (404)
```json
{
  "detail": "Job not found or expired. Jobs expire after 1 hour."
}
```

### Job Not Completed (400)
```json
{
  "detail": "Job status is 'processing', not completed. Current status: Starting extraction..."
}
```

### Extraction Failed
Check status endpoint - will return `"status": "failed"` with error message.

---

## Best Practices

1. **Polling Interval**: Poll every 2-3 seconds (not too frequently)
2. **Timeout**: Set a maximum polling time (e.g., 5 minutes)
3. **Error Handling**: Always check for "failed" status
4. **Progress Updates**: Show progress to users while polling
5. **Result Caching**: Cache results on frontend if needed

---

## Example cURL Commands

```bash
# Create job
curl -X POST "http://localhost:8000/extract" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/faculty",
    "selector": ".content"
  }'

# Check status
curl "http://localhost:8000/extract/status/abc-123-def-456"

# Get result
curl "http://localhost:8000/extract/result/abc-123-def-456"
```

