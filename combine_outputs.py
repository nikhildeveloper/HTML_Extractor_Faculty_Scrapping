#!/usr/bin/env python3
"""
Combine all extracted text files into one combined file.
Reads all .txt files from the content/ folder and combines them.
"""

import os
from pathlib import Path
from datetime import datetime

# Script directory
SCRIPT_DIR = Path(__file__).parent
CONTENT_DIR = SCRIPT_DIR / "content"
OUTPUT_FILE = SCRIPT_DIR / "combine.txt"


def combine_all_text_files():
    """Combine all .txt files from content/ folder into combine.txt"""
    
    if not CONTENT_DIR.exists():
        print(f"❌ Content directory not found: {CONTENT_DIR}")
        return False
    
    # Find all .txt files
    txt_files = sorted(CONTENT_DIR.glob("*.txt"))
    
    if not txt_files:
        print(f"❌ No .txt files found in: {CONTENT_DIR}")
        return False
    
    print(f"\n{'='*70}")
    print(f"📚 COMBINING TEXT FILES")
    print(f"{'='*70}")
    print(f"Found {len(txt_files)} text file(s) to combine\n")
    
    combined_lines = []
    total_files = 0
    total_size = 0
    
    for idx, txt_file in enumerate(txt_files, 1):
        try:
            print(f"[{idx}/{len(txt_files)}] Processing: {txt_file.name}")
            
            with open(txt_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            
            if not content:
                print(f"  ⚠️  Empty file, skipping")
                continue
            
            file_size = len(content)
            total_size += file_size
            
            # Extract URL from first line (format: URL on first line)
            lines = content.split('\n')
            url = lines[0] if lines else txt_file.stem
            
            # Add separator and file header
            combined_lines.append("=" * 80)
            combined_lines.append(f"FILE {idx}: {txt_file.name}")
            combined_lines.append(f"SOURCE URL: {url}")
            combined_lines.append(f"FILE SIZE: {file_size:,} characters")
            combined_lines.append("=" * 80)
            combined_lines.append("")
            
            # Add file content
            combined_lines.append(content)
            combined_lines.append("")
            combined_lines.append("")
            
            total_files += 1
            print(f"  ✅ Added {file_size:,} characters")
        
        except Exception as e:
            print(f"  ❌ Error reading {txt_file.name}: {e}")
            continue
    
    if not combined_lines:
        print(f"\n❌ No content to combine")
        return False
    
    # Write combined file
    try:
        print(f"\n💾 Writing combined file...")
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            # Write header
            f.write("=" * 80 + "\n")
            f.write("COMBINED EXTRACTION RESULTS\n")
            f.write("=" * 80 + "\n")
            f.write(f"Combined Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total Files Combined: {total_files}\n")
            f.write(f"Total Size: {total_size:,} characters\n")
            f.write("=" * 80 + "\n\n")
            
            # Write all content
            f.write('\n'.join(combined_lines))
        
        output_size = OUTPUT_FILE.stat().st_size / 1024  # KB
        
        print(f"\n{'='*70}")
        print(f"✅ COMBINATION COMPLETE")
        print(f"{'='*70}")
        print(f"📊 Statistics:")
        print(f"   Files processed: {total_files}")
        print(f"   Total size: {total_size:,} characters")
        print(f"   Output file: {OUTPUT_FILE}")
        print(f"   Output size: {output_size:.2f} KB")
        print(f"{'='*70}\n")
        
        return True
    
    except Exception as e:
        print(f"\n❌ Error writing combined file: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    combine_all_text_files()


