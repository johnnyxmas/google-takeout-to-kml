#!/usr/bin/env python3
"""
Enhanced Google Maps to KML converter with multi-file ZIP support
"""

import csv
import re
import argparse
import sys
import zipfile
import os
from typing import Dict, Iterator, Optional
from xml.etree import ElementTree as ET
from xml.dom import minidom
from collections import defaultdict
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configuration
GEOCODE_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "GoogleMapsToKML/1.0"
MAX_RETRIES = 3
CACHE_SIZE = 1000

class Geocoder:
    """Handles reverse geocoding with caching and retries"""
    def __init__(self):
        self.session = requests.Session()
        retry = Retry(total=MAX_RETRIES, backoff_factor=0.1)
        self.session.mount('https://', HTTPAdapter(max_retries=retry))
        self.cache = {}
        
    def reverse_geocode(self, lat: float, lon: float) -> Optional[str]:
        """Get address from coordinates with caching"""
        cache_key = f"{lat:.5f},{lon:.5f}"
        if cache_key in self.cache:
            return self.cache[cache_key]
            
        try:
            params = {'lat': lat, 'lon': lon, 'format': 'json'}
            headers = {'User-Agent': USER_AGENT}
            response = self.session.get(GEOCODE_URL, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            address = data.get('display_name', '')
            self.cache[cache_key] = address
            return address
        except Exception as e:
            print(f"Geocoding failed for {lat},{lon}: {str(e)}", file=sys.stderr)
            return None

def process_csv_file(csv_path: str, output_path: str, geocoder: Optional[Geocoder] = None) -> int:
    """Process single CSV file and write to KML"""
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        places = []
        for row in reader:
            result = process_csv_row(row, geocoder)
            if result:
                places.append(result)
        return write_kml(output_path, places)

def process_zip_file(zip_path: str, output_dir: str, geocoder: Optional[Geocoder] = None) -> Dict[str, int]:
    """Process ZIP archive and create multiple KMLs"""
    results = {}
    with zipfile.ZipFile(zip_path) as zf:
        for filename in zf.namelist():
            if filename.lower().endswith('.csv'):
                base_name = os.path.splitext(os.path.basename(filename))[0]
                kml_path = os.path.join(output_dir, f"{base_name}.kml")
                
                with zf.open(filename) as zf_file:
                    reader = csv.DictReader(line.decode('utf-8') for line in zf_file)
                    places = []
                    for row in reader:
                        result = process_csv_row(row, geocoder)
                        if result:
                            places.append(result)
                    
                    count = write_kml(kml_path, places)
                    results[filename] = count
                    print(f"Created {kml_path} with {count} places")
    
    return results

def main():
    parser = argparse.ArgumentParser(description='Google Maps to KML converter')
    parser.add_argument('input', help='Input CSV/ZIP file path')
    parser.add_argument('output', help='Output KML file path or directory')
    parser.add_argument('--geocode', action='store_true', help='Enable reverse geocoding')
    args = parser.parse_args()

    geocoder = Geocoder() if args.geocode else None
    
    try:
        if args.input.lower().endswith('.zip'):
            # Ensure output directory exists
            os.makedirs(args.output, exist_ok=True)
            results = process_zip_file(args.input, args.output, geocoder)
            total = sum(results.values())
            print(f"Processed {len(results)} CSV files with {total} total places")
        else:
            count = process_csv_file(args.input, args.output, geocoder)
            print(f"Created {args.output} with {count} places")
            
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()