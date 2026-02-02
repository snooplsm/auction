# Auction Project Codebase Analysis

## 1. PROJECT STRUCTURE

### File Directory
```
/Users/snooplsm/auction/
├── process_auctions.py           # Main processor script (Python)
├── AuctionMap.html               # Generated interactive map (Folium-based)
├── 20251205.html                 # Latest generated map output
├── AuctionMap.geojson            # Geographic data in GeoJSON format
├── AuctionList_Processed.xlsx    # Output spreadsheet with coords & neighborhoods
├── Auction List.xlsx             # Sample input file
├── geocode_cache.db              # SQLite3 cache for geocoding & neighborhoods
└── Other .xlsx files             # Various test/archive files
```

### Technology Stack
- **Backend**: Python 3 with asyncio
- **Visualization**: Folium (Python mapping library)
- **Data Format**: GeoJSON, Excel (XLSX)
- **Caching**: SQLite3
- **API Clients**: aiohttp (async HTTP)

---

## 2. LEGEND DEFINITION AND CLUSTER REFERENCE

### Legend Location
**File**: `/Users/snooplsm/auction/process_auctions.py`
**Function**: `_create_legend_html()` (lines 519-636)

### Legend Items (Current)
```
Blue = Active
Green = Sold
Orange = Postponed
Gray = Withdrawn/Cancelled
Red = Cluster (300 ft radius)  <-- CLUSTER REFERENCE
```

### Generated Output Files
- **HTML Legend**: Embedded in Folium maps (`20251205.html`, `AuctionMap.html`)
- **Location in HTML**: Lines 284-290 of generated maps
- **Legend Container ID**: `legend` (fixed position, bottom-left, draggable)

### Red Color for Clusters
**Source**: Line 442 in `process_auctions.py`
```python
folium.Marker(
    location=[cluster_lat, cluster_lng],
    popup=popup,
    tooltip=f"Cluster: {len(cluster)} properties within 300 feet",
    icon=folium.Icon(color='red', icon='sitemap', prefix='fa')
).add_to(fg)
```

**Reference in Legend**: Line 596
```python
<span style="color: red;">●</span> Red = Cluster (300 ft radius)
```

---

## 3. NEIGHBORHOOD DATA HANDLING

### Current Neighborhood Status
**Problem**: All neighborhoods currently return "Unknown" in GeoJSON files
- Example from `AuctionMap.geojson`: 31 properties with `"neighborhood": "Unknown"`

### Where Neighborhoods Are Defined

#### 3.1 Reverse Geocoding Function
**File**: `/Users/snooplsm/auction/process_auctions.py`
**Function**: `get_neighborhood()` (lines 122-147)

```python
async def get_neighborhood(session, lat, lng):
    """Get neighborhood from coordinates using reverse geocoding."""
    # Queries: https://api.phila.gov/ais_doc/v1/reverse
    # Looking for: neighborhood_name or neighborhood property
    # Returns: "Unknown" if not found
```

**Current Implementation**:
1. Calls Philadelphia AIS reverse geocoding API
2. Extracts `neighborhood_name` or `neighborhood` property
3. Falls back to "Unknown" on failure

#### 3.2 Neighborhood Cache
**File**: `/Users/snooplsm/auction/geocode_cache.db`
**Table**: `neighborhood_cache`
**Schema**:
```sql
CREATE TABLE IF NOT EXISTS neighborhood_cache (
    lat REAL,
    lng REAL,
    neighborhood TEXT,
    PRIMARY KEY (lat, lng)
)
```

**Functions**:
- `cache_get_neighborhood(conn, lat, lng)` - Retrieve cached neighborhood
- `cache_set_neighborhood(conn, lat, lng, neighborhood)` - Store in cache

#### 3.3 Neighborhood Processing Pipeline
**File**: `/Users/snooplsm/auction/process_auctions.py` (lines 709-732)

```python
# In main processing loop:
lat, lng = await geocode_address(session, cache_conn, addr, opa)
neighborhood = "Unknown"
if lat and lng:
    neighborhood = await get_neighborhood(session, lat, lng)

# Returns in result dict:
"neighborhood": neighborhood,  # Goes to Excel and GeoJSON
```

#### 3.4 Map Visualization Grouping
**File**: `/Users/snooplsm/auction/process_auctions.py` (lines 366-390)

Properties grouped by neighborhood:
```python
neighborhoods = {}
for r in valid_results:
    neighborhood = r.get("neighborhood", "Unknown")
    if neighborhood not in neighborhoods:
        neighborhoods[neighborhood] = []
    neighborhoods[neighborhood].append(r)

# Creates Folium FeatureGroup for each neighborhood
for neighborhood, data in neighborhood_markers.items():
    fg = folium.FeatureGroup(name=neighborhood, show=True)
    # Add markers to this feature group
    fg.add_to(map_obj)
```

---

## 4. OPA DATA USAGE

### OPA Field Information
**OPA** = Office of Property Assessment account number (Philadelphia property ID)

### OPA Implementation Locations

#### 4.1 Input Processing
**File**: `/Users/snooplsm/auction/process_auctions.py`
**Lines**: 662, 688-692

```python
idx_opa = headers.index("OPA")
opa_raw = row[idx_opa].value
opas = split_ampersand_field(str(opa_raw))  # Handle multiple properties
```

#### 4.2 OPA-Based Geocoding (Priority Method)
**File**: `/Users/snooplsm/auction/process_auctions.py`
**Function**: `geocode_address()` (lines 189-247)

```python
# OPA is tried FIRST (most accurate):
if opa:
    url = f"{PHILA_AIS_URL}/{opa}"  # Using Philadelphia API
    # Line 207-220
```

**API Endpoint**: `https://api.phila.gov/ais_doc/v1/search/{OPA}`
**Response**: GeoJSON with coordinates

#### 4.3 OPA in Output Data
**File**: `/Users/snooplsm/auction/process_auctions.py`
**Lines**: 724, 749, 768

Output includes:
- `"opa": opa` - In result dict
- `"phila_link": f"https://property.phila.gov/?p={opa}"` - Link to OPA property record

#### 4.4 OPA in GeoJSON
**Example from AuctionMap.geojson** (line 21):
```json
"opa": "401270900",
"phila_link": "https://property.phila.gov/?p=401270900",
```

#### 4.5 OPA in Popups
**File**: `/Users/snooplsm/auction/process_auctions.py`
**Function**: `_create_popup_html()` (lines 481-482)

Displays in property popups:
```html
OPA: {r['opa'] or 'N/A'}<br>
```

---

## 5. NOMINATIM API INTEGRATION

### Current Integration Status
**Status**: Already integrated and actively used

### Nominatim Implementation

#### 5.1 Configuration
**File**: `/Users/snooplsm/auction/process_auctions.py`
**Line**: 28

```python
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "AuctionProcessor/1.0 (your@email.com)"
```

#### 5.2 Fallback Hierarchy
**Order of attempts** (in `geocode_address()` function, lines 189-247):

1. **Primary**: OPA API (Philadelphia AIS)
   - Most accurate for PA properties
   - Requires valid OPA number

2. **Secondary**: Nominatim Full Address Search
   - Called when OPA not available or fails
   - Parameters: full address, format=jsonv2, limit=1
   - Rate limit: 1 second delay between requests

3. **Tertiary**: Nominatim Zipcode Fallback
   - Extracts 5-digit zipcode from address
   - Called when full address fails
   - Rate limit: 1 second delay between requests

#### 5.3 Nominatim API Calls

**Full Address Search** (lines 225-244):
```python
params = {
    "q": address,           # Full street address
    "format": "jsonv2",
    "limit": 1,             # Only first result
}

async with session.get(NOMINATIM_URL, params=params) as resp:
    if resp.status == 200:
        data = await resp.json()
        lat = float(data[0]["lat"])
        lng = float(data[0]["lon"])
```

**Zipcode Only Search** (lines 261-280):
```python
params = {
    "q": zipcode,          # Just 5-digit code
    "format": "jsonv2",
    "limit": 1,
}

async with session.get(NOMINATIM_URL, params=params) as resp:
    # Similar parsing...
```

#### 5.4 Rate Limiting & Courtesy
- 1-second delay after each Nominatim request (lines 243, 279)
- 0.5-second delay after OPA requests (line 219)
- User-Agent header sent with all requests (line 677)

#### 5.5 Geocode Cache
**File**: `/Users/snooplsm/auction/geocode_cache.db`
**Table**: `cache`
**Schema**:
```sql
CREATE TABLE IF NOT EXISTS cache (
    query TEXT PRIMARY KEY,
    lat REAL,
    lng REAL
)
```

**Purpose**: Avoid redundant Nominatim queries
**Hit Detection**: Lines 192-199

---

## 6. MAP VISUALIZATION ARCHITECTURE

### Map Generation Function
**File**: `/Users/snooplsm/auction/process_auctions.py`
**Function**: `create_interactive_map()` (lines 343-458)

### Map Components

#### 6.1 Base Map
```python
map_obj = folium.Map(
    location=[center_lat, center_lng],  # Auto-centered
    zoom_start=12,
    tiles="OpenStreetMap",
    prefer_canvas=True
)
```

#### 6.2 Feature Groups (One per Neighborhood)
```python
for neighborhood, data in neighborhood_markers.items():
    fg = folium.FeatureGroup(name=neighborhood, show=True)
    # Add markers...
    fg.add_to(map_obj)
```

#### 6.3 Marker Types

**Single Property** (Blue, Green, Orange, or Gray):
```python
folium.Marker(
    location=[r['lat'], r['lng']],
    popup=popup,
    tooltip=f"{r['address']} - {r['status']}",
    icon=folium.Icon(color=marker_color, icon=marker_icon)
).add_to(fg)
```

**Clustered Properties** (Red with sitemap icon):
```python
folium.Marker(
    location=[cluster_lat, cluster_lng],  # Cluster center
    popup=popup,
    tooltip=f"Cluster: {len(cluster)} properties within 300 feet",
    icon=folium.Icon(color='red', icon='sitemap', prefix='fa')
).add_to(fg)
```

#### 6.4 Clustering Logic
**File**: `/Users/snooplsm/auction/process_auctions.py`
**Function**: `cluster_properties()` (lines 150-183)

```python
def cluster_properties(properties, max_distance_feet=300):
    # Uses Haversine distance formula
    # Groups properties within 300 feet of each other
    # Called per neighborhood (line 377)
```

#### 6.5 Custom Legend (HTML/CSS/JavaScript)
**File**: `/Users/snooplsm/auction/process_auctions.py`
**Function**: `_create_legend_html()` (lines 519-636)

**Features**:
- Fixed position: bottom-left of map
- Draggable by header
- Expandable/collapsible neighborhoods
- Shows property count per neighborhood
- List of all addresses in neighborhood
- Color legend for marker types

**HTML Output**: Embedded directly in Folium map via `Element`

#### 6.6 Layer Control
**Line**: 453
```python
folium.LayerControl().add_to(map_obj)
```
Allows toggling neighborhoods on/off

#### 6.7 Popups
**Function**: `_create_popup_html()` (lines 461-503)

**Popup Content**:
```
Address
Auction ID, Neighborhood, Status, Start Price, Auction Opens
OPA, Book/Writ, Debt Amount
Links: Bid4Assets, OPA Property Record, Google Street View
```

---

## 7. DATA FLOW SUMMARY

```
INPUT (Excel)
    ↓
process_file()
    ├─ Load Excel rows
    ├─ Split ampersand fields (addresses, OPAs, books)
    └─ Create async tasks for each property
         ↓
geocode_address()
    ├─ Check cache (fast)
    ├─ Try OPA API (most accurate)
    ├─ Try Nominatim full address
    └─ Try Nominatim zipcode
         ↓
get_neighborhood()
    └─ Reverse geocode to get neighborhood
         ↓
OUTPUTS:
    ├─ AuctionList_Processed.xlsx
    │   └─ Columns: All input + Neighborhood, Lat, Lng, links
    ├─ AuctionMap.geojson
    │   └─ GeoJSON features with all properties
    └─ [date].html (Interactive Folium map)
        ├─ Feature groups by neighborhood
        ├─ Markers color-coded by status
        ├─ Cluster markers in red
        ├─ Legend with neighborhoods & colors
        ├─ Layer control
        └─ Draggable legend
```

---

## 8. KEY FILES REFERENCE

| File | Purpose | Key Functions |
|------|---------|---|
| `process_auctions.py` | Main processor | `process_file()`, `geocode_address()`, `get_neighborhood()`, `create_interactive_map()` |
| `AuctionMap.geojson` | Spatial data | GeoJSON FeatureCollection |
| `20251205.html` | Interactive map | Folium-generated, legend at lines 60-291 |
| `geocode_cache.db` | Caching layer | 2 tables: `cache`, `neighborhood_cache` |
| `AuctionList_Processed.xlsx` | Output data | Full property info with coordinates |

---

## 9. API ENDPOINTS SUMMARY

| API | Endpoint | Purpose | Used For |
|-----|----------|---------|----------|
| Philadelphia AIS | `https://api.phila.gov/ais_doc/v1/search/{OPA}` | OPA-based geocoding | Primary location lookup |
| Philadelphia AIS | `https://api.phila.gov/ais_doc/v1/reverse` | Reverse geocoding | Neighborhood lookup |
| Nominatim OSM | `https://nominatim.openstreetmap.org/search` | Address geocoding | Fallback when OPA unavailable |
| Philadelphia Property | `https://property.phila.gov/?p={OPA}` | Property info link | Generated in popups/output |
| Bid4Assets | `https://www.bid4assets.com/auction/index/{ID}` | Auction link | Generated in popups/output |
| Google Maps | `https://www.google.com/maps?q={address}&layer=c` | Street view link | Generated in output |

