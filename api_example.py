#!/usr/bin/env python3
"""
Example usage of the HTML Extractor API
"""

import requests
import json

API_BASE_URL = "http://localhost:8000"

def extract_single_url():
    """Example: Extract content from a single URL"""
    response = requests.post(
        f"{API_BASE_URL}/extract",
        json={
            "url": "https://example.com/faculty",
            "selector": ".content .title,.content .meta",
            "include_links": True,
            "use_js": True,
            "wait_time": 5.0,
            "save_to_file": False
        }
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Successfully extracted {data['pages_extracted']} page(s)")
        print(f"📊 Total characters: {data['total_characters']}")
        print(f"\n📄 Content preview (first 500 chars):")
        print(data['content'][:500])
        if data.get('links'):
            print(f"\n🔗 Found {len(data['links'])} links")
    else:
        print(f"❌ Error: {response.status_code}")
        print(response.json())


def extract_batch():
    """Example: Extract content from multiple URLs"""
    response = requests.post(
        f"{API_BASE_URL}/extract/batch",
        json={
            "items": [
                {
                    "url": "https://example.com/faculty1",
                    "selector": ".content"
                },
                {
                    "url": "https://example.com/faculty2",
                    "selector": "main"
                }
            ],
            "include_links": True,
            "use_js": True,
            "wait_time": 5.0,
            "save_to_file": False
        }
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Processed {data['total_items']} items")
        print(f"✅ Successful: {data['successful']}")
        print(f"❌ Failed: {data['failed']}")
        
        for result in data['results']:
            if result['success']:
                print(f"\n📄 {result['url']}: {result['pages_extracted']} pages, {result['total_characters']} chars")
            else:
                print(f"\n❌ {result['url']}: {result.get('error', 'Unknown error')}")
    else:
        print(f"❌ Error: {response.status_code}")
        print(response.json())


def check_health():
    """Example: Check API health"""
    response = requests.get(f"{API_BASE_URL}/health")
    if response.status_code == 200:
        data = response.json()
        print(f"✅ API Status: {data['status']}")
        print(f"🕐 Timestamp: {data['timestamp']}")
    else:
        print(f"❌ API is not responding")


if __name__ == "__main__":
    print("HTML Extractor API Examples\n")
    
    # Check if API is running
    try:
        check_health()
        print("\n" + "="*50 + "\n")
        
        # Uncomment to test single extraction
        # extract_single_url()
        
        # Uncomment to test batch extraction
        # extract_batch()
        
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to API. Make sure the server is running:")
        print("   python api.py")

