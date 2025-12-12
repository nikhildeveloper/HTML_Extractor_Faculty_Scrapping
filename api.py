#!/usr/bin/env python3
"""
FastAPI wrapper for HTML Content Extractor
Provides REST API endpoints for extracting HTML content from URLs
Uses async job pattern with Redis (status) and MongoDB Atlas (content storage)
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl, Field
from typing import Optional, List, Dict
import asyncio
import json
import uuid
import os
from datetime import datetime
from pathlib import Path
import sys

# Redis for job status (local on EC2)
import redis

# MongoDB Atlas for content storage (cloud)
from pymongo import MongoClient
from bson import ObjectId

# Import extraction functions from the main script
from extract_html_content import (
    extract_all_pages_recursive
)

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Initialize Redis (local on EC2)
REDIS_HOST = os.getenv("REDIS_HOST")
if not REDIS_HOST:
    print("❌ REDIS_HOST not set in environment variables")
    print("   Set it in .env file or environment")
    sys.exit(1)
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))

try:
    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True
    )
    # Test connection
    redis_client.ping()
    print(f"✅ Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
except Exception as e:
    print(f"❌ Redis connection failed: {e}")
    print("   Make sure Redis is running: sudo systemctl start redis")
    sys.exit(1)

# Initialize MongoDB Atlas (cloud)
MONGO_ATLAS_URI = os.getenv("MONGO_ATLAS_URI")
if not MONGO_ATLAS_URI:
    print("❌ MONGO_ATLAS_URI not set in environment variables")
    print("   Set it in .env file or environment")
    sys.exit(1)

try:
    mongo_client = MongoClient(MONGO_ATLAS_URI)
    # Test connection
    mongo_client.admin.command('ping')
    db = mongo_client['extractions']
    print(f"✅ Connected to MongoDB Atlas")
except Exception as e:
    print(f"❌ MongoDB Atlas connection failed: {e}")
    print("   Check your MONGO_ATLAS_URI connection string")
    sys.exit(1)

app = FastAPI(
    title="HTML Content Extractor API",
    description="Extract HTML content from URLs with CSS selector support and pagination handling. Uses async job pattern.",
    version="2.0.0"
)

# Dictionary to track cancellation requests
cancellation_flags = {}


class ExtractRequest(BaseModel):
    """Request model for extraction"""
    url: HttpUrl = Field(..., description="URL to extract content from")
    selector: Optional[str] = Field(None, description="CSS selector to target specific content (e.g., 'main', '.content', '#article')")
    include_links: bool = Field(True, description="Whether to include links in the output")
    use_js: bool = Field(True, description="Whether to use JavaScript rendering (Playwright)")
    wait_time: float = Field(5.0, description="Wait time in seconds for JS content to load", ge=0, le=60)
    has_pagination: Optional[bool] = Field(False, description="Whether the page has pagination")
    max_pages: Optional[int] = Field(1, description="Maximum number of pages to extract (only used if has_pagination is True)", ge=1, le=1000)


class JobResponse(BaseModel):
    """Response model for job creation"""
    job_id: str
    status: str
    message: str


class StatusResponse(BaseModel):
    """Response model for job status"""
    job_id: str
    status: str
    pages_extracted: Optional[int] = None
    total_characters: Optional[int] = None
    progress: Optional[int] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    message: Optional[str] = None


class ResultResponse(BaseModel):
    """Response model for extraction result"""
    job_id: str
    url: str
    selector: Optional[str]
    pages_extracted: int
    total_characters: int
    total_links: int
    content: str
    links: List[Dict[str, str]]
    created_at: str
    completed_at: str


def update_redis_status(job_id: str, status_data: dict):
    """Update job status in Redis"""
    try:
        redis_client.setex(
            f"job:{job_id}",
            3600,  # 1 hour TTL
            json.dumps(status_data)
        )
    except Exception as e:
        print(f"⚠️  Error updating Redis for {job_id}: {e}")


def deduplicate_links(links: List) -> List[Dict[str, str]]:
    """Deduplicate links while preserving order"""
    if not links:
        return []
    
    seen = set()
    unique_links = []
    
    for link in links:
        if isinstance(link, dict):
            link_str = f"{link.get('text', '')} — {link.get('url', '')}"
        else:
            link_str = str(link)
        
        if link_str not in seen:
            seen.add(link_str)
            unique_links.append(
                link if isinstance(link, dict) else {'text': '', 'url': str(link)}
            )
    
    return unique_links


async def process_extraction(job_id: str, request: ExtractRequest):
    """Background task to process extraction"""
    print(f"\n🔄 Background extraction started for job: {job_id}")
    print(f"   URL: {request.url}")
    print(f"   Selector: {request.selector}")
    
    try:
        # Update status: processing started
        update_redis_status(job_id, {
            "status": "processing",
            "url": str(request.url),
            "selector": request.selector,
            "progress": 0,
            "pages_extracted": 0,
            "message": "Starting extraction...",
            "created_at": datetime.now().isoformat()
        })
        
        # Check for cancellation before starting
        if cancellation_flags.get(job_id):
            update_redis_status(job_id, {
                "status": "cancelled",
                "message": "Extraction cancelled before starting",
                "cancelled_at": datetime.now().isoformat()
            })
            cancellation_flags.pop(job_id, None)
            print(f"🛑 Job {job_id} cancelled before extraction started")
            return
        
        # Run extraction (this takes time)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            extract_all_pages_recursive,
            str(request.url),
            request.use_js,
            request.wait_time,
            request.selector,
            request.include_links,
            job_id,  # Pass job_id for cancellation checking
            request.has_pagination,  # Pass pagination flag
            request.max_pages if request.has_pagination else 1  # Pass max pages limit
        )
        
        # Check for cancellation after extraction
        if cancellation_flags.get(job_id):
            update_redis_status(job_id, {
                "status": "cancelled",
                "message": "Extraction cancelled",
                "cancelled_at": datetime.now().isoformat()
            })
            cancellation_flags.pop(job_id, None)
            print(f"🛑 Job {job_id} cancelled")
            return
        
        if not result or not isinstance(result, list) or len(result) == 0:
            raise Exception("No content extracted. The selector might not match any elements.")
        
        print(f"✅ Extraction completed: {len(result)} pages")
        
        # Combine all pages
        combined_text_parts = []
        all_links = []
        
        for page_data in result:
            page_text = page_data.get('text', '')
            if page_text:
                combined_text_parts.append(page_text)
            
            if request.include_links and page_data.get('links'):
                all_links.extend(page_data.get('links', []))
        
        combined_content = '\n\n'.join(combined_text_parts)
        unique_links = deduplicate_links(all_links)
        
        print(f"📊 Combined: {len(combined_content)} characters, {len(unique_links)} links")
        
        # Prepare document for MongoDB
        extraction_doc = {
            "job_id": job_id,
            "url": str(request.url),
            "selector": request.selector,
            "content": combined_content,  # Large content
            "links": unique_links,
            "pages_extracted": len(result),
            "total_characters": len(combined_content),
            "total_links": len(unique_links),
            "created_at": datetime.now(),
            "completed_at": datetime.now()
        }
        
        # Save to MongoDB Atlas
        db.extractions.insert_one(extraction_doc)
        print(f"💾 Saved to MongoDB Atlas: job_id={job_id}")
        
        # Update Redis with completion status (small data only)
        update_redis_status(job_id, {
            "status": "completed",
            "pages_extracted": len(result),
            "total_characters": len(combined_content),
            "total_links": len(unique_links),
            "completed_at": datetime.now().isoformat(),
            "message": f"Successfully extracted {len(result)} page(s)"
        })
        
        print(f"✅ Job {job_id} completed successfully")
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Extraction failed for job {job_id}: {error_msg}")
        
        # Update Redis with error
        update_redis_status(job_id, {
            "status": "failed",
            "error": error_msg,
            "failed_at": datetime.now().isoformat(),
            "message": f"Extraction failed: {error_msg}"
        })
        
        # Optionally log error to MongoDB
        try:
            db.extraction_errors.insert_one({
                "job_id": job_id,
                "url": str(request.url),
                "selector": request.selector,
                "error": error_msg,
                "failed_at": datetime.now()
            })
        except:
            pass


@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "name": "HTML Content Extractor API",
        "version": "2.0.0",
        "description": "Async job-based extraction with Redis and MongoDB Atlas",
        "endpoints": {
            "POST /extract": "Create extraction job (returns job_id immediately)",
            "GET /extract/status/{job_id}": "Check job status",
            "GET /extract/result/{job_id}": "Get extraction result (when completed)",
            "DELETE /extract/{job_id}": "Cancel an extraction job"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Check Redis
        redis_client.ping()
        redis_status = "healthy"
    except:
        redis_status = "unhealthy"
    
    try:
        # Check MongoDB
        mongo_client.admin.command('ping')
        mongo_status = "healthy"
    except:
        mongo_status = "unhealthy"
    
    return {
        "status": "healthy" if (redis_status == "healthy" and mongo_status == "healthy") else "degraded",
        "redis": redis_status,
        "mongodb": mongo_status,
        "timestamp": datetime.now().isoformat()
    }


@app.post("/extract", response_model=JobResponse)
async def extract_content(request: ExtractRequest):
    """
    Create an extraction job
    
    Returns job_id immediately. Use /extract/status/{job_id} to check status
    and /extract/result/{job_id} to get results when completed.
    """
    # Generate unique job ID
    job_id = str(uuid.uuid4())
    
    print(f"\n📥 New extraction request")
    print(f"   Job ID: {job_id}")
    print(f"   URL: {request.url}")
    print(f"   Selector: {request.selector}")
    
    # Store initial status in Redis
    update_redis_status(job_id, {
        "status": "processing",
        "url": str(request.url),
        "selector": request.selector,
        "progress": 0,
        "pages_extracted": 0,
        "message": "Job created, extraction starting...",
        "created_at": datetime.now().isoformat()
    })
    
    # Start background extraction task
    asyncio.create_task(process_extraction(job_id, request))
    
    print(f"✅ Job created: {job_id}")
    
    return JobResponse(
        job_id=job_id,
        status="processing",
        message="Extraction job created. Poll /extract/status/{job_id} for updates."
    )


@app.get("/extract/status/{job_id}", response_model=StatusResponse)
async def get_status(job_id: str):
    """
    Get the status of an extraction job
    
    Poll this endpoint to check if extraction is complete.
    Returns immediately with current status (no large data).
    """
    # Read from Redis (fast, small data)
    job_data = redis_client.get(f"job:{job_id}")
    
    if not job_data:
        raise HTTPException(
            status_code=404,
            detail="Job not found or expired. Jobs expire after 1 hour."
        )
    
    data = json.loads(job_data)
    
    return StatusResponse(
        job_id=job_id,
        status=data["status"],
        pages_extracted=data.get("pages_extracted"),
        total_characters=data.get("total_characters"),
        progress=data.get("progress"),
        completed_at=data.get("completed_at"),
        error=data.get("error"),
        message=data.get("message")
    )


@app.delete("/extract/{job_id}")
async def cancel_extraction(job_id: str):
    """
    Cancel an extraction job
    
    Marks the job for cancellation. The extraction process will check
    for this flag and stop gracefully.
    """
    # Check if job exists in Redis
    job_data = redis_client.get(f"job:{job_id}")
    
    if not job_data:
        raise HTTPException(
            status_code=404,
            detail="Job not found or expired"
        )
    
    data = json.loads(job_data)
    
    # Only allow cancellation if job is still processing
    if data.get("status") not in ["processing", "pending"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job with status '{data.get('status')}'. Only processing or pending jobs can be cancelled."
        )
    
    # Mark job for cancellation
    cancellation_flags[job_id] = True
    
    # Update Redis status immediately
    update_redis_status(job_id, {
        **data,
        "status": "cancelled",
        "message": "Cancellation requested",
        "cancelled_at": datetime.now().isoformat()
    })
    
    print(f"🛑 Cancellation requested for job: {job_id}")
    
    return {
        "job_id": job_id,
        "status": "cancelled",
        "message": "Cancellation requested. The extraction will stop at the next check point."
    }


@app.get("/extract/result/{job_id}", response_model=ResultResponse)
async def get_result(job_id: str):
    """
    Get the complete extraction result
    
    Only works when job status is "completed".
    Fetches full content from MongoDB Atlas.
    """
    # First check status from Redis (fast)
    status_data = redis_client.get(f"job:{job_id}")
    
    if not status_data:
        raise HTTPException(
            status_code=404,
            detail="Job not found or expired"
        )
    
    status = json.loads(status_data)
    
    if status["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Job status is '{status['status']}', not completed. Current status: {status.get('message', 'processing')}"
        )
    
    # Fetch full content from MongoDB Atlas
    extraction = db.extractions.find_one({"job_id": job_id})
    
    if not extraction:
        raise HTTPException(
            status_code=404,
            detail="Extraction result not found in database"
        )
    
    # Convert MongoDB document to response
    return ResultResponse(
        job_id=job_id,
        url=extraction["url"],
        selector=extraction.get("selector"),
        pages_extracted=extraction["pages_extracted"],
        total_characters=extraction["total_characters"],
        total_links=extraction["total_links"],
        content=extraction["content"],
        links=extraction["links"],
        created_at=extraction["created_at"].isoformat(),
        completed_at=extraction["completed_at"].isoformat()
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
