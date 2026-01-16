#!/usr/bin/env python3
"""
Scrape yeast strain data from Beer Maverick and generate seed JSON file.

Beer Maverick has 430+ yeast strains with detailed fermentation data.

Usage:
    python scripts/scrape_beermaverick.py

Output:
    backend/seed/yeast_strains.json
"""

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Missing dependencies. Install with:")
    print("  pip install requests beautifulsoup4")
    sys.exit(1)


# Output path
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
OUTPUT_FILE = PROJECT_ROOT / "backend" / "seed" / "yeast_strains.json"

# Base URL
BASE_URL = "https://beermaverick.com"
YEAST_LIST_URL = f"{BASE_URL}/yeasts/"

# Rate limiting
REQUEST_DELAY = 0.5  # seconds between requests
MAX_WORKERS = 5  # concurrent requests


def fahrenheit_to_celsius(f: float) -> float:
    """Convert Fahrenheit to Celsius, rounded to 1 decimal."""
    return round((f - 32) * 5 / 9, 1)


def parse_temp_range(temp_str: str) -> tuple[float | None, float | None]:
    """Parse temperature range like '68-73° F' and convert to Celsius."""
    if not temp_str:
        return None, None

    # Match patterns like "68-73° F" or "68-73°F (20-23°C)"
    # First try to extract Celsius directly if present (case-insensitive)
    c_match = re.search(r'\((\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*°?\s*C\)', temp_str, re.IGNORECASE)
    if c_match:
        return float(c_match.group(1)), float(c_match.group(2))

    # Otherwise parse Fahrenheit and convert (case-insensitive)
    f_match = re.search(r'(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*°?\s*F', temp_str, re.IGNORECASE)
    if f_match:
        low_f = float(f_match.group(1))
        high_f = float(f_match.group(2))
        return fahrenheit_to_celsius(low_f), fahrenheit_to_celsius(high_f)

    # Single temp (case-insensitive)
    single_match = re.search(r'(\d+(?:\.\d+)?)\s*°?\s*F', temp_str, re.IGNORECASE)
    if single_match:
        temp_c = fahrenheit_to_celsius(float(single_match.group(1)))
        return temp_c, temp_c

    return None, None


def parse_attenuation(att_str: str) -> tuple[float | None, float | None]:
    """Parse attenuation like '73-80%' and return low/high."""
    if not att_str:
        return None, None

    # Range like "73-80%"
    match = re.search(r'(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*%?', att_str)
    if match:
        return float(match.group(1)), float(match.group(2))

    # Single value like "75%"
    match = re.search(r'(\d+(?:\.\d+)?)\s*%', att_str)
    if match:
        val = float(match.group(1))
        return val, val

    return None, None


def parse_alcohol_tolerance(tol_str: str) -> str | None:
    """Parse alcohol tolerance like 'High%' or 'Medium'."""
    if not tol_str:
        return None

    tol_lower = tol_str.lower().strip().replace('%', '')

    if 'very high' in tol_lower:
        return 'very_high'
    elif 'high' in tol_lower:
        return 'high'
    elif 'medium' in tol_lower or 'med' in tol_lower:
        return 'medium'
    elif 'low' in tol_lower:
        return 'low'

    return tol_lower


def normalize_flocculation(flocc_str: str) -> str | None:
    """Normalize flocculation to standard values."""
    if not flocc_str:
        return None

    flocc_lower = flocc_str.lower().strip()

    if 'very high' in flocc_lower:
        return 'very_high'
    elif 'high' in flocc_lower:
        return 'high'
    elif 'medium' in flocc_lower or 'med' in flocc_lower:
        return 'medium'
    elif 'low' in flocc_lower:
        return 'low'

    return flocc_lower.replace(' ', '_')


def normalize_type(type_str: str) -> str | None:
    """Normalize yeast type."""
    if not type_str:
        return None

    type_lower = type_str.lower().strip()

    if 'kveik' in type_lower:
        return 'ale'  # Kveik is a type of ale yeast
    elif 'ale' in type_lower or 'saccharomyces' in type_lower:
        return 'ale'
    elif 'lager' in type_lower:
        return 'lager'
    elif 'wine' in type_lower:
        return 'wine'
    elif 'wild' in type_lower or 'brett' in type_lower:
        return 'wild'
    elif 'bacteria' in type_lower:
        return 'bacteria'
    elif 'hybrid' in type_lower or 'blend' in type_lower:
        return 'hybrid'

    return 'ale'  # Default to ale


def normalize_form(form_str: str) -> str | None:
    """Normalize yeast form."""
    if not form_str:
        return None

    form_lower = form_str.lower().strip()

    if 'dry' in form_lower:
        return 'dry'
    elif 'liquid' in form_lower:
        return 'liquid'
    elif 'slant' in form_lower:
        return 'slant'

    return form_lower


def extract_product_id(name: str, url: str) -> str | None:
    """Extract product ID from name or URL."""
    # Try URL first - usually has the product ID
    # e.g., wlp001-california-ale-yeast-white-labs
    url_match = re.search(r'/yeast/([a-z]{2,4}[-]?\d{2,4}[a-z]?)-', url.lower())
    if url_match:
        return url_match.group(1).upper().replace('-', '')

    # Common patterns in name
    patterns = [
        r'\b(WLP\d{3}[A-Z]?)\b',  # White Labs
        r'\b(WY\d{4}[A-Z]?)\b',   # Wyeast
        r'\b(OYL[-]?\d{3})\b',    # Omega
        r'\b([A-Z]\d{2})\b',      # Imperial (A01, B45, etc.)
        r'\b([A-Z]{1,3}[-]?\d{2,3})\b',  # Various
    ]

    for pattern in patterns:
        match = re.search(pattern, name, re.IGNORECASE)
        if match:
            return match.group(1).upper().replace('-', '')

    return None


def get_yeast_urls() -> list[tuple[str, str, str]]:
    """Get all yeast URLs from the main listing page.

    Returns list of (url, name, type) tuples.
    """
    print(f"Fetching yeast list from {YEAST_LIST_URL}...")

    response = requests.get(YEAST_LIST_URL, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, 'html.parser')

    yeasts = []

    # Find all yeast links in the tables
    for link in soup.find_all('a', href=True):
        href = link['href']
        if '/yeast/' in href and href != '/yeasts/' and not href.endswith('/yeasts/'):
            name = link.get_text(strip=True)
            if name and name != 'View all yeast':
                # Convert relative URL to absolute
                full_url = href if href.startswith('http') else f"{BASE_URL}{href}"

                # Try to get type from the next sibling cell
                yeast_type = 'Yeast'
                parent_td = link.find_parent('td')
                if parent_td:
                    next_td = parent_td.find_next_sibling('td')
                    if next_td:
                        yeast_type = next_td.get_text(strip=True) or 'Yeast'

                yeasts.append((full_url, name, yeast_type))

    # Dedupe by URL
    seen_urls = set()
    unique_yeasts = []
    for url, name, yeast_type in yeasts:
        if url not in seen_urls:
            seen_urls.add(url)
            unique_yeasts.append((url, name, yeast_type))

    print(f"Found {len(unique_yeasts)} unique yeast URLs")
    return unique_yeasts


def scrape_yeast_page(url: str, name: str, list_type: str) -> dict | None:
    """Scrape a single yeast page for detailed data."""
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # Initialize strain data
        strain = {
            "name": name,
            "producer": None,
            "product_id": None,
            "type": normalize_type(list_type),
            "form": None,
            "attenuation_low": None,
            "attenuation_high": None,
            "temp_low": None,
            "temp_high": None,
            "alcohol_tolerance": None,
            "flocculation": None,
            "description": None,
            "source": "beermaverick"
        }

        # Parse tables for data
        for table in soup.find_all('table'):
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True).lower()
                    value = cells[1].get_text(strip=True)

                    # Use startswith checks to avoid matching description text
                    if label.startswith('brand'):
                        strain['producer'] = value if value else None
                    elif label.startswith('packet'):
                        strain['form'] = normalize_form(value)
                    elif label.startswith('type'):
                        # Only override if we got more specific info
                        if value and value.lower() != 'yeast':
                            strain['type'] = normalize_type(value)
                    elif label.startswith('attenuation'):
                        low, high = parse_attenuation(value)
                        strain['attenuation_low'] = low
                        strain['attenuation_high'] = high
                    elif label.startswith('flocculation'):
                        strain['flocculation'] = normalize_flocculation(value)
                    elif label.startswith('optimal') or label.startswith('temperature'):
                        low, high = parse_temp_range(value)
                        strain['temp_low'] = low
                        strain['temp_high'] = high
                    elif label.startswith('alcohol'):
                        strain['alcohol_tolerance'] = parse_alcohol_tolerance(value)

        # Get description
        desc_header = soup.find(['h2', 'h3'], string=re.compile(r'description', re.I))
        if desc_header:
            desc_p = desc_header.find_next('p')
            if desc_p:
                strain['description'] = desc_p.get_text(strip=True)

        # Extract product ID
        strain['product_id'] = extract_product_id(name, url)

        return strain

    except Exception as e:
        print(f"  Error scraping {url}: {e}")
        return None


def scrape_all_yeasts(yeast_list: list[tuple[str, str, str]]) -> list[dict]:
    """Scrape all yeast pages with rate limiting and parallel requests."""
    strains = []
    total = len(yeast_list)

    print(f"\nScraping {total} yeast pages...")

    def scrape_with_delay(item):
        url, name, yeast_type = item
        time.sleep(REQUEST_DELAY)  # Rate limit
        return scrape_yeast_page(url, name, yeast_type)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(scrape_with_delay, item): item for item in yeast_list}

        for i, future in enumerate(as_completed(futures), 1):
            item = futures[future]
            url, name, _ = item

            try:
                strain = future.result()
                if strain:
                    strains.append(strain)
                    if i % 50 == 0 or i == total:
                        print(f"  Progress: {i}/{total} ({len(strains)} successful)")
            except Exception as e:
                print(f"  Error with {name}: {e}")

    return strains


def deduplicate_strains(strains: list[dict]) -> list[dict]:
    """Remove duplicate strains based on name + producer."""
    seen = set()
    unique = []

    for strain in strains:
        key = (strain["name"].lower(), (strain["producer"] or "").lower())
        if key not in seen:
            seen.add(key)
            unique.append(strain)

    return unique


def main():
    print("=" * 60)
    print("Beer Maverick Yeast Strain Scraper")
    print("=" * 60)

    # Get all yeast URLs
    yeast_list = get_yeast_urls()

    if not yeast_list:
        print("No yeasts found!")
        sys.exit(1)

    # Scrape all yeasts
    all_strains = scrape_all_yeasts(yeast_list)

    if not all_strains:
        print("No strains collected!")
        sys.exit(1)

    # Deduplicate
    unique_strains = deduplicate_strains(all_strains)
    print(f"\nTotal unique strains: {len(unique_strains)}")

    # Sort by producer, then name
    unique_strains.sort(key=lambda s: ((s["producer"] or "ZZZ").lower(), s["name"].lower()))

    # Build output
    output = {
        "version": "2.0",
        "last_updated": datetime.now().strftime("%Y-%m-%d"),
        "sources": ["beermaverick.com"],
        "strain_count": len(unique_strains),
        "strains": unique_strains
    }

    # Ensure output directory exists
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Write JSON
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nSaved to: {OUTPUT_FILE}")
    print(f"File size: {OUTPUT_FILE.stat().st_size:,} bytes")

    # Show sample and stats
    print("\n" + "=" * 60)
    print("Sample strains:")
    for strain in unique_strains[:5]:
        print(f"  - {strain['name']} ({strain['producer']}) - {strain['type']}, {strain['form']}")
        print(f"    Attenuation: {strain['attenuation_low']}-{strain['attenuation_high']}%")
        print(f"    Temp: {strain['temp_low']}-{strain['temp_high']}°C")

    # Count by producer
    print("\n" + "=" * 60)
    print("Strains by producer:")
    producer_counts = {}
    for strain in unique_strains:
        producer = strain['producer'] or 'Unknown'
        producer_counts[producer] = producer_counts.get(producer, 0) + 1

    for producer, count in sorted(producer_counts.items(), key=lambda x: -x[1])[:15]:
        print(f"  {producer}: {count}")


if __name__ == "__main__":
    main()
