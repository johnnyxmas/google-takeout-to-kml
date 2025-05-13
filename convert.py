#!/usr/bin/env python3
"""
Enhanced Google Maps to KML/Z converter with multi-file ZIP support
"""

import csv
import re
import logging
import argparse
import sys
import zipfile
import os
from typing import Dict, Iterator, Optional, List
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

def process_csv_row(row: Dict[str, str], geocoder: Optional[Geocoder]) -> Optional[Dict]:
    """Process single CSV row into enhanced place dictionary"""
    try:
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            logging.debug(f"Processing row: {row}")
        # Try to get coordinates from explicit columns first
        lat = None
        lon = None
        
        # Check for explicit coordinate columns
        for lat_key in ['Latitude', 'latitude', 'lat']:
            if lat_key in row:
                lat = float(row[lat_key])
                break
        for lon_key in ['Longitude', 'longitude', 'lon', 'lng']:
            if lon_key in row:
                lon = float(row[lon_key])
                break

        # Preserve all original CSV data
        place = {
            'name': row.get('Title', row.get('Name', '')),
            'lat': lat,
            'lon': lon,
            'url': row.get('URL', row.get('Google Maps URL', '')),
            'description': row.get('Note', row.get('Description', '')),
            'raw_data': row  # Keep all original fields
        }
                
        # If no explicit coordinates, try to extract from URL
        if lat is None or lon is None:
            url = row.get('URL', row.get('Google Maps URL', ''))
            if not url:
                return None
                
            # Try different URL patterns with detailed failure logging
            if 'maps/search/' in url:
                # Dropped pin format: "maps/search/lat,lon"
                coords = url.split('maps/search/')[-1].split(',')
                if len(coords) >= 2:
                    try:
                        lat = float(coords[0])
                        lon = float(coords[1])
                        logging.debug(f"Extracted coordinates from maps/search/ format: {lat},{lon}")
                    except ValueError:
                        logging.debug(f"Failed to parse coordinates from maps/search/ format in URL: {url}")
            elif '!3d' in url and '!4d' in url:
                # Place URL format: "!3dlat!4dlon"
                lat_start = url.find('!3d') + 3
                lat_end = url.find('!4d')
                lon_start = url.find('!4d') + 3
                if lat_start > 3 and lat_end > lat_start:
                    try:
                        lat = float(url[lat_start:lat_end])
                        lon = float(url[lon_start:lon_start+20].split('!')[0])
                        logging.debug(f"Extracted coordinates from !3d format: {lat},{lon}")
                    except ValueError:
                        logging.debug(f"Failed to parse coordinates from !3d format in URL: {url}")
            elif '@' in url:
                # Newer format: "@lat,lon,z"
                coords = url.split('@')[-1].split(',')
                if len(coords) >= 2:
                    try:
                        lat = float(coords[0])
                        lon = float(coords[1])
                        logging.debug(f"Extracted coordinates from @ format: {lat},{lon}")
                    except ValueError:
                        logging.debug(f"Failed to parse coordinates from @ format in URL: {url}")
            elif 'maps/place/' in url:
                # Handle both direct place URLs and data=!4m2!3m1!1s format
                try:
                    response = requests.get(url,
                                        headers={'User-Agent': USER_AGENT},
                                        allow_redirects=True)
                    final_url = response.url
                    
                    # Try to extract from final URL first
                    if '@' in final_url:
                        coords = final_url.split('@')[-1].split(',')
                        if len(coords) >= 2:
                            try:
                                lat = float(coords[0])
                                lon = float(coords[1])
                                logging.debug(f"Extracted coordinates from redirected URL: {lat},{lon}")
                                return {
                                    'name': row.get('Title', row.get('Name', '')),
                                    'lat': lat,
                                    'lon': lon,
                                    'url': final_url,
                                    'note': row.get('Note', '')
                                }
                            except ValueError:
                                logging.debug(f"Failed to parse coordinates from redirected URL: {final_url}")
                    
                    # Special handling for data=!4m2!3m1!1s format
                    if 'data=!4m2!3m1!1s' in url:
                        logging.debug(f"Processing data=!4m2!3m1!1s format URL: {url}")
                        # These URLs should redirect to a URL with coordinates
                        if final_url != url:
                            if '@' in final_url:
                                coords = final_url.split('@')[-1].split(',')
                                if len(coords) >= 2:
                                    try:
                                        lat = float(coords[0])
                                        lon = float(coords[1])
                                        logging.debug(f"Extracted coordinates from data= redirect URL: {lat},{lon}")
                                        return {
                                            'name': row.get('Title', row.get('Name', '')),
                                            'lat': lat,
                                            'lon': lon,
                                            'url': final_url,
                                            'note': row.get('Note', '')
                                        }
                                    except ValueError:
                                        logging.debug(f"Failed to parse coordinates from data= redirect URL: {final_url}")
                    
                    # Fallback to page content scraping if needed
                    place_type = None
                    content = response.text
                    
                    if lat is None or lon is None:
                        # Try multiple coordinate patterns
                        patterns = [
                            r'"latitude":([0-9.-]+),"longitude":([0-9.-]+)',  # JSON-style
                            r'!3d([0-9.-]+)!4d([0-9.-]+)',  # URL-style
                            r'@([0-9.-]+),([0-9.-]+),',  # Map-style
                            r'center=([0-9.-]+)%2C([0-9.-]+)',  # URL-encoded
                            r'!3d([0-9.-]+)!4d([0-9.-]+)'  # Alternative format
                        ]
                        
                        for pattern in patterns:
                            coord_match = re.search(pattern, content)
                            if coord_match:
                                lat = float(coord_match.group(1))
                                lon = float(coord_match.group(2))
                                logging.debug(f"Extracted coordinates using pattern {pattern}: {lat},{lon}")
                                break
                    
                    # Try to extract place type/category
                    type_matches = re.findall(r'"featureTypeDescription":"([^"]+)"|"([^"]+)"\s*:\s*"Point Of Interest"', content)
                    if type_matches:
                        place_type = next((t for t in type_matches[0] if t), None)
                        logging.debug(f"Extracted place type: {place_type}")
                        
                    return {
                        'name': row.get('Title', row.get('Name', '')),
                        'lat': lat,
                        'lon': lon,
                        'url': final_url,
                        'note': row.get('Note', ''),
                        'type': place_type
                    }
                except Exception as e:
                    logging.debug(f"Error processing place URL: {str(e)}")
                    
        if lat is None or lon is None:
            error_msg = "Could not extract coordinates"
            if 'URL' in row or 'Google Maps URL' in row:
                error_msg += " from URL"
            logging.debug(f"{error_msg} from row: {row}")
            return {'error': error_msg}
            
        # Validate coordinates are reasonable
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            error_msg = f"Invalid coordinates {lat},{lon}"
            logging.debug(f"{error_msg} from row: {row}")
            return {'error': error_msg}
            
        place = {
            'name': row.get('Title', row.get('Name', '')),
            'lat': lat,
            'lon': lon,
            'url': row.get('URL', row.get('Google Maps URL', '')),
            'note': row.get('Note', '')
        }

        # Add geocoded address if enabled
        if geocoder:
            place['address'] = geocoder.reverse_geocode(place['lat'], place['lon'])

        return place
    except (KeyError, ValueError) as e:
        logging.debug(f"Skipping malformed row - {str(e)}: {row}")
        return None

def process_csv_file(csv_path: str, output_path: str, geocoder: Optional[Geocoder] = None, kmz: bool = False) -> Dict[str, int]:
    """Process single CSV file and write to KML/KMZ"""
    places = []
    failed = []
    
    # First pass to count rows (for progress reporting)
    with open(csv_path, 'r', encoding='utf-8') as f:
        total_rows = sum(1 for _ in csv.DictReader(f))
    
    # Second pass to process rows
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            percent = int((i+1)/total_rows*100)
            print(f"\rProcessing: {percent}% ({i+1}/{total_rows})", end='', flush=True)
            
            result = process_csv_row(row, geocoder)
            if result:
                if 'error' in result:
                    failed.append({
                        'name': row.get('Title', row.get('Name', 'Unknown')),
                        'url': row.get('URL', row.get('Google Maps URL', '')),
                        'error': result['error']
                    })
                else:
                    places.append(result)
    
    success_count = write_kml(output_path, places, failed_locations=failed, kmz=kmz)
    return {
        'success': success_count,
        'failed': len(failed)
    }

def process_zip_file(zip_path: str, output_dir: str, geocoder: Optional[Geocoder] = None, kmz: bool = False) -> Dict[str, int]:
    """Process ZIP archive and create multiple KML/KMZ files"""
    results = {}
    with zipfile.ZipFile(zip_path) as zf:
        # First pass to count CSV files
        csv_files = [f for f in zf.namelist() if f.lower().endswith('.csv')]
        total_files = len(csv_files)
        
        for i, filename in enumerate(csv_files):
            percent = int((i+1)/total_files*100)
            print(f"\rProcessing file: {percent}% ({i+1}/{total_files})", end='', flush=True)
            
            base_name = os.path.splitext(os.path.basename(filename))[0]
            ext = '.kmz' if kmz else '.kml'
            output_path = os.path.join(output_dir, f"{base_name}{ext}")
            
            with zf.open(filename) as zf_file:
                # Process rows in streaming fashion
                reader = csv.DictReader(line.decode('utf-8') for line in zf_file)
                places = []
                failed = []
                
                for row in reader:
                    result = process_csv_row(row, geocoder)
                    if result:
                        if 'error' in result:
                            failed.append({
                                'name': row.get('Title', row.get('Name', 'Unknown')),
                                'url': row.get('URL', row.get('Google Maps URL', '')),
                                'error': result['error']
                            })
                        else:
                            places.append(result)
                
                count = write_kml(output_path, places, failed_locations=failed, kmz=kmz)
                results[filename] = count
                print(f"Created {output_path} with {count} places")
    
    return results

# Google Maps icon URLs
ICON_MAP = {
    'lodging': 'http://maps.google.com/mapfiles/kml/pal4/icon57.png',
    'restaurant': 'http://maps.google.com/mapfiles/kml/pal4/icon46.png',
    'bar': 'http://maps.google.com/mapfiles/kml/pal4/icon7.png',
    'hiking': 'http://maps.google.com/mapfiles/kml/pal4/icon13.png',
    'swimming': 'http://maps.google.com/mapfiles/kml/pal4/icon61.png',
    'scenic': 'http://maps.google.com/mapfiles/kml/pal4/icon38.png',  # Camera icon
    'default': 'http://maps.google.com/mapfiles/kml/pal4/icon49.png'
}

def get_icon_url(place_type: Optional[str]) -> str:
    """Get appropriate Google Maps icon based on place type"""
    if not place_type:
        return ICON_MAP['scenic']  # Camera icon for scenic spots
    place_type = place_type.lower()
    if 'hotel' in place_type or 'motel' in place_type or 'lodging' in place_type:
        return ICON_MAP['lodging']
    elif 'restaurant' in place_type or 'cafe' in place_type or 'dining' in place_type:
        return ICON_MAP['restaurant']
    elif 'bar' in place_type or 'pub' in place_type:
        return ICON_MAP['bar']
    elif 'hiking' in place_type or 'trail' in place_type:
        return ICON_MAP['hiking']
    elif 'swimming' in place_type or 'pool' in place_type or 'beach' in place_type:
        return ICON_MAP['swimming']
    return ICON_MAP['default']

def write_kml(output_path: str, places: List[Dict], failed_locations: Optional[List[Dict]] = None, kmz: bool = False) -> int:
    """Write places data to KML/KMZ file with layers and icons"""
    # Create base KML structure
    kml = ET.Element('kml', xmlns='http://www.opengis.net/kml/2.2')
    document = ET.SubElement(kml, 'Document')
    
    # Precompile regex patterns for better performance
    coord_patterns = [
        re.compile(r'"latitude":([0-9.-]+),"longitude":([0-9.-]+)'),
        re.compile(r'!3d([0-9.-]+)!4d([0-9.-]+)'),
        re.compile(r'@([0-9.-]+),([0-9.-]+),'),
        re.compile(r'center=([0-9.-]+)%2C([0-9.-]+)')
    ]
    
    # Create layer folders and track places
    layers = {
        'Sleep': {
            'folder': ET.SubElement(document, 'Folder'),
            'places': [],
            'desc': 'Hotels, motels and other lodging'
        },
        'Eat': {
            'folder': ET.SubElement(document, 'Folder'),
            'places': [],
            'desc': 'Restaurants, bars and cafes'
        },
        'Do': {
            'folder': ET.SubElement(document, 'Folder'),
            'places': [],
            'desc': 'Activities and other places'
        }
    }
    
    # Organize places into layers
    for place in places:
        # Determine layer
        place_type = str(place.get('type', 'Scenic spot')).lower()
        if not place_type:
            place_type = 'scenic spot'
            
        if any(x in place_type for x in ['hotel', 'motel', 'lodging']):
            layer = layers['Sleep']
        elif any(x in place_type for x in ['restaurant', 'cafe', 'bar', 'pub']):
            layer = layers['Eat']
        else:
            layer = layers['Do']
            
        layer['places'].append(place)
        folder = layer['folder']  # Maintain existing folder reference
            
        placemark = ET.SubElement(folder, 'Placemark')
        ET.SubElement(placemark, 'name').text = place['name']
        
        # Add style with icon
        style = ET.SubElement(placemark, 'Style')
        icon = ET.SubElement(style, 'IconStyle')
        ET.SubElement(icon, 'Icon').text = get_icon_url(place_type)
        
        point = ET.SubElement(placemark, 'Point')
        ET.SubElement(point, 'coordinates').text = f"{place['lon']},{place['lat']},0"
        
        # Build detailed description
        desc = []
        if 'url' in place:
            desc.append(f"<a href=\"{place['url']}\">View on Google Maps</a>")
        if 'description' in place:
            desc.append(f"<b>Notes:</b> {place['description']}")
        if 'address' in place:
            desc.append(f"<b>Address:</b> {place['address']}")
        if 'phone' in place.get('raw_data', {}):
            desc.append(f"<b>Phone:</b> {place['raw_data']['phone']}")
            
        ET.SubElement(placemark, 'description').text = '<br/>'.join(desc)
    
    # Failed locations
    if failed_locations:
        folder = ET.SubElement(document, 'Folder')
        ET.SubElement(folder, 'name').text = 'Failed Conversions'
        ET.SubElement(folder, 'description').text = 'Locations that could not be converted'
        
        for failed in failed_locations:
            placemark = ET.SubElement(folder, 'Placemark')
            ET.SubElement(placemark, 'name').text = failed['name']
            ET.SubElement(placemark, 'description').text = f"URL: {failed.get('url', '')}\nError: {failed.get('error', 'Unknown error')}"
    
    # Pretty print the XML
    xml_str = minidom.parseString(ET.tostring(kml)).toprettyxml(indent="  ")
    
    # Create output directory if needed
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    
    if kmz:
        # Create KMZ (ZIP containing doc.kml)
        with zipfile.ZipFile(output_path, 'w', compression=zipfile.ZIP_DEFLATED) as kmz_file:
            kmz_file.writestr('doc.kml', xml_str)
    else:
        # Write plain KML
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(xml_str)
    
    # Export individual layer files
    layers_dir = os.path.join(os.path.dirname(output_path), 'layers')
    os.makedirs(layers_dir, exist_ok=True)
    
    base_name = os.path.splitext(os.path.basename(output_path))[0]
    
    for layer_name, layer_data in layers.items():
        if not layer_data['places']:
            continue
            
        # Create layer-specific KML
        layer_kml = ET.Element('kml', xmlns='http://www.opengis.net/kml/2.2')
        layer_doc = ET.SubElement(layer_kml, 'Document')
        layer_folder = ET.SubElement(layer_doc, 'Folder')
        ET.SubElement(layer_folder, 'name').text = layer_name
        ET.SubElement(layer_folder, 'description').text = layer_data['desc']
        
        for place in layer_data['places']:
            placemark = ET.SubElement(layer_folder, 'Placemark')
            ET.SubElement(placemark, 'name').text = place['name']
            
            style = ET.SubElement(placemark, 'Style')
            icon = ET.SubElement(style, 'IconStyle')
            ET.SubElement(icon, 'Icon').text = get_icon_url(place.get('type'))
            
            point = ET.SubElement(placemark, 'Point')
            ET.SubElement(point, 'coordinates').text = f"{place['lon']},{place['lat']},0"
            
            desc = []
            if 'url' in place:
                desc.append(f"<a href=\"{place['url']}\">View on Google Maps</a>")
            if 'description' in place:
                desc.append(f"<b>Notes:</b> {place['description']}")
            if 'address' in place:
                desc.append(f"<b>Address:</b> {place['address']}")
            if 'phone' in place.get('raw_data', {}):
                desc.append(f"<b>Phone:</b> {place['raw_data']['phone']}")
                
            ET.SubElement(placemark, 'description').text = '<br/>'.join(desc)
        
        layer_xml = minidom.parseString(ET.tostring(layer_kml)).toprettyxml(indent="  ")
        
        # Write both KML and KMZ versions
        layer_base = os.path.join(layers_dir, f"{base_name}_{layer_name.lower()}")
        
        with open(f"{layer_base}.kml", 'w', encoding='utf-8') as f:
            f.write(layer_xml)
            
        with zipfile.ZipFile(f"{layer_base}.kmz", 'w', compression=zipfile.ZIP_DEFLATED) as kmz_file:
            kmz_file.writestr('doc.kml', layer_xml)
    
    return len(places)

def show_banner():
    print("\n")
    print("Google \"My Maps\" to KML/Z Converter by Johnny Xmas")
    print("="*50 + "\n")

def main():
    show_banner()
    parser = argparse.ArgumentParser(description='Google \"My Maps\" to KML converter')
    parser.add_argument('input', help='Input CSV/ZIP file path')
    parser.add_argument('output', help='Output KML file path or directory')
    parser.add_argument('--geocode', action='store_true', help='Enable reverse geocoding')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--kml', action='store_true', help='Output KML format instead of KMZ (default)')
    args = parser.parse_args()

    # Configure logging to both file and console
    handlers = [
        logging.FileHandler('convert.log', mode='w'),
        logging.StreamHandler()
    ]
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=handlers
    )

    geocoder = Geocoder() if args.geocode else None
    
    try:
        if args.input.lower().endswith('.zip'):
            # Ensure output directory exists
            os.makedirs(args.output, exist_ok=True)
            results = process_zip_file(args.input, args.output, geocoder, not args.kml)
            total = sum(results.values())
            print(f"Processed {len(results)} CSV files with {total} total places")
        else:
            count = process_csv_file(args.input, args.output, geocoder, not args.kml)
            print(f"Created {args.output} with {count} places")
            
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()