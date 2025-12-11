#!/usr/bin/env python3
"""
HTML Content Extractor
Extracts complete HTML text content from URLs, handles dynamic JS loading,
and saves to text files. Supports single pages and multi-page extraction.
"""

import os
import sys
import re
import time
import json
import pandas as pd
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse, urljoin, urlunparse
from typing import List, Dict, Optional
import asyncio
from bs4 import BeautifulSoup
import requests
import urllib3
from playwright.async_api import async_playwright

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Add parent directory to path to use existing venv modules if needed
sys.path.insert(0, str(Path(__file__).parent.parent))

# Script directory
SCRIPT_DIR = Path(__file__).parent
CONTENT_DIR = SCRIPT_DIR / "content"


def sanitize_filename(url, max_length=200):
    """Convert URL to a safe filename"""
    parsed = urlparse(url)
    # Create filename from URL components
    domain = parsed.netloc.replace('.', '_').replace(':', '_')
    path = parsed.path.strip('/').replace('/', '_').replace('\\', '_')
    
    # Combine domain and path
    if path:
        filename = f"{domain}_{path}"
    else:
        filename = domain
    
    # Remove invalid characters
    filename = re.sub(r'[<>:"|?*]', '', filename)
    
    # Truncate if too long
    if len(filename) > max_length:
        filename = filename[:max_length]
    
    # Add timestamp to make it unique
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    return f"{filename}_{timestamp}"


def extract_links_from_html(html, base_url, selector=None):
    """Extract all links (URL and link text) from HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Apply selector if provided
    if selector:
        try:
            target_element = soup.select_one(selector)
            if target_element:
                soup = BeautifulSoup(str(target_element), 'html.parser')
            else:
                print(f"  ⚠️  Selector '{selector}' not found, extracting from entire page")
        except Exception as e:
            print(f"  ⚠️  Error applying selector '{selector}': {e}, extracting from entire page")
    
    links = []
    seen_links = set()
    
    # Find all anchor tags with href
    for a_tag in soup.find_all('a', href=True):
        href = a_tag.get('href', '').strip()
        link_text = a_tag.get_text(strip=True)
        
        if not href:
            continue
        
        # Convert relative URLs to absolute
        full_url = urljoin(base_url, href)
        
        # Skip javascript:, mailto:, tel: links
        if href.startswith(('javascript:', 'mailto:', 'tel:', '#')):
            continue
        
        # Create link entry
        link_entry = {
            'url': full_url,
            'text': link_text if link_text else href,
            'href': href
        }
        
        # Avoid duplicates (same URL)
        if full_url not in seen_links:
            links.append(link_entry)
            seen_links.add(full_url)
    
    return links


def extract_text_with_inline_links(html, selector=None, include_links=True, base_url=None):
    """Extract text content with links shown inline in format 'Link Text — URL'"""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Apply CSS selector if provided
    if selector:
        try:
            print(f"  🎯 Applying CSS selector: '{selector}'")
            target_elements = soup.select(selector)
            if target_elements:
                print(f"  ✅ Found {len(target_elements)} element(s) matching selector")
                # Create a new soup with just the selected elements
                selected_html = ''.join(str(elem) for elem in target_elements)
                soup = BeautifulSoup(selected_html, 'html.parser')
            else:
                print(f"  ⚠️  No elements found matching selector '{selector}', extracting from entire page")
        except Exception as e:
            print(f"  ⚠️  Error applying selector '{selector}': {e}, extracting from entire page")
    
    # Remove script and style elements
    for tag in soup(['script', 'style', 'meta', 'link', 'noscript']):
        tag.decompose()
    
    # Process links inline - replace anchor tags with "Link Text — URL" format
    if include_links and base_url:
        for a_tag in soup.find_all('a', href=True):
            href = a_tag.get('href', '').strip()
            link_text = a_tag.get_text(strip=True)
            
            # Skip javascript, mailto, tel links
            if not href or href.startswith(('javascript:', 'mailto:', 'tel:')):
                # For anchor links (#), just keep the text
                if href.startswith('#'):
                    a_tag.replace_with(link_text if link_text else '')
                else:
                    a_tag.replace_with(link_text if link_text else '')
                continue
            
            # Convert relative URLs to absolute
            full_url = urljoin(base_url, href)
            
            # Replace the anchor tag with "Link Text — URL" format
            if link_text:
                replacement_text = f"{link_text} — {full_url}"
            else:
                replacement_text = full_url
            
            a_tag.replace_with(replacement_text)
    
    # Get all text content (links are now inline)
    text = soup.get_text(separator='\n', strip=True)
    
    # Clean up excessive whitespace but preserve structure
    lines = []
    for line in text.split('\n'):
        line = line.strip()
        if line:  # Only keep non-empty lines
            lines.append(line)
    
    text_content = '\n'.join(lines)
    
    # Also collect all links separately for reference (if needed)
    links = []
    if include_links and base_url:
        # Re-parse to get links (for separate listing if needed)
        temp_soup = BeautifulSoup(html, 'html.parser')
        if selector:
            target_elements = temp_soup.select(selector)
            if target_elements:
                selected_html = ''.join(str(elem) for elem in target_elements)
                temp_soup = BeautifulSoup(selected_html, 'html.parser')
        
        for a_tag in temp_soup.find_all('a', href=True):
            href = a_tag.get('href', '').strip()
            link_text = a_tag.get_text(strip=True)
            
            if not href or href.startswith(('javascript:', 'mailto:', 'tel:', '#')):
                continue
            
            full_url = urljoin(base_url, href)
            links.append({
                'url': full_url,
                'text': link_text if link_text else href,
                'href': href
            })
        
        # Remove duplicates
        seen = set()
        unique_links = []
        for link in links:
            if link['url'] not in seen:
                seen.add(link['url'])
                unique_links.append(link)
        links = unique_links
    
    return {
        'text': text_content,
        'links': links
    }


def load_page_with_playwright(url, wait_time=5):
    """Load page with Playwright to handle dynamic JS content"""
    html = ""
    
    async def load_page():
        nonlocal html
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                print(f"  🔧 Loading with Playwright (JS rendering enabled)...")
                await page.goto(url, timeout=60000, wait_until='domcontentloaded')
                await page.wait_for_load_state("load", timeout=60000)
                
                # Wait for dynamic content
                await asyncio.sleep(wait_time)
                await page.wait_for_timeout(3000)  # Additional wait
                
                # Scroll to load lazy-loaded content
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(2)
                
                html = await page.content()
            except Exception as e:
                print(f"  ⚠️  Error loading with Playwright: {e}")
                html = None
            finally:
                await browser.close()
    
    asyncio.run(load_page())
    return html


def load_page_with_requests(url):
    """Load page with simple HTTP request (no JS)"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    try:
        print(f"  📄 Loading with HTTP request...")
        response = requests.get(url, headers=headers, timeout=30, verify=False)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"  ⚠️  Error loading with HTTP: {e}")
        return None


def extract_single_page(url, use_js=True, wait_time=5, selector=None, include_links=True):
    """Extract content from a single page"""
    print(f"\n📄 Extracting content from: {url}")
    
    # Load HTML
    if use_js:
        html = load_page_with_playwright(url, wait_time)
    else:
        html = load_page_with_requests(url)
    
    if not html:
        print(f"  ❌ Failed to load page")
        return None
    
    print(f"  ✅ Page loaded ({len(html)} characters)")
    
    # Extract text content with inline links
    extracted = extract_text_with_inline_links(html, selector=selector, include_links=include_links, base_url=url)
    
    text_content = extracted['text']
    links = extracted['links']
    
    print(f"  ✅ Text extracted ({len(text_content)} characters)")
    if include_links:
        print(f"  🔗 Links found: {len(links)}")
    
    return {
        'text': text_content,
        'links': links,
        'url': url
    }


def find_pagination_links(html, base_url):
    """Find ALL pagination links (next page, page numbers, etc.)"""
    soup = BeautifulSoup(html, 'html.parser')
    
    pagination_links = set()
    base_parsed = urlparse(base_url)
    base_path = base_parsed.path
    base_netloc = base_parsed.netloc
    
    # Strategy 1: Find pagination containers (more specific)
    pagination_patterns = [
        {'class': lambda x: x and ('pagination' in x.lower() or 'pager' in x.lower())},
        {'class': lambda x: x and 'page' in x.lower() and ('number' in x.lower() or 'item' in x.lower())},
        {'id': lambda x: x and ('pagination' in x.lower() or 'pager' in x.lower())},
        {'role': lambda x: x and 'navigation' in x.lower()},
    ]
    
    for pattern in pagination_patterns:
        containers = soup.find_all(['div', 'nav', 'ul', 'ol'], pattern)
        for container in containers:
            links = container.find_all('a', href=True)
            for link in links:
                href = link.get('href', '').strip()
                if not href:
                    continue
                
                full_url = urljoin(base_url, href)
                parsed = urlparse(full_url)
                
                # Must be same domain
                if parsed.netloc != base_netloc:
                    continue
                
                # Check if URL looks like pagination
                if re.search(r'[?&](page|p)=\d+', full_url, re.I) or re.search(r'/page[_-]?\d+', full_url, re.I):
                    pagination_links.add(full_url)
                # Or if link text suggests pagination
                else:
                    text = link.get_text(strip=True).lower()
                    # Check for page numbers, next, last, etc.
                    if (any(keyword in text for keyword in ['next', 'page', '>', '»', 'last']) or 
                        re.search(r'^\d+$', text.strip())):
                        pagination_links.add(full_url)
    
    # Strategy 2: Find ALL links with page parameters in the same path (most comprehensive)
    all_links = soup.find_all('a', href=True)
    for link in all_links:
        href = link.get('href', '').strip()
        if not href:
            continue
        
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)
        
        # Must be same domain
        if parsed.netloc != base_netloc:
            continue
        
        # Check if it's a pagination URL (has page parameter)
        if re.search(r'[?&](page|p)=\d+', full_url, re.I):
            # Same base path (or very similar - allow for slight variations)
            if (parsed.path == base_path or 
                parsed.path.startswith(base_path) or 
                base_path.startswith(parsed.path)):
                pagination_links.add(full_url)
        # Also check for /page/ or /page- patterns in path
        elif re.search(r'/page[_-]?\d+', parsed.path, re.I):
            if base_path in parsed.path or parsed.path in base_path:
                pagination_links.add(full_url)
    
    return list(pagination_links)


def detect_pagination_from_urls(urls):
    """Group URLs that appear to be from same pagination sequence"""
    # Simple heuristic: URLs with page numbers
    paginated = []
    for url in urls:
        if re.search(r'[?&](page|p)=?\d+', url, re.I) or re.search(r'/page[_-]?\d+', url, re.I):
            paginated.append(url)
    return paginated


def find_next_page_button(soup):
    """Find the 'Next Page' button/link in the HTML"""
    # PRIORITY 1: Check for buttons with data-action="next"
    data_action_next = soup.find_all(['a', 'button'], attrs={'data-action': lambda x: x and 'next' in str(x).lower()})
    for btn in data_action_next:
        # Check if it's not disabled
        if btn.get('disabled') or 'disabled' in str(btn.get('class', [])).lower():
            continue
        return btn
    
    # PRIORITY 2: Check for links inside elements with "next" class
    next_containers = soup.find_all(['li', 'div', 'span'], class_=lambda x: x and 'next' in str(x).lower())
    for container in next_containers:
        link = container.find('a', href=True)
        if link:
            # Check if it's not disabled
            if link.get('disabled') or 'disabled' in str(link.get('class', [])).lower():
                continue
            return link
    
    # PRIORITY 3: Check for FacetWP pagination (data-page attribute with 'next' class or text)
    facetwp_next = soup.find('a', class_=lambda x: x and 'facetwp-page' in str(x) and 'next' in str(x))
    if facetwp_next:
        # Check if it's not disabled
        classes = str(facetwp_next.get('class', [])).lower()
        if 'disabled' not in classes:
            # Check if there's actually a next page (data-page should exist)
            data_page = facetwp_next.get('data-page')
            if data_page:
                return facetwp_next
    
    # PRIORITY 4: Check for any element with data-page attribute that could be next
    data_page_buttons = soup.find_all(['a', 'button'], attrs={'data-page': True})
    for btn in data_page_buttons:
        classes = str(btn.get('class', [])).lower()
        text = btn.get_text(strip=True).lower()
        if 'next' in classes or ('next' in text and ('»' in btn.get_text() or '>' in btn.get_text())):
            if 'disabled' not in classes:
                return btn
    
    # PRIORITY 5: Look for common "Next" button patterns (existing logic)
    next_patterns = [
        {'text': lambda x: x and 'next' in x.lower() and 'page' in x.lower()},
        {'text': lambda x: x and ('next' in x.lower() or '»' in x or '>' in x) and x.strip()},
        {'class': lambda x: x and ('next' in x.lower() or 'pager-next' in x.lower())},
        {'aria-label': lambda x: x and 'next' in x.lower()},
    ]
    
    for pattern in next_patterns:
        buttons = soup.find_all(['a', 'button'], pattern)
        for btn in buttons:
            # Check if it's not disabled
            if btn.get('disabled') or 'disabled' in str(btn.get('class', [])).lower():
                continue
            return btn
    
    return None


def extract_with_js_pagination(start_url, wait_time=5, selector=None, include_links=True, job_id=None, has_pagination=False, max_pages=1):
    """Extract content by clicking 'Next Page' buttons (for JS-based pagination)"""
    print(f"\n📚 Starting JavaScript-based pagination extraction")
    if has_pagination:
        print(f"   Will extract up to {max_pages} page(s) as specified by user\n")
    else:
        print(f"   Will click 'Next Page' buttons until all content is loaded\n")
    
    all_text_parts = []
    page_count = 0
    # Use user-specified max_pages if pagination is enabled, otherwise use safety limit
    max_pages_limit = max_pages if has_pagination else 1000
    
    # Check cancellation and update progress via Redis if job_id is provided
    cancellation_check = None
    update_progress = None
    if job_id:
        try:
            import redis
            import json
            import os
            redis_host = os.getenv("REDIS_HOST", "localhost")
            redis_port = int(os.getenv("REDIS_PORT", 6379))
            redis_db = int(os.getenv("REDIS_DB", 0))
            redis_client = redis.Redis(host=redis_host, port=redis_port, db=redis_db, decode_responses=True)
            
            def check_cancelled():
                try:
                    job_data = redis_client.get(f"job:{job_id}")
                    if job_data:
                        data = json.loads(job_data)
                        return data.get("status") == "cancelled"
                    return False
                except:
                    return False
            
            def update_redis_progress(pages_count):
                """Update Redis with current page count"""
                try:
                    job_data = redis_client.get(f"job:{job_id}")
                    if job_data:
                        data = json.loads(job_data)
                        data["pages_extracted"] = pages_count
                        data["message"] = f"Extracting page {pages_count}..."
                        redis_client.setex(
                            f"job:{job_id}",
                            3600,  # 1 hour TTL
                            json.dumps(data)
                        )
                except:
                    pass  # Silently fail if Redis update fails
            
            cancellation_check = check_cancelled
            update_progress = update_redis_progress
        except ImportError:
            # Redis not available, cancellation won't work
            pass
    
    async def extract_pages():
        nonlocal page_count, all_text_parts
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            try:
                # Load initial page
                print(f"\n{'='*70}")
                print(f"📄 Loading initial page: {start_url}")
                print(f"{'='*70}")
                
                await page.goto(start_url, timeout=60000, wait_until='domcontentloaded')
                await page.wait_for_load_state("load", timeout=60000)
                await asyncio.sleep(wait_time)
                await page.wait_for_timeout(3000)
                
                # Scroll to load any lazy content
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(2)
                
                consecutive_no_next = 0
                previous_content_hash = None
                consecutive_same_content = 0
                
                while page_count < max_pages_limit:
                    # Check for cancellation
                    if cancellation_check and cancellation_check():
                        print(f"\n🛑 Extraction cancelled by user")
                        break
                    
                    page_count += 1
                    
                    # Check if we've reached the user-specified max pages limit
                    if has_pagination and page_count > max_pages_limit:
                        print(f"\n✅ Reached user-specified page limit ({max_pages_limit} pages) - stopping")
                        break
                    
                    print(f"\n{'='*70}")
                    print(f"📄 Page {page_count}" + (f" of {max_pages_limit}" if has_pagination else ""))
                    print(f"{'='*70}")
                    
                    # Get current page HTML
                    html = await page.content()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Extract content from current page
                    extracted = extract_text_with_inline_links(html, selector=selector, include_links=include_links, base_url=start_url)
                    
                    if extracted and extracted.get('text'):
                        # Check if content has changed (hash check with more characters for better detection)
                        # Use more characters for better detection (first 2000 chars or full text if shorter)
                        text_to_hash = extracted['text'][:2000] if len(extracted['text']) > 2000 else extracted['text']
                        content_hash = hash(text_to_hash)
                        if content_hash == previous_content_hash:
                            consecutive_same_content += 1
                            if consecutive_same_content >= 2:
                                print(f"  ✅ Content unchanged after {consecutive_same_content} clicks - reached end")
                                break
                        else:
                            consecutive_same_content = 0
                            previous_content_hash = content_hash
                        
                        all_text_parts.append({
                            'url': f"{start_url} (page {page_count})",
                            'page_number': page_count,
                            'text': extracted['text'],
                            'links': extracted.get('links', [])
                        })
                        print(f"  ✅ Extracted {len(extracted['text'])} characters")
                        
                        # Update Redis with current page count
                        if update_progress:
                            update_progress(page_count)
                    else:
                        print(f"  ⚠️  No content extracted")
                    
                    # Check if we're on the last page (multiple detection methods)
                    # NOTE: We check the ORIGINAL HTML soup, NOT the extracted content,
                    # to avoid false matches from pagination text in extracted content
                    try:
                        page_of_match = None
                        
                        # Method 1: Check for "X of Y" pattern ONLY in pagination containers
                        page_info_elem = soup.find('a', attrs={'aria-current': 'page'})
                        if not page_info_elem:
                            # Also check in pagination container
                            pagination_containers = soup.find_all(['nav', 'ul', 'div'], 
                                class_=lambda x: x and 'pagination' in str(x).lower())
                            for container in pagination_containers:
                                page_info_elem = container.find('a', attrs={'aria-current': 'page'})
                                if page_info_elem:
                                    break
                        
                        if page_info_elem:
                            page_info_text = page_info_elem.get_text(strip=True)
                            # Look for pattern like "1 of 28" or "1of 28" (with or without spaces)
                            page_of_match = re.search(r'(\d+)\s*of\s*(\d+)', page_info_text, re.IGNORECASE)
                            if page_of_match:
                                current_page_num = int(page_of_match.group(1))
                                total_pages = int(page_of_match.group(2))
                                # Only stop if we're actually at the last page AND Next button is disabled/not available
                                if current_page_num >= total_pages:
                                    # Double-check: verify Next button is actually disabled/not available
                                    next_button_check = find_next_page_button(soup)
                                    if not next_button_check:
                                        print(f"  ✅ Reached last page ({current_page_num} of {total_pages}) - no Next button - stopping")
                                        break
                                    # Check if Next button is disabled
                                    is_next_disabled = (
                                        next_button_check.get('disabled') or 
                                        'disabled' in str(next_button_check.get('class', [])).lower() or
                                        (next_button_check.find_parent(['li', 'div', 'span']) and 
                                         'disabled' in str(next_button_check.find_parent(['li', 'div', 'span']).get('class', [])).lower())
                                    )
                                    if is_next_disabled:
                                        print(f"  ✅ Reached last page ({current_page_num} of {total_pages}) - Next button disabled - stopping")
                                        break
                        
                        # Method 2: Check pagination containers for "X of Y" pattern (more specific, not entire page)
                        if not page_of_match:
                            pagination_containers = soup.find_all(['nav', 'ul', 'div'], 
                                class_=lambda x: x and 'pagination' in str(x).lower())
                            for container in pagination_containers:
                                container_text = container.get_text()
                                container_match = re.search(r'(\d+)\s*of\s*(\d+)', container_text, re.IGNORECASE)
                                if container_match:
                                    current_page_num = int(container_match.group(1))
                                    total_pages = int(container_match.group(2))
                                    # Only stop if we're actually at the last page AND Next button is disabled/not available
                                    if current_page_num >= total_pages:
                                        # Double-check: verify Next button is actually disabled/not available
                                        next_button_check = find_next_page_button(soup)
                                        if not next_button_check:
                                            print(f"  ✅ Reached last page ({current_page_num} of {total_pages}) - no Next button - stopping")
                                            page_of_match = container_match  # Set for consistency
                                            break
                                        # Check if Next button is disabled
                                        is_next_disabled = (
                                            next_button_check.get('disabled') or 
                                            'disabled' in str(next_button_check.get('class', [])).lower() or
                                            (next_button_check.find_parent(['li', 'div', 'span']) and 
                                             'disabled' in str(next_button_check.find_parent(['li', 'div', 'span']).get('class', [])).lower())
                                        )
                                        if is_next_disabled:
                                            print(f"  ✅ Reached last page ({current_page_num} of {total_pages}) - Next button disabled - stopping")
                                            page_of_match = container_match  # Set for consistency
                                            break
                                # Break outer loop if we found a match and stopped
                                if container_match and current_page_num >= total_pages:
                                    break
                        
                        # Method 3: Check for FacetWP pagination (existing logic)
                        current_page_elem = soup.find('a', class_=lambda x: x and 'facetwp-page' in str(x) and 'active' in str(x))
                        if current_page_elem:
                            current_page_str = current_page_elem.get('data-page')
                            if current_page_str:
                                current_page_num = int(current_page_str)
                                # Get last page number
                                last_page_elem = soup.find('a', class_=lambda x: x and 'facetwp-page' in str(x) and 'last' in str(x))
                                if last_page_elem:
                                    last_page_str = last_page_elem.get('data-page')
                                    if last_page_str:
                                        last_page_num = int(last_page_str)
                                        if current_page_num >= last_page_num:
                                            print(f"  ✅ Reached last page ({last_page_num}) - stopping")
                                            break
                    except Exception as e:
                        pass  # If we can't determine page numbers, continue
                    
                    # Find and click "Next Page" button OR next numbered page link
                    next_button = find_next_page_button(soup)
                    
                    # If no "Next" button, try to find next numbered page link
                    if not next_button:
                        # Look for pagination with numbered links
                        pagination_containers = soup.find_all(['nav', 'ul', 'div'], 
                            class_=lambda x: x and 'pagination' in str(x).lower())
                        
                        current_page_num = None
                        next_page_link = None
                        
                        for container in pagination_containers:
                            # Find current active page
                            active_link = container.find('a', attrs={'aria-current': 'page'})
                            if not active_link:
                                active_link = container.find('a', class_=lambda x: x and 'active' in str(x).lower())
                            
                            if active_link:
                                active_text = active_link.get_text(strip=True)
                                if re.search(r'^\d+$', active_text):
                                    current_page_num = int(active_text)
                            
                            # Find all numbered links
                            all_links = container.find_all('a')
                            for link in all_links:
                                link_text = link.get_text(strip=True)
                                if re.search(r'^\d+$', link_text):
                                    link_num = int(link_text)
                                    # If we found current page, next link is the one after it
                                    if current_page_num and link_num == current_page_num + 1:
                                        next_page_link = link
                                        break
                                    # Or if no current page found, find the first non-active numbered link > 1
                                    elif not current_page_num and link_num > 1:
                                        if not link.get('aria-current') and 'active' not in str(link.get('class', [])).lower():
                                            next_page_link = link
                                            break
                            
                            if next_page_link:
                                break
                        
                        if next_page_link:
                            next_button = next_page_link
                    
                    if not next_button:
                        # Before giving up, check if there are numbered page links that might indicate more pages
                        pagination_containers = soup.find_all(['nav', 'ul', 'div'], 
                            class_=lambda x: x and 'pagination' in str(x).lower())
                        
                        current_page_num = None
                        max_page_num = None
                        
                        for container in pagination_containers:
                            # Find current active page
                            active_link = container.find('a', attrs={'aria-current': 'page'})
                            if not active_link:
                                active_link = container.find('a', class_=lambda x: x and 'active' in str(x).lower())
                            
                            if active_link:
                                active_text = active_link.get_text(strip=True)
                                if re.search(r'^\d+$', active_text):
                                    current_page_num = int(active_text)
                            
                            # Find all numbered links to get max page
                            all_links = container.find_all('a')
                            for link in all_links:
                                link_text = link.get_text(strip=True)
                                if re.search(r'^\d+$', link_text):
                                    link_num = int(link_text)
                                    if max_page_num is None or link_num > max_page_num:
                                        max_page_num = link_num
                            
                            # Also check for "X of Y" pattern
                            container_text = container.get_text()
                            page_of_match = re.search(r'(\d+)\s*of\s*(\d+)', container_text, re.IGNORECASE)
                            if page_of_match:
                                total_pages = int(page_of_match.group(2))
                                if max_page_num is None or total_pages > max_page_num:
                                    max_page_num = total_pages
                        
                        # If we found a max page number and we're not there yet, try to click it
                        if current_page_num and max_page_num and current_page_num < max_page_num:
                            # Try to find and click the next numbered page
                            for container in pagination_containers:
                                all_links = container.find_all('a')
                                for link in all_links:
                                    link_text = link.get_text(strip=True)
                                    if re.search(r'^\d+$', link_text):
                                        link_num = int(link_text)
                                        if link_num == current_page_num + 1:
                                            next_button = link
                                            print(f"  🔍 Found next numbered page link: {link_num}")
                                            break
                                if next_button:
                                    break
                        
                        if not next_button:
                            print(f"  ✅ No 'Next Page' button or next page link found - reached end")
                            break
                    
                    # First, check if we have "X of Y" information to determine if we should continue
                    current_page_from_pattern = None
                    total_pages_from_pattern = None
                    try:
                        # Check for "X of Y" pattern in pagination
                        page_info_elem = soup.find('a', attrs={'aria-current': 'page'})
                        if not page_info_elem:
                            pagination_containers = soup.find_all(['nav', 'ul', 'div'], 
                                class_=lambda x: x and 'pagination' in str(x).lower())
                            for container in pagination_containers:
                                page_info_elem = container.find('a', attrs={'aria-current': 'page'})
                                if page_info_elem:
                                    break
                        
                        if page_info_elem:
                            page_info_text = page_info_elem.get_text(strip=True)
                            page_of_match = re.search(r'(\d+)\s*of\s*(\d+)', page_info_text, re.IGNORECASE)
                            if page_of_match:
                                current_page_from_pattern = int(page_of_match.group(1))
                                total_pages_from_pattern = int(page_of_match.group(2))
                    except:
                        pass
                    
                    # Check if button is disabled (multiple ways)
                    is_disabled = False
                    # Check disabled attribute
                    if next_button.get('disabled') or next_button.get('disabled') == '':
                        is_disabled = True
                    # Check disabled in class
                    if 'disabled' in str(next_button.get('class', [])).lower():
                        is_disabled = True
                    # Check if parent has disabled class
                    parent = next_button.find_parent(['li', 'div', 'span'])
                    if parent and 'disabled' in str(parent.get('class', [])).lower():
                        is_disabled = True
                    
                    # If we have "X of Y" pattern info, use it to determine if we should continue
                    if is_disabled and current_page_from_pattern and total_pages_from_pattern:
                        if current_page_from_pattern < total_pages_from_pattern:
                            # We know there are more pages, so ignore the disabled state and continue
                            is_disabled = False
                            print(f"  🔄 Next button appears disabled, but 'X of Y' shows {current_page_from_pattern} of {total_pages_from_pattern} - continuing")
                    
                    # Before stopping due to disabled button, check if there are numbered page links available
                    if is_disabled:
                        # Check if there are numbered page links that indicate more pages
                        pagination_containers = soup.find_all(['nav', 'ul', 'div'], 
                            class_=lambda x: x and 'pagination' in str(x).lower())
                        
                        current_page_num = None
                        max_page_num = None
                        next_page_link = None
                        
                        for container in pagination_containers:
                            # Find current active page
                            active_link = container.find('a', attrs={'aria-current': 'page'})
                            if not active_link:
                                active_link = container.find('a', class_=lambda x: x and 'active' in str(x).lower())
                            
                            if active_link:
                                active_text = active_link.get_text(strip=True)
                                if re.search(r'^\d+$', active_text):
                                    current_page_num = int(active_text)
                            
                            # Find all numbered links
                            all_links = container.find_all('a')
                            for link in all_links:
                                link_text = link.get_text(strip=True)
                                if re.search(r'^\d+$', link_text):
                                    link_num = int(link_text)
                                    if max_page_num is None or link_num > max_page_num:
                                        max_page_num = link_num
                                    # If we found current page, next link is the one after it
                                    if current_page_num and link_num == current_page_num + 1:
                                        next_page_link = link
                            
                            # Also check for "X of Y" pattern
                            container_text = container.get_text()
                            page_of_match = re.search(r'(\d+)\s*of\s*(\d+)', container_text, re.IGNORECASE)
                            if page_of_match:
                                total_pages = int(page_of_match.group(2))
                                if max_page_num is None or total_pages > max_page_num:
                                    max_page_num = total_pages
                        
                        # If there's a next numbered page link available, use it instead
                        if next_page_link and current_page_num and max_page_num and current_page_num < max_page_num:
                            next_button = next_page_link
                            is_disabled = False
                            print(f"  🔄 Next button disabled, but found numbered page link {current_page_num + 1} - continuing")
                        else:
                            print(f"  ✅ 'Next Page' button is disabled - reached end")
                            break
                    
                    # For FacetWP, check if Next button data-page indicates we're at the end
                    if next_button.get('data-page'):
                        try:
                            next_data_page = int(next_button.get('data-page'))
                            current_page_elem = soup.find('a', class_=lambda x: x and 'facetwp-page' in str(x) and 'active' in str(x))
                            if current_page_elem:
                                current_data_page = current_page_elem.get('data-page')
                                if current_data_page and int(current_data_page) >= next_data_page:
                                    print(f"  ✅ Reached last page - Next button would go to same or previous page")
                                    break
                        except:
                            pass
                    
                    # Get button selector
                    button_text = next_button.get_text(strip=True)
                    button_href = next_button.get('href', '')
                    
                    # Try to find the button using Playwright
                    try:
                        # Try multiple strategies to find and click the button
                        clicked = False
                        
                        # Strategy 1: Click by text content
                        try:
                            await page.click(f"text='{button_text}'", timeout=5000)
                            clicked = True
                            print(f"  🔘 Clicked 'Next Page' button (by text: '{button_text}')")
                        except:
                            pass
                        
                        # Strategy 2: Click by href if it's a link
                        if not clicked and button_href:
                            try:
                                await page.click(f"a[href*='{button_href}']", timeout=5000)
                                clicked = True
                                print(f"  🔘 Clicked 'Next Page' button (by href)")
                            except:
                                pass
                        
                        # Strategy 3: Click by common selectors (including FacetWP)
                        if not clicked:
                            selectors = [
                                # FacetWP specific selectors (HIGH PRIORITY)
                                ".facetwp-page.next",
                                "a.facetwp-page.next",
                                "[data-page].facetwp-page.next",
                                # Generic selectors
                                "a:has-text('Next')",
                                "button:has-text('Next')",
                                ".pager-next a",
                                ".pagination .next",
                                "[aria-label*='next' i]",
                                "[aria-label*='Next' i]"
                            ]
                            for sel in selectors:
                                try:
                                    await page.click(sel, timeout=3000)
                                    clicked = True
                                    print(f"  🔘 Clicked 'Next Page' button (by selector: {sel})")
                                    break
                                except:
                                    continue
                        
                        # Strategy 4: Click numbered page link by ID, data-action, parent class, or text
                        if not clicked and next_button:
                            try:
                                # Try clicking by data-action attribute
                                data_action = next_button.get('data-action')
                                if data_action:
                                    try:
                                        await page.click(f"[data-action='{data_action}']", timeout=3000)
                                        clicked = True
                                        print(f"  🔘 Clicked page link (by data-action: {data_action})")
                                    except:
                                        pass
                                
                                # Try clicking by parent class (e.g., .next a)
                                if not clicked:
                                    try:
                                        await page.click(".next a", timeout=3000)
                                        clicked = True
                                        print(f"  🔘 Clicked page link (by parent class: .next a)")
                                    except:
                                        pass
                                
                                # Try clicking by ID if it exists (e.g., pagination-2)
                                if not clicked:
                                    button_id = next_button.get('id', '')
                                    if button_id:
                                        try:
                                            await page.click(f"#{button_id}", timeout=3000)
                                            clicked = True
                                            print(f"  🔘 Clicked page link (by ID: {button_id})")
                                        except:
                                            pass
                                
                                # Try clicking by text (page number or "Next")
                                if not clicked:
                                    button_text = next_button.get_text(strip=True)
                                    if re.search(r'^\d+$', button_text) or 'next' in button_text.lower():
                                        # Try multiple ways to click numbered link
                                        try:
                                            await page.click(f"text='{button_text}'", timeout=3000)
                                            clicked = True
                                            print(f"  🔘 Clicked page link (by text: '{button_text}')")
                                        except:
                                            # Try with pagination container context
                                            try:
                                                await page.click(f".pagination a:has-text('{button_text}')", timeout=3000)
                                                clicked = True
                                                print(f"  🔘 Clicked page link (by text in pagination: '{button_text}')")
                                            except:
                                                pass
                            except Exception as e:
                                pass
                        
                        # Strategy 4: Click by data-page attribute if FacetWP
                        if not clicked:
                            try:
                                # Find the next page number from current active page
                                current_page_elem = await page.query_selector(".facetwp-page.active")
                                if current_page_elem:
                                    current_page_num = await current_page_elem.get_attribute("data-page")
                                    if current_page_num:
                                        next_page_num = int(current_page_num) + 1
                                        next_selector = f".facetwp-page[data-page='{next_page_num}']"
                                        await page.click(next_selector, timeout=3000)
                                        clicked = True
                                        print(f"  🔘 Clicked 'Next Page' button (by data-page: {next_page_num})")
                            except Exception as e:
                                pass
                        
                        # Strategy 5: Try clicking by data-page of next button directly
                        if not clicked and next_button:
                            try:
                                data_page = next_button.get('data-page')
                                if data_page:
                                    data_page_selector = f".facetwp-page[data-page='{data_page}'].next"
                                    await page.click(data_page_selector, timeout=3000)
                                    clicked = True
                                    print(f"  🔘 Clicked 'Next Page' button (by data-page attribute: {data_page})")
                            except Exception as e:
                                pass
                        
                        if not clicked:
                            print(f"  ⚠️  Could not click 'Next Page' button - stopping")
                            break
                        
                        # Wait for FacetWP AJAX to complete
                        try:
                            # Wait for FacetWP loading indicator to disappear
                            await page.wait_for_function(
                                "document.querySelector('.facetwp-loading') === null",
                                timeout=10000
                            )
                        except:
                            pass  # If no loading indicator, just continue with normal wait
                        
                        # Wait for new content to load
                        await asyncio.sleep(wait_time)
                        await page.wait_for_timeout(3000)
                        
                        # Additional wait for FacetWP to update DOM
                        try:
                            await page.wait_for_function(
                                "document.querySelector('.facetwp-template') !== null",
                                timeout=5000
                            )
                        except:
                            pass
                        
                        # Wait a bit more for any animations/transitions
                        await asyncio.sleep(1)
                        
                        # Scroll to trigger lazy loading
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await asyncio.sleep(2)
                        
                        # Reset counters since we successfully clicked
                        consecutive_no_next = 0
                        consecutive_same_content = 0  # Reset since we navigated
                        
                    except Exception as e:
                        print(f"  ⚠️  Error clicking next button: {e}")
                        consecutive_no_next += 1
                        if consecutive_no_next >= 3:
                            print(f"  ⚠️  Multiple failures, stopping")
                            break
                        await asyncio.sleep(2)
                
            finally:
                await browser.close()
        
        return all_text_parts
    
    # Run the async extraction
    return asyncio.run(extract_pages())


def extract_all_pages_recursive(start_url, use_js=True, wait_time=5, selector=None, include_links=True, job_id=None, has_pagination=False, max_pages=1):
    """Extract content from all pages by recursively following pagination links"""
    print(f"\n📚 Starting automatic pagination extraction from: {start_url}")
    if has_pagination:
        print(f"   Will extract up to {max_pages} page(s) as specified by user\n")
    else:
        print(f"   Will automatically follow all pagination links until the end\n")
    
    # Check cancellation and update progress via Redis if job_id is provided
    cancellation_check = None
    update_progress = None
    if job_id:
        try:
            import redis
            import json
            import os
            redis_host = os.getenv("REDIS_HOST", "localhost")
            redis_port = int(os.getenv("REDIS_PORT", 6379))
            redis_db = int(os.getenv("REDIS_DB", 0))
            redis_client = redis.Redis(host=redis_host, port=redis_port, db=redis_db, decode_responses=True)
            
            def check_cancelled():
                try:
                    job_data = redis_client.get(f"job:{job_id}")
                    if job_data:
                        data = json.loads(job_data)
                        return data.get("status") == "cancelled"
                    return False
                except:
                    return False
            
            def update_redis_progress(pages_count):
                """Update Redis with current page count"""
                try:
                    job_data = redis_client.get(f"job:{job_id}")
                    if job_data:
                        data = json.loads(job_data)
                        data["pages_extracted"] = pages_count
                        data["message"] = f"Extracting page {pages_count}..."
                        redis_client.setex(
                            f"job:{job_id}",
                            3600,  # 1 hour TTL
                            json.dumps(data)
                        )
                except:
                    pass  # Silently fail if Redis update fails
            
            cancellation_check = check_cancelled
            update_progress = update_redis_progress
        except ImportError:
            # Redis not available, cancellation won't work
            pass
    
    # First, check if this is JS-based pagination by loading the page
    if use_js:
        # Load page to check pagination type
        html = load_page_with_playwright(start_url, wait_time)
        if html:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Check for FacetWP pagination (data-page attributes indicate JS pagination)
            facetwp_pagination = soup.find('div', class_=lambda x: x and 'facetwp' in str(x).lower())
            has_data_page = soup.find_all(['a', 'button'], attrs={'data-page': True})
            
            next_button = find_next_page_button(soup)
            
            # If we find FacetWP or data-page attributes, it's definitely JS pagination
            if facetwp_pagination or (has_data_page and next_button):
                print(f"  🔍 Detected JavaScript-based pagination (FacetWP/data-page detected)")
                print(f"  🔄 Switching to button-clicking mode...\n")
                return extract_with_js_pagination(start_url, wait_time, selector, include_links, job_id, has_pagination, max_pages)
            
            # Check for numbered pagination links with href="#" (no "Next" button needed)
            pagination_containers = soup.find_all(['nav', 'ul', 'div'], 
                class_=lambda x: x and 'pagination' in str(x).lower())
            
            has_numbered_pagination_links = False
            has_next_prev_buttons = False
            if pagination_containers:
                for container in pagination_containers:
                    # Look for numbered links with href="#"
                    numbered_links = container.find_all('a', href=lambda x: x in ['#', 'javascript:void(0)'])
                    for link in numbered_links:
                        link_text = link.get_text(strip=True)
                        # Check if it's a page number (just digits)
                        if re.search(r'^\d+$', link_text):
                            has_numbered_pagination_links = True
                            break
                    
                    # Also check for Next/Prev buttons with href="#" and data-action
                    next_prev_buttons = container.find_all('a', href=lambda x: x in ['#', 'javascript:void(0)'])
                    for btn in next_prev_buttons:
                        if btn.get('data-action') or ('next' in btn.get_text(strip=True).lower() or 'prev' in btn.get_text(strip=True).lower()):
                            has_next_prev_buttons = True
                            break
                    
                    if has_numbered_pagination_links or has_next_prev_buttons:
                        break
            
            # If we find numbered pagination with href="#" OR Next/Prev buttons with href="#", it's JS pagination
            if has_numbered_pagination_links or has_next_prev_buttons:
                print(f"  🔍 Detected JavaScript-based pagination (pagination buttons with href='#')")
                print(f"  🔄 Switching to button-clicking mode...\n")
                return extract_with_js_pagination(start_url, wait_time, selector, include_links, job_id, has_pagination, max_pages)
            
            # Check if "Next Page" button exists and points to same URL
            if next_button:
                next_href = next_button.get('href', '')
                # If no href or href is empty/just #, it's likely JS pagination
                if not next_href or next_href in ['', '#', 'javascript:void(0)']:
                    print(f"  🔍 Detected JavaScript-based pagination (Next button has no href)")
                    print(f"  🔄 Switching to button-clicking mode...\n")
                    return extract_with_js_pagination(start_url, wait_time, selector, include_links, job_id, has_pagination, max_pages)
                
                if next_href:
                    next_url = urljoin(start_url, next_href)
                    # If next button points to same URL, it's JS-based pagination
                    if urlparse(next_url).path == urlparse(start_url).path and urlparse(next_url).query == urlparse(start_url).query:
                        print(f"  🔍 Detected JavaScript-based pagination (Next button has same URL)")
                        print(f"  🔄 Switching to button-clicking mode...\n")
                        return extract_with_js_pagination(start_url, wait_time, selector, include_links, job_id, has_pagination, max_pages)
    
    # Regular URL-based pagination
    all_text_parts = []
    visited_urls = set()
    urls_to_visit = [start_url]
    page_count = 0
    # Use user-specified max_pages if pagination is enabled, otherwise use safety limit
    max_iterations = max_pages if has_pagination else 1000  # Safety limit to prevent infinite loops
    
    iteration = 0
    while urls_to_visit and iteration < max_iterations:
        # Check for cancellation
        if cancellation_check and cancellation_check():
            print(f"\n🛑 Extraction cancelled by user")
            return all_text_parts
        
        iteration += 1
        url = urls_to_visit.pop(0)
        
        # Skip if already visited
        if url in visited_urls:
            continue
        
        visited_urls.add(url)
        page_count += 1
        
        # Check if we've reached the user-specified max pages limit
        if has_pagination and page_count > max_iterations:
            print(f"\n✅ Reached user-specified page limit ({max_iterations} pages) - stopping")
            break
        
        print(f"\n{'='*70}")
        print(f"📄 Page {page_count}" + (f" of {max_iterations}" if has_pagination else "") + f": {url}")
        print(f"{'='*70}")
        
        # Load and extract content
        if use_js:
            html = load_page_with_playwright(url, wait_time)
        else:
            html = load_page_with_requests(url)
        
        if not html:
            print(f"  ⚠️  Failed to load page, skipping...")
            continue
        
        # Extract content
        extracted = extract_text_with_inline_links(html, selector=selector, include_links=include_links, base_url=url)
        
        if extracted and extracted.get('text'):
            all_text_parts.append({
                'url': url,
                'page_number': page_count,
                'text': extracted['text'],
                'links': extracted.get('links', [])
            })
            
            # Update Redis with current page count
            if update_progress:
                update_progress(page_count)
            
            # Find pagination links on this page
            pagination_links = find_pagination_links(html, url)
            
            # Filter out links that point to the same URL (JS-based pagination)
            valid_pagination_links = []
            for pag_url in pagination_links:
                parsed_pag = urlparse(pag_url)
                parsed_current = urlparse(url)
                # Only add if URL is actually different
                if parsed_pag.path != parsed_current.path or parsed_pag.query != parsed_current.query:
                    valid_pagination_links.append(pag_url)
            
            # Add new pagination links to queue (if not already visited)
            new_links = 0
            for pag_url in valid_pagination_links:
                if pag_url not in visited_urls and pag_url not in urls_to_visit:
                    urls_to_visit.append(pag_url)
                    new_links += 1
            
            if new_links > 0:
                print(f"  🔍 Found {new_links} new pagination link(s) to process")
            else:
                print(f"  ✅ No new pagination links found")
            
            # Add delay between pages
            if urls_to_visit:
                print(f"  ⏱️  Waiting 2 seconds before next page...")
                time.sleep(2)
        else:
            print(f"  ⚠️  No content extracted, skipping...")
    
    if iteration >= max_iterations:
        print(f"\n⚠️  Reached maximum iteration limit ({max_iterations}). Stopping extraction.")
    
    print(f"\n✅ Finished extracting {page_count} page(s)")
    return all_text_parts


def format_links_section(links):
    """Format links section for output (optional - links are now inline)"""
    if not links:
        return ""
    
    # Links are now inline, but we can optionally show a summary
    output = []
    output.append(f"\n{'─'*80}")
    output.append(f"LINKS SUMMARY ({len(links)} unique links found - all shown inline above)")
    output.append(f"{'─'*80}\n")
    
    return '\n'.join(output)


def save_content_to_file(content_data, base_url, selector=None):
    """Save extracted content to a text file"""
    # Create content directory if it doesn't exist
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Generate filename
    filename_base = sanitize_filename(base_url)
    output_file = CONTENT_DIR / f"{filename_base}.txt"
    
    # Handle multiple pages vs single page
    if isinstance(content_data, list) and len(content_data) > 1:
        # Multiple pages
        print(f"\n💾 Saving {len(content_data)} pages to: {output_file.name}")
        
        with open(output_file, 'w', encoding='utf-8') as f:
            # Write base URL at the top
            f.write(f"{base_url}\n\n")
            
            for page_data in content_data:
                # Write text content (links are already inline)
                f.write(page_data.get('text', ''))
                f.write(f"\n\n")
    else:
        # Single page
        if isinstance(content_data, list):
            text_content = content_data[0].get('text', '')
            links = content_data[0].get('links', [])
            url = content_data[0].get('url', base_url)
        elif isinstance(content_data, dict):
            text_content = content_data.get('text', '')
            links = content_data.get('links', [])
            url = content_data.get('url', base_url)
        else:
            text_content = content_data
            links = []
            url = base_url
        
        print(f"\n💾 Saving content to: {output_file.name}")
        
        with open(output_file, 'w', encoding='utf-8') as f:
            # Write URL at the top (as per user's desired format)
            f.write(f"{url}\n\n")
            
            # Write text content (links are already inline)
            f.write(text_content)
            f.write(f"\n")
    
    file_size = output_file.stat().st_size / 1024  # KB
    print(f"  ✅ File saved: {output_file}")
    print(f"  📊 File size: {file_size:.2f} KB")
    
    return output_file


def process_batch(url_selector_pairs: List[Dict[str, str]], use_js: bool = True, 
                  wait_time: float = 5, include_links: bool = True):
    """
    Process multiple URLs with their respective CSS selectors.
    
    Args:
        url_selector_pairs: List of dicts with 'url' and 'selector' keys.
                           Example: [{'url': 'https://example.com', 'selector': 'main'}, ...]
        use_js: Whether to use JavaScript rendering
        wait_time: Wait time for JS content
        include_links: Whether to include links in output
    """
    print(f"\n{'='*70}")
    print(f"📚 BATCH PROCESSING MODE")
    print(f"{'='*70}")
    print(f"Total URLs to process: {len(url_selector_pairs)}\n")
    
    results = []
    
    for idx, pair in enumerate(url_selector_pairs, 1):
        url = pair.get('url', '').strip()
        selector = pair.get('selector', '').strip() or None
        
        if not url:
            print(f"\n⚠️  [{idx}/{len(url_selector_pairs)}] Skipping empty URL")
            continue
        
        # Validate URL
        parsed = urlparse(url)
        if not parsed.scheme:
            url = 'https://' + url
        
        print(f"\n{'='*70}")
        print(f"[{idx}/{len(url_selector_pairs)}] Processing: {url}")
        if selector:
            print(f"CSS Selector: {selector}")
        print(f"{'='*70}")
        
        try:
            # Use existing extraction logic
            content_data = extract_all_pages_recursive(
                url, use_js, wait_time, selector, include_links
            )
            
            if content_data:
                # Save to file (one file per URL)
                output_file = save_content_to_file(content_data, url, selector)
                results.append({
                    'url': url,
                    'selector': selector,
                    'status': 'success',
                    'output_file': str(output_file),
                    'pages_extracted': len(content_data)
                })
                print(f"✅ [{idx}/{len(url_selector_pairs)}] Completed: {output_file.name}")
            else:
                results.append({
                    'url': url,
                    'selector': selector,
                    'status': 'failed',
                    'error': 'No content extracted'
                })
                print(f"❌ [{idx}/{len(url_selector_pairs)}] Failed: No content extracted")
        
        except Exception as e:
            error_msg = str(e)
            results.append({
                'url': url,
                'selector': selector,
                'status': 'error',
                'error': error_msg
            })
            print(f"❌ [{idx}/{len(url_selector_pairs)}] Error: {error_msg}")
            continue
        
        # Add delay between URLs to be polite
        if idx < len(url_selector_pairs):
            print(f"\n⏱️  Waiting 3 seconds before next URL...")
            time.sleep(3)
    
    # Print summary
    print(f"\n{'='*70}")
    print(f"📊 BATCH PROCESSING SUMMARY")
    print(f"{'='*70}")
    successful = sum(1 for r in results if r['status'] == 'success')
    failed = len(results) - successful
    print(f"Total URLs processed: {len(results)}")
    print(f"✅ Successful: {successful}")
    print(f"❌ Failed: {failed}")
    print(f"{'='*70}\n")
    
    return results


def load_batch_from_json(json_file: Path) -> List[Dict[str, str]]:
    """Load URL/selector pairs from a JSON file."""
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Support multiple formats
        if isinstance(data, list):
            # Format: [{'url': '...', 'selector': '...'}, ...]
            return data
        elif isinstance(data, dict) and 'urls' in data:
            # Format: {'urls': [{'url': '...', 'selector': '...'}, ...]}
            return data['urls']
        else:
            raise ValueError("Invalid JSON format")
    
    except Exception as e:
        print(f"❌ Error loading JSON file: {e}")
        return []


def load_batch_from_text(text_file: Path) -> List[Dict[str, str]]:
    """Load URL/selector pairs from a text file (one per line, format: URL|SELECTOR)."""
    pairs = []
    try:
        with open(text_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith('#'):  # Skip empty lines and comments
                    continue
                
                # Format: URL|SELECTOR or just URL
                if '|' in line:
                    url, selector = line.split('|', 1)
                    pairs.append({'url': url.strip(), 'selector': selector.strip()})
                else:
                    pairs.append({'url': line.strip(), 'selector': ''})
    
    except Exception as e:
        print(f"❌ Error loading text file: {e}")
        return []
    
    return pairs


def load_batch_from_excel(excel_file: Path) -> List[Dict[str, str]]:
    """Load URL/selector pairs from an Excel file with 'links' and 'selectors' columns."""
    pairs = []
    try:
        # Read Excel file
        df = pd.read_excel(excel_file, engine='openpyxl')
        
        # Handle different column name variations
        url_col = None
        selector_col = None
        
        # Find URL column (case-insensitive, handle variations)
        for col in df.columns:
            col_lower = str(col).lower().strip()
            if col_lower in ['links', 'link', 'url', 'urls', 'website']:
                url_col = col
                break
        
        # Find selector column (case-insensitive, handle variations)
        for col in df.columns:
            col_lower = str(col).lower().strip()
            if col_lower in ['selectors', 'selector', 'css', 'css_selector', 'css-selector']:
                selector_col = col
                break
        
        if url_col is None:
            print(f"❌ Error: Could not find 'links' column in Excel file.")
            print(f"   Available columns: {list(df.columns)}")
            return []
        
        # Process each row
        for idx, row in df.iterrows():
            url = str(row[url_col]).strip() if pd.notna(row[url_col]) else ''
            
            # Skip empty URLs
            if not url or url.lower() == 'nan':
                continue
            
            # Get selector (optional column)
            if selector_col and selector_col in df.columns:
                selector = str(row[selector_col]).strip() if pd.notna(row[selector_col]) else ''
                if selector.lower() == 'nan':
                    selector = ''
            else:
                selector = ''
            
            pairs.append({'url': url, 'selector': selector})
        
        print(f"✅ Loaded {len(pairs)} URL(s) from Excel file")
        if selector_col:
            print(f"   URL column: '{url_col}', Selector column: '{selector_col}'")
        else:
            print(f"   URL column: '{url_col}', Selector column: (none - will extract entire page)")
    
    except Exception as e:
        print(f"❌ Error loading Excel file: {e}")
        import traceback
        traceback.print_exc()
        return []
    
    return pairs


def main():
    """Main function"""
    print(f"\n{'='*70}")
    print(f"🌐 HTML CONTENT EXTRACTOR")
    print(f"{'='*70}\n")
    
    # Ask for batch mode or single URL mode
    print(f"{'─'*70}")
    mode_choice = input("Processing mode:\n  1. Single URL\n  2. Batch mode (multiple URLs with selectors)\nEnter choice (1 or 2, default: 1): ").strip()
    batch_mode = mode_choice == '2'
    
    # Ask about including links (applies to all)
    print(f"\n{'─'*70}")
    links_choice = input("Include links in output? (y/n, default: y): ").strip().lower()
    include_links = not links_choice.startswith('n')
    
    # Ask about JS loading (applies to all)
    print(f"\n{'─'*70}")
    js_choice = input("Does the page require JavaScript/动态内容? (y/n, default: y): ").strip().lower()
    use_js = not js_choice.startswith('n')
    
    wait_time = 5
    if use_js:
        wait_input = input("Wait time for JS content to load in seconds (default: 5): ").strip()
        if wait_input:
            try:
                wait_time = float(wait_input)
            except ValueError:
                print("  ⚠️  Invalid input, using default 5 seconds")
    
    if batch_mode:
        # BATCH MODE
        print(f"\n{'─'*70}")
        print("Batch mode: Provide URLs and selectors")
        print("Options:")
        print("  1. Enter JSON file path")
        print("  2. Enter text file path (format: URL|SELECTOR, one per line)")
        print("  3. Enter Excel file path (columns: 'links' and 'selectors')")
        print("  4. Enter URLs manually (one per line, format: URL|SELECTOR)")
        
        input_method = input("\nEnter choice (1, 2, 3, or 4, default: 4): ").strip()
        
        url_selector_pairs = []
        
        if input_method == '1':
            # JSON file
            json_path = input("\nEnter path to JSON file: ").strip()
            if json_path:
                json_file = Path(json_path)
                if json_file.exists():
                    url_selector_pairs = load_batch_from_json(json_file)
                else:
                    print(f"❌ File not found: {json_path}")
                    return
            else:
                print("❌ No file path provided")
                return
        
        elif input_method == '2':
            # Text file
            text_path = input("\nEnter path to text file: ").strip()
            if text_path:
                text_file = Path(text_path)
                if text_file.exists():
                    url_selector_pairs = load_batch_from_text(text_file)
                else:
                    print(f"❌ File not found: {text_path}")
                    return
            else:
                print("❌ No file path provided")
                return
        
        elif input_method == '3':
            # Excel file
            excel_path = input("\nEnter path to Excel file (or just filename if in html_extractor folder): ").strip()
            if excel_path:
                excel_file = Path(excel_path)
                # If just filename provided, check in html_extractor folder
                if not excel_file.is_absolute() and not excel_file.exists():
                    excel_file = SCRIPT_DIR / excel_path
                
                if excel_file.exists():
                    url_selector_pairs = load_batch_from_excel(excel_file)
                else:
                    print(f"❌ File not found: {excel_file}")
                    print(f"   Searched at: {excel_file.absolute()}")
                    return
            else:
                print("❌ No file path provided")
                return
        
        else:
            # Manual input
            print("\nEnter URLs with selectors (format: URL|SELECTOR)")
            print("Leave selector empty for entire page (format: URL|)")
            print("Press Enter twice when done:")
            
            while True:
                line = input().strip()
                if not line:
                    break
                
                if '|' in line:
                    url, selector = line.split('|', 1)
                    url_selector_pairs.append({'url': url.strip(), 'selector': selector.strip()})
                else:
                    url_selector_pairs.append({'url': line.strip(), 'selector': ''})
        
        if not url_selector_pairs:
            print("❌ No URLs provided")
            return
        
        # Process batch
        try:
            results = process_batch(url_selector_pairs, use_js, wait_time, include_links)
            
            # Optionally save results summary
            summary_choice = input("\nSave batch processing summary? (y/n, default: n): ").strip().lower()
            if summary_choice.startswith('y'):
                summary_file = CONTENT_DIR / f"batch_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                CONTENT_DIR.mkdir(parents=True, exist_ok=True)
                with open(summary_file, 'w', encoding='utf-8') as f:
                    json.dump(results, f, indent=2)
                print(f"✅ Summary saved: {summary_file}")
        
        except KeyboardInterrupt:
            print(f"\n\n⚠️  Batch processing interrupted by user")
        except Exception as e:
            print(f"\n❌ Error during batch processing: {e}")
            import traceback
            traceback.print_exc()
    
    else:
        # SINGLE URL MODE (existing logic)
        url = input("\nEnter the URL to extract: ").strip()
        
        if not url:
            print("❌ Error: No URL provided")
            return
        
        # Validate URL
        parsed = urlparse(url)
        if not parsed.scheme:
            url = 'https://' + url
            print(f"  ℹ️  Added https:// prefix: {url}")
        
        # Ask about CSS selector
        print(f"\n{'─'*70}")
        selector_input = input("Enter CSS selector to target specific content (e.g., 'main', '.content', '#article', or leave blank for entire page): ").strip()
        selector = selector_input if selector_input else None
        
        if selector:
            print(f"  ✅ Will extract content from: {selector}")
        else:
            print(f"  ✅ Will extract content from entire page")
        
        # Extract content - automatically detect and follow pagination
        try:
            print(f"\n{'─'*70}")
            print(f"🚀 Starting extraction...")
            print(f"   The script will automatically detect and follow pagination links")
            print(f"   until all pages are extracted.\n")
            
            # Always use recursive extraction to automatically follow pagination
            content_data = extract_all_pages_recursive(url, use_js, wait_time, selector, include_links)
            
            # Save to file
            if content_data:
                output_file = save_content_to_file(content_data, url, selector)
                print(f"\n{'='*70}")
                print(f"✅ EXTRACTION COMPLETE")
                print(f"{'='*70}")
                print(f"📁 Output file: {output_file}")
                print(f"{'='*70}\n")
            else:
                print(f"\n❌ No content extracted. Please check the URL and try again.\n")
        
        except KeyboardInterrupt:
            print(f"\n\n⚠️  Extraction interrupted by user")
        except Exception as e:
            print(f"\n❌ Error during extraction: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()

