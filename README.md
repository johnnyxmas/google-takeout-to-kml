# Google Maps to KML Converter

Convert Google Maps saved places to KML format with advanced features.

## Features

- 🗺️ Convert CSV or ZIP exports to KML
- 📁 Process multiple CSVs from ZIP archives
- 🔍 Reverse geocoding for location details

## Installation

```bash
pip install -r requirements.txt
```

## Requirements

- Python 3.8+
- Required packages:
  - requests
  - python-dateutil

## Usage

### Exporting from Google Takeout

1. Go to [Google Takeout](https://takeout.google.com)
2. Select only "Maps (your places)" data
3. Choose export format as CSV
4. Select delivery method (email/download)
5. Wait for Google to prepare your export
6. Download the ZIP archive containing your places

### Basic Conversion

```bash
python3 google_maps_to_kml.py input.csv output.kml
```

### ZIP Archive Processing

```bash
# Creates multiple KMLs in output_directory/
python3 google_maps_to_kml.py takeout.zip output_directory/
```

### With Reverse Geocoding

```bash
python3 google_maps_to_kml.py --geocode input.csv output.kml
```

## Output Format

For ZIP inputs:

```
output_directory/
├── Saved Places.kml
├── Starred Places.kml
└── ...
```

Each KML contains:

- Place names
- Coordinates
- Original URLs
- Location details (with --geocode)
- Categorized placemarks

## Error Handling

The tool will:

- Skip malformed rows with warnings
- Continue after API errors
- Provide clear error messages
- Exit with status codes:
  - 0: Success
  - 1: Fatal error
  - 2: Partial success

## Configuration

The following settings can be modified by editing the script directly:

- `GEOCODE_URL`: Nominatim reverse geocoding endpoint (default: "https://nominatim.openstreetmap.org/reverse")
- `USER_AGENT`: User agent string for API requests (default: "GoogleMapsToKML/1.0")
- `MAX_RETRIES`: Number of retry attempts for geocoding (default: 3)
- `CACHE_SIZE`: Size of geocoding cache (default: 1000)

## Examples

Process a full Google Takeout:

```bash
python3 google_maps_to_kml.py --geocode takeout-2025-05-11.zip my_places/
```

Convert single CSV with details:

```bash
python3 google_maps_to_kml.py --geocode saved_places.csv map.kml