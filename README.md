# Google Maps to KMZ Converter

Convert Google Maps saved places to compressed KMZ format by default (or KML optionally).

## Key Features

- 🗜️ Default KMZ output (5-10x smaller than KML)
- ⚡ Single command conversion
- 🔄 Supports both CSV and ZIP inputs
- 📍 Optional reverse geocoding
- ❌ Tracks failed conversions

## Basic Usage

```bash
python convert.py input.csv output.kmz
```

### Options:
- `--kml` - Output KML instead of default KMZ
- `--geocode` - Add address details
- `--debug` - Enable verbose logging

## Examples

```bash
# Default KMZ output
python convert.py saved_places.csv my_places.kmz

# Force KML output
python convert.py --kml saved_places.csv output.kml

# Process ZIP archive
python convert.py takeout.zip outputs/

# With geocoding and debug
python convert.py --geocode --debug input.csv output.kmz
```

## Output Details

- KMZ is the recommended format (smaller, single file)
- Failed conversions are included with error details
- Maintains original place names and URLs
- Creates a `layers` subdirectory with:
  - Individual KML/KMZ files for each category (Sleep, Eat, Do)
  - Both KML and KMZ versions of each layer
  - Organized by place type (hotels, restaurants, activities)

## Layer Organization

Places are automatically categorized into:
- **Sleep**: Hotels, motels and other lodging
- **Eat**: Restaurants, bars and cafes
- **Do**: All other activities and places

Each layer maintains:
- Google Maps icons
- Original place metadata
- Clickable map links