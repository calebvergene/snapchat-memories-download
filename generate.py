import json
import sys
import calendar
from collections import defaultdict, OrderedDict
from datetime import datetime
from pathlib import Path
import urllib.request
import urllib.error
import time
import zipfile
import io


def load_memories(json_path: Path):
    """Load and normalize memories from Snapchat export JSON."""
    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    items = data.get("Saved Media", [])
    print(f"Found {len(items)} items in 'Saved Media'")
    normalized = []

    for idx, item in enumerate(items):
        date_str = item.get("Date") or item.get("date")
        media_type = item.get("Media Type") or item.get("media_type") or ""
        location = item.get("Location") or item.get("location") or ""
        
        # Get the media URL
        media_download_url = (
            item.get("Media Download Url")
            or item.get("Media Download URL")
            or item.get("media_download_url")
        )
        wrapper_link = item.get("Download Link") or item.get("download_link")
        download_link = media_download_url or wrapper_link

        if not date_str or not download_link:
            if idx < 5:
                print(f"  Item {idx}: Skipping - no date or URL")
            continue

        # Parse date
        dt = None
        for fmt in ["%Y-%m-%d %H:%M:%S %Z", "%Y-%m-%d %H:%M:%S", "%B %d, %Y"]:
            try:
                dt = datetime.strptime(date_str.replace(" UTC", ""), fmt.replace(" %Z", ""))
                break
            except ValueError:
                pass
        
        if not dt:
            if idx < 5:
                print(f"  Item {idx}: Skipping - couldn't parse date: '{date_str}'")
            continue

        normalized.append({
            "datetime": dt,
            "date_str": date_str,
            "media_type": media_type,
            "location": location,
            "url": download_link,
        })

    return normalized


def download_media_files(items, output_dir: Path):
    """Download all media files and return list with local paths."""
    media_dir = output_dir / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\nDownloading {len(items)} media files to {media_dir}...")
    print("(This may take a while - Snapchat servers can be slow)\n")
    downloaded = []
    failed = []
    start_time = time.time()
    
    for idx, item in enumerate(items):
        url = item["url"]
        dt = item["datetime"]
        media_type = item["media_type"].lower()
        
        # Create filename: YYYYMMDD_HHMMSS_index.ext
        timestamp = dt.strftime("%Y%m%d_%H%M%S")
        
        # Determine extension
        if "video" in media_type:
            ext = "mp4"
        elif "image" in media_type or "photo" in media_type:
            ext = "jpg"
        else:
            # Try from URL
            url_lower = url.lower()
            if ".mp4" in url_lower:
                ext = "mp4"
            elif ".mov" in url_lower:
                ext = "mov"
            elif ".jpg" in url_lower or ".jpeg" in url_lower:
                ext = "jpg"
            elif ".png" in url_lower:
                ext = "png"
            else:
                ext = "jpg"  # default
        
        filename = f"{timestamp}_{idx:04d}.{ext}"
        local_path = media_dir / filename
        relative_path = f"media/{filename}"
        
        # Download
        try:
            file_start = time.time()
            print(f"  [{idx+1}/{len(items)}] {filename}...", end=" ", flush=True)
            
            # Add timeout to avoid hanging on slow downloads
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as response:
                data = response.read()
                content_type = response.headers.get('content-type', '').lower()
            
            # Check if it's a ZIP file
            is_zip = (
                'zip' in content_type or 
                data[:4] == b'PK\x03\x04'  # ZIP magic number
            )
            
            if is_zip:
                # Extract the main media file from ZIP
                try:
                    with zipfile.ZipFile(io.BytesIO(data)) as zf:
                        # Look for file with '-main.' in the name
                        main_file = None
                        for name in zf.namelist():
                            if '-main.' in name:
                                main_file = name
                                break
                        
                        # If no -main, find any media file that's not overlay
                        if not main_file:
                            for name in zf.namelist():
                                if ('-overlay' not in name and 
                                    'overlay' not in name.lower() and
                                    any(name.lower().endswith(e) for e in ['.mp4', '.mov', '.jpg', '.jpeg', '.png', '.heic'])):
                                    main_file = name
                                    break
                        
                        if main_file:
                            # Extract and save the main file
                            data = zf.read(main_file)
                            local_path.write_bytes(data)
                            file_size = len(data) / 1024 / 1024  # MB
                            file_time = time.time() - file_start
                            print(f"✓ (ZIP: {file_size:.1f}MB in {file_time:.1f}s)")
                        else:
                            print(f"✗ No media file found in ZIP")
                            failed.append(item)
                            continue
                except zipfile.BadZipFile:
                    print(f"✗ Invalid ZIP file")
                    failed.append(item)
                    continue
            else:
                # Regular file, save directly
                local_path.write_bytes(data)
                file_size = len(data) / 1024 / 1024  # MB
                file_time = time.time() - file_start
                print(f"✓ ({file_size:.1f}MB in {file_time:.1f}s)")
            
            # Add local path to item
            item_copy = item.copy()
            item_copy["local_path"] = relative_path
            downloaded.append(item_copy)
            
            # Reduced rate limiting since we have timeout now
            if (idx + 1) % 20 == 0:
                elapsed = time.time() - start_time
                rate = (idx + 1) / elapsed * 60
                print(f"    Progress: {idx+1}/{len(items)} downloaded ({rate:.1f} files/min)")
                time.sleep(0.3)
                
        except urllib.error.URLError as e:
            print(f"✗ Network error: {str(e)[:40]}")
            failed.append(item)
        except TimeoutError:
            print(f"✗ Timeout (>30s)")
            failed.append(item)
        except Exception as e:
            print(f"✗ {str(e)[:50]}")
            failed.append(item)
    
    total_time = time.time() - start_time
    print(f"\n✓ Downloaded: {len(downloaded)} files in {total_time/60:.1f} minutes")
    if failed:
        print(f"✗ Failed: {len(failed)} files")
    
    return downloaded


def group_by_year_month(items):
    """Group items by year and month."""
    grouped = defaultdict(lambda: defaultdict(list))

    for item in items:
        dt = item["datetime"]
        grouped[dt.year][dt.month].append(item)

    # Sort years and months (newest first)
    ordered = OrderedDict()
    for year in sorted(grouped.keys(), reverse=True):
        months = grouped[year]
        ordered_months = OrderedDict()
        for month in sorted(months.keys(), reverse=True):
            # Sort items in month by datetime (newest first)
            ordered_months[month] = sorted(
                months[month], key=lambda x: x["datetime"], reverse=True
            )
        ordered[year] = ordered_months

    return ordered


def build_html(grouped):
    """Generate simple offline HTML gallery."""
    
    # Calculate stats
    total_items = sum(len(items) for year in grouped.values() for items in year.values())
    total_years = len(grouped)
    total_months = sum(len(months) for months in grouped.values())
    
    html = f"""<!DOCTYPE html>
<html lang='en'>
<head>
  <meta charset='UTF-8'>
  <meta name='viewport' content='width=device-width, initial-scale=1.0'>
  <title>Snapchat Memories</title>
  <link rel='preconnect' href='https://fonts.googleapis.com'>
  <link rel='preconnect' href='https://fonts.gstatic.com' crossorigin>
  <link href='https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700&display=swap' rel='stylesheet'>
  <style>
    * {{ box-sizing: border-box; }}
    
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
      background: #ffffff;
      color: #1a1a1a;
    }}
    
    .page {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 32px 20px 64px;
    }}
    
    header {{
      margin-bottom: 32px;
      text-align: center;
    }}
    
    h1 {{
      font-size: 2.5rem;
      margin: 0 0 8px;
      font-weight: 700;
      font-family: 'Manrope', sans-serif;
    }}
    
    .chip {{
      display: inline-block;
      padding: 4px 12px;
      background: #f0f0f0;
      border-radius: 12px;
      font-size: 0.8rem;
      margin: 8px 0;
    }}
    
    .subtitle {{
      color: #666;
      font-size: 1rem;
      margin: 16px 0;
      line-height: 1.5;
    }}
    
    .stats {{
      display: flex;
      gap: 12px;
      justify-content: center;
      margin: 16px 0;
      flex-wrap: wrap;
    }}
    
    .stat {{
      padding: 8px 16px;
      background: #f8f9fa;
      border-radius: 20px;
      font-size: 0.9rem;
      border: 1px solid #e0e0e0;
    }}
    
    .year-group {{
      margin-bottom: 32px;
    }}
    
    .year-header {{
      font-size: 1.8rem;
      font-weight: 700;
      margin-bottom: 16px;
      padding-bottom: 12px;
      border-bottom: 2px solid #e0e0e0;
    }}
    
    .year-summary {{
      font-size: 0.9rem;
      color: #666;
      font-weight: 400;
      margin-top: 4px;
    }}
    
    .month {{
      margin-bottom: 16px;
      border: 1px solid #e0e0e0;
      border-radius: 12px;
      overflow: hidden;
    }}
    
    .month-header {{
      padding: 16px 20px;
      background: #f8f9fa;
      cursor: pointer;
      display: flex;
      justify-content: space-between;
      align-items: center;
      user-select: none;
    }}
    
    .month-header:hover {{
      background: #f0f0f0;
    }}
    
    .month-title {{
      font-size: 1.1rem;
      font-weight: 600;
    }}
    
    .month-count {{
      font-size: 0.85rem;
      color: #666;
      margin-top: 2px;
    }}
    
    .month-badges {{
      display: flex;
      gap: 8px;
      align-items: center;
    }}
    
    .badge {{
      padding: 4px 10px;
      background: white;
      border: 1px solid #e0e0e0;
      border-radius: 12px;
      font-size: 0.75rem;
      color: #666;
    }}
    
    .chevron {{
      margin-left: 8px;
      transition: transform 0.2s;
    }}
    
    .month.open .chevron {{
      transform: rotate(90deg);
    }}
    
    .month-content {{
      max-height: 0;
      overflow: hidden;
      transition: max-height 0.3s ease;
      background: #fafafa;
    }}
    
    .month.open .month-content {{
      max-height: 10000px;
    }}
    
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
      gap: 14px;
      padding: 20px;
    }}
    
    .card {{
      background: white;
      border: 1px solid #e0e0e0;
      border-radius: 8px;
      overflow: hidden;
      box-shadow: 0 2px 4px rgba(0,0,0,0.06);
    }}
    
    .media {{
      width: 100%;
      aspect-ratio: 9/16;
      object-fit: cover;
      background: #f0f0f0;
      display: block;
    }}
    
    video.media {{
      object-fit: cover;
      background: #000;
    }}
    
    .card-footer {{
      padding: 10px;
      text-align: center;
      font-size: 0.8rem;
      color: #666;
    }}
    
    .type-badge {{
      position: absolute;
      top: 8px;
      left: 8px;
      padding: 4px 10px;
      background: rgba(255,255,255,0.95);
      border-radius: 12px;
      font-size: 0.7rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    
    .media-wrapper {{
      position: relative;
    }}
    
    @media (max-width: 768px) {{
      .grid {{
        grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
        gap: 12px;
        padding: 12px;
      }}
      
      h1 {{
        font-size: 2rem;
      }}
    }}
  </style>
</head>
<body>
  <div class='page'>
    <header>
      <h1>📸 Snapchat Archives</h1>
      <div class='chip'>Memories Saved Offline</div>
      <p class='subtitle'>
        Don't pay for a Snapchat subscription! All memories are stored locally, so you're memories won't expire.
      </p>
      <div class='stats'>
        <div class='stat'>{total_items} memories</div>
        <div class='stat'>{total_years} years</div>
        <div class='stat'>{total_months} months</div>
      </div>
    </header>
    
    <main>
"""
    
    # Build year sections
    for year, months in grouped.items():
        year_count = sum(len(items) for items in months.values())
        html += f"""
      <div class='year-group'>
        <div class='year-header'>
          {year}
          <div class='year-summary'>{year_count} snap{'s' if year_count != 1 else ''} · {len(months)} month{'s' if len(months) != 1 else ''}</div>
        </div>
"""
        
        # Build month sections
        for month_num, items in months.items():
            month_name = calendar.month_name[month_num]
            count = len(items)
            vid_count = sum(1 for i in items if "video" in i["media_type"].lower())
            img_count = count - vid_count
            
            html += f"""
        <div class='month'>
          <div class='month-header'>
            <div>
              <div class='month-title'>{month_name}</div>
              <div class='month-count'>{count} item{'s' if count != 1 else ''}</div>
            </div>
            <div class='month-badges'>
              <span class='badge'>{vid_count} video{'s' if vid_count != 1 else ''}</span>
              <span class='badge'>{img_count} photo{'s' if img_count != 1 else ''}</span>
              <span class='chevron'>▶</span>
            </div>
          </div>
          <div class='month-content'>
            <div class='grid'>
"""
            
            # Build media cards
            for item in items:
                local_path = item["local_path"]
                date_label = item["datetime"].strftime("%B %d, %Y")
                is_video = "video" in item["media_type"].lower()
                
                if is_video:
                    media_html = f"<video class='media' controls preload='metadata' src='{local_path}'></video>"
                    type_badge = "<div class='type-badge'>▶ Video</div>"
                else:
                    media_html = f"<img class='media' src='{local_path}' alt='{date_label}' loading='lazy'>"
                    type_badge = "<div class='type-badge'>📷 Photo</div>"
                
                html += f"""
              <div class='card'>
                <div class='media-wrapper'>
                  {type_badge}
                  {media_html}
                </div>
                <div class='card-footer'>{date_label}</div>
              </div>
"""
            
            html += """
            </div>
          </div>
        </div>
"""
        
        html += """
      </div>
"""
    
    html += """
    </main>
  </div>
  
  <script>
    // Accordion functionality
    document.addEventListener('DOMContentLoaded', function() {
      const months = document.querySelectorAll('.month');
      
      // Open first month by default
      if (months[0]) {
        months[0].classList.add('open');
      }
      
      months.forEach(month => {
        const header = month.querySelector('.month-header');
        header.addEventListener('click', () => {
          month.classList.toggle('open');
        });
      });
    });
  </script>
</body>
</html>
"""
    
    return html


def main():
    if len(sys.argv) > 1:
        json_path = Path(sys.argv[1])
    else:
        json_path = Path("memories_history.json")
    
    if not json_path.exists():
        print(f"Error: Could not find JSON file at {json_path}")
        sys.exit(1)

    # Determine output directory (same as JSON file)
    output_dir = json_path.parent
    
    print(f"Loading memories from {json_path}...")
    memories = load_memories(json_path)
    print(f"Loaded {len(memories)} valid memories")
    
    if not memories:
        print("\nNo memories found. Please check your JSON file.")
        sys.exit(1)

    # Download all media files
    downloaded_memories = download_media_files(memories, output_dir)
    
    if not downloaded_memories:
        print("\nNo files were downloaded successfully.")
        sys.exit(1)
    
    # Group by year/month
    grouped = group_by_year_month(downloaded_memories)
    
    # Generate HTML
    print("\nGenerating HTML gallery...")
    html = build_html(grouped)
    
    output_path = output_dir / "memories_gallery.html"
    output_path.write_text(html, encoding="utf-8")
    
    print(f"\n✓ Complete!")
    print(f"  Downloaded: {len(downloaded_memories)} files")
    print(f"  Gallery: {output_path.resolve()}")
    print(f"\nOpen {output_path.name} in your browser to view your memories!")


if __name__ == "__main__":
    main()