#!/usr/bin/env python3
"""
Scrape yeast strain data from BrewUnited and generate seed JSON file.

Usage:
    python scripts/scrape_yeast_data.py

Output:
    backend/seed/yeast_strains.json
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

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

# Sources
BREWUNITED_URL = "http://www.brewunited.com/yeast_database.php"


def fahrenheit_to_celsius(f: float) -> float:
    """Convert Fahrenheit to Celsius, rounded to 1 decimal."""
    return round((f - 32) * 5 / 9, 1)


def parse_temp_range(temp_str: str) -> tuple[float | None, float | None]:
    """Parse temperature range like '62°F - 75°F' and convert to Celsius."""
    if not temp_str:
        return None, None

    # Match patterns like "62°F - 75°F" or "62-75°F"
    match = re.search(r'(\d+(?:\.\d+)?)\s*°?\s*F?\s*[-–]\s*(\d+(?:\.\d+)?)\s*°?\s*F?', temp_str)
    if match:
        low_f = float(match.group(1))
        high_f = float(match.group(2))
        return fahrenheit_to_celsius(low_f), fahrenheit_to_celsius(high_f)

    # Single temp like "68°F"
    match = re.search(r'(\d+(?:\.\d+)?)\s*°?\s*F', temp_str)
    if match:
        temp_c = fahrenheit_to_celsius(float(match.group(1)))
        return temp_c, temp_c

    return None, None


def parse_attenuation(att_str: str) -> tuple[float | None, float | None]:
    """Parse attenuation like '75.0%' or '73% - 77%' and return low/high."""
    if not att_str:
        return None, None

    # Range like "73% - 77%" or "73-77%"
    match = re.search(r'(\d+(?:\.\d+)?)\s*%?\s*[-–]\s*(\d+(?:\.\d+)?)\s*%?', att_str)
    if match:
        return float(match.group(1)), float(match.group(2))

    # Single value like "75.0%"
    match = re.search(r'(\d+(?:\.\d+)?)\s*%', att_str)
    if match:
        val = float(match.group(1))
        return val, val

    return None, None


def normalize_flocculation(flocc_str: str) -> str | None:
    """Normalize flocculation to standard values."""
    if not flocc_str:
        return None

    flocc_lower = flocc_str.lower().strip()

    if "very high" in flocc_lower or "very_high" in flocc_lower:
        return "very_high"
    elif "high" in flocc_lower:
        return "high"
    elif "medium" in flocc_lower or "med" in flocc_lower:
        return "medium"
    elif "low" in flocc_lower:
        return "low"

    return flocc_str.lower().replace(" ", "_")


def normalize_type(type_str: str) -> str | None:
    """Normalize yeast type."""
    if not type_str:
        return None

    type_lower = type_str.lower().strip()

    if "ale" in type_lower:
        return "ale"
    elif "lager" in type_lower:
        return "lager"
    elif "wine" in type_lower:
        return "wine"
    elif "wild" in type_lower or "brett" in type_lower:
        return "wild"
    elif "wheat" in type_lower or "wit" in type_lower:
        return "ale"  # Wheat yeasts are typically ale yeasts
    elif "cider" in type_lower:
        return "wine"
    elif "mead" in type_lower:
        return "wine"

    return type_lower


def normalize_form(form_str: str) -> str | None:
    """Normalize yeast form."""
    if not form_str:
        return None

    form_lower = form_str.lower().strip()

    if "dry" in form_lower:
        return "dry"
    elif "liquid" in form_lower:
        return "liquid"
    elif "slant" in form_lower:
        return "slant"

    return form_lower


def extract_product_id(name: str, lab: str) -> str | None:
    """Try to extract product ID from name (e.g., 'WLP001' from 'California Ale WLP001')."""
    # Common patterns: WLP001, WY1056, S-04, US-05, BE-134
    patterns = [
        r'\b(WLP\d{3}[A-Z]?)\b',  # White Labs: WLP001, WLP001+
        r'\b(WY\d{4}[A-Z]?)\b',   # Wyeast: WY1056
        r'\b(\d{4}[A-Z]?)\b',     # Just numbers: 1056
        r'\b([A-Z]{1,3}[-]?\d{2,3})\b',  # Fermentis/Lallemand: S-04, US-05, BE-134
    ]

    for pattern in patterns:
        match = re.search(pattern, name, re.IGNORECASE)
        if match:
            return match.group(1).upper()

    return None


def clean_text(text: str) -> str:
    """Clean text by removing extra whitespace and newlines."""
    if not text:
        return ""
    return " ".join(text.split()).strip()


def scrape_brewunited() -> list[dict]:
    """Scrape yeast data from BrewUnited."""
    print(f"Fetching {BREWUNITED_URL}...")

    response = requests.get(BREWUNITED_URL, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, 'html.parser')

    # Find the yeast table - it's the main data table on the page
    tables = soup.find_all('table')
    yeast_table = None

    for table in tables:
        # Look for table with yeast-related headers
        headers = table.find_all('th')
        header_text = " ".join([h.get_text() for h in headers]).lower()
        if 'name' in header_text and 'lab' in header_text and 'flocculation' in header_text:
            yeast_table = table
            break

    if not yeast_table:
        # Try finding by class or id
        yeast_table = soup.find('table', class_='yeast') or soup.find('table', id='yeast')

    if not yeast_table:
        # Fallback: find largest table
        if tables:
            yeast_table = max(tables, key=lambda t: len(t.find_all('tr')))

    if not yeast_table:
        print("Could not find yeast table!")
        return []

    rows = yeast_table.find_all('tr')
    print(f"Found {len(rows)} rows in table")

    strains = []

    for row in rows[1:]:  # Skip header row
        cells = row.find_all(['td', 'th'])
        if len(cells) < 7:
            continue

        # Extract cell text
        name = clean_text(cells[0].get_text())
        lab = clean_text(cells[1].get_text())
        yeast_type = clean_text(cells[2].get_text())
        form = clean_text(cells[3].get_text())
        temp = clean_text(cells[4].get_text())
        attenuation = clean_text(cells[5].get_text())
        flocculation = clean_text(cells[6].get_text())
        notes = clean_text(cells[7].get_text()) if len(cells) > 7 else ""

        # Skip empty or header rows
        if not name or name.lower() == 'name':
            continue

        # Parse values
        temp_low, temp_high = parse_temp_range(temp)
        att_low, att_high = parse_attenuation(attenuation)
        product_id = extract_product_id(name, lab)

        strain = {
            "name": name,
            "producer": lab if lab and lab.lower() != "various" else None,
            "product_id": product_id,
            "type": normalize_type(yeast_type),
            "form": normalize_form(form),
            "attenuation_low": att_low,
            "attenuation_high": att_high,
            "temp_low": temp_low,
            "temp_high": temp_high,
            "alcohol_tolerance": None,  # Not in BrewUnited data
            "flocculation": normalize_flocculation(flocculation),
            "description": notes if notes else None,
            "source": "brewunited"
        }

        strains.append(strain)

    print(f"Extracted {len(strains)} yeast strains")
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
    print("Yeast Strain Data Scraper")
    print("=" * 60)

    all_strains = []

    # Scrape BrewUnited
    try:
        brewunited_strains = scrape_brewunited()
        all_strains.extend(brewunited_strains)
    except Exception as e:
        print(f"Error scraping BrewUnited: {e}")

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
        "version": "1.0",
        "last_updated": datetime.now().strftime("%Y-%m-%d"),
        "sources": ["brewunited.com"],
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

    # Show sample
    print("\nSample strains:")
    for strain in unique_strains[:5]:
        print(f"  - {strain['name']} ({strain['producer']}) - {strain['type']}, {strain['form']}")


if __name__ == "__main__":
    main()
