# Key Code Snippets - Auction Project

## 1. LEGEND CODE

### Location: process_auctions.py, lines 519-636

#### Legend HTML Generation
```python
def _create_legend_html(neighborhood_markers):
    """Create interactive HTML legend for neighborhoods."""
    legend_html = """
    <div id="legend" style="
        position: fixed;
        bottom: 50px; left: 50px;
        width: 320px;
        background-color: white;
        border: 2px solid grey;
        ...
    ">
        <h3 style="margin-top: 0; margin-bottom: 12px; font-size: 16px;">
            Properties by Neighborhood
        </h3>
```

#### Legend Items (Color Codes)
```python
# Lines 589-596
legend_html += """
    <div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid #ddd; 
                font-size: 11px; color: #666;">
        <strong>Legend:</strong><br>
        <span style="color: blue;">●</span> Blue = Active<br>
        <span style="color: green;">●</span> Green = Sold<br>
        <span style="color: orange;">●</span> Orange = Postponed<br>
        <span style="color: gray;">●</span> Gray = Withdrawn/Cancelled<br>
        <span style="color: red;">●</span> Red = Cluster (300 ft radius)
    </div>
"""
```

### Red Cluster Marker Code
```python
# Lines 438-443
folium.Marker(
    location=[cluster_lat, cluster_lng],
    popup=popup,
    tooltip=f"Cluster: {len(cluster)} properties within 300 feet",
    icon=folium.Icon(color='red', icon='sitemap', prefix='fa')
).add_to(fg)
```

---

## 2. NEIGHBORHOOD HANDLING CODE

### get_neighborhood() Function
```python
# Lines 122-147
async def get_neighborhood(session, lat, lng):
    """Get neighborhood from coordinates using reverse geocoding."""
    if lat is None or lng is None:
        return "Unknown"

    try:
        # Try Philadelphia neighborhoods endpoint
        url = "https://api.phila.gov/ais_doc/v1/reverse"
        params = {
            "lat": lat,
            "lng": lng,
            "gatekeeperKey": PHILA_GATEKEEPER_KEY,
        }

        async with session.get(url, params=params, timeout=5) as resp:
            if resp.status == 200:
                data = await resp.json()
                if data.get("features") and len(data["features"]) > 0:
                    props = data["features"][0].get("properties", {})
                    neighborhood = props.get("neighborhood_name") or \
                                  props.get("neighborhood") or "Unknown"
                    logger.debug(f"Found neighborhood: {neighborhood} for ({lat:.4f}, {lng:.4f})")
                    return neighborhood
    except Exception as e:
        logger.debug(f"Error getting neighborhood: {e}")

    return "Unknown"
```

### Neighborhood Processing in Main Loop
```python
# Lines 709-732 (in worker function)
lat, lng = await geocode_address(session, cache_conn, addr, opa)
neighborhood = "Unknown"
if lat and lng:
    neighborhood = await get_neighborhood(session, lat, lng)
return {
    "auction_id": auction_id,
    "status": status,
    "min_bid": min_bid,
    "open_date": str(open_date) if open_date else None,
    "attorney": attorney,
    "debt_amount": debt_amount,
    "book_writ": bk,
    "opa": opa,
    "address": addr,
    "lat": lat,
    "lng": lng,
    "neighborhood": neighborhood,  # Goes to Excel and GeoJSON
    ...
}
```

### Neighborhood Grouping for Map
```python
# Lines 366-390
neighborhoods = {}
for r in valid_results:
    neighborhood = r.get("neighborhood", "Unknown")
    if neighborhood not in neighborhoods:
        neighborhoods[neighborhood] = []
    neighborhoods[neighborhood].append(r)

# Create feature groups for each neighborhood
feature_groups = {}
for neighborhood, data in neighborhood_markers.items():
    fg = folium.FeatureGroup(name=neighborhood, show=True)
    feature_groups[neighborhood] = fg
    # Add markers for each cluster...
    fg.add_to(map_obj)
```

---

## 3. OPA DATA USAGE CODE

### OPA Input Processing
```python
# Lines 656-699
idx_opa = headers.index("OPA")
# ... later in loop ...
opa_raw = row[idx_opa].value
opas = split_ampersand_field(str(opa_raw))  # Handle multiple properties

# Normalize lengths for parallel arrays
max_len = max(len(addresses), len(opas), len(books))
addresses += [None] * (max_len - len(addresses))
opas += [None] * (max_len - len(opas))
books += [None] * (max_len - len(books))
```

### OPA-Based Geocoding (Primary Method)
```python
# Lines 202-220 in geocode_address()
if opa:
    logger.debug(f"[OPA] Querying OPA {opa} for: {address}")
    params = {
        "gatekeeperKey": PHILA_GATEKEEPER_KEY,
    }
    url = f"{PHILA_AIS_URL}/{opa}"  # https://api.phila.gov/ais_doc/v1/search/{OPA}

    async with session.get(url, params=params) as resp:
        if resp.status == 200:
            data = await resp.json()
            if data.get("features") and len(data["features"]) > 0:
                coords = data["features"][0].get("geometry", {}).get("coordinates")
                if coords and len(coords) >= 2:
                    lng = float(coords[0])
                    lat = float(coords[1])
                    cache_set(cache_conn, address, lat, lng)
                    logger.debug(f"[OPA] Found OPA {opa} -> ({lat:.4f}, {lng:.4f})")
                    await asyncio.sleep(0.5)  # Small delay for API politeness
                    return (lat, lng)
```

### OPA Output
```python
# Lines 748-750 (Excel output)
new_sheet.append([
    ...,
    r["opa"],
    ...,
])

# Lines 784-786 (GeoJSON output)
"properties": {
    "opa": "401270900",
    "phila_link": "https://property.phila.gov/?p=401270900",
    ...
}

# Lines 481-482 (Popup display)
OPA: {r['opa'] or 'N/A'}<br>
```

---

## 4. NOMINATIM INTEGRATION CODE

### Configuration
```python
# Lines 28-31
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
PHILA_AIS_URL = "https://api.phila.gov/ais_doc/v1/search"
PHILA_GATEKEEPER_KEY = "6ba4de64d6ca99aa4db3b9194e37adbf"
USER_AGENT = "AuctionProcessor/1.0 (your@email.com)"
```

### Nominatim Full Address Search (Fallback 1)
```python
# Lines 225-244
logger.debug(f"[NOMINATIM] Querying: {address}")
params = {
    "q": address,
    "format": "jsonv2",
    "limit": 1,
}

async with session.get(NOMINATIM_URL, params=params) as resp:
    if resp.status != 200:
        logger.debug(f"[NOMINATIM] Failed ({resp.status}): {address}...")
        return await geocode_zipcode_fallback(session, cache_conn, address, opa)

    data = await resp.json()
    if data:
        lat = float(data[0]["lat"])
        lng = float(data[0]["lon"])
        cache_set(cache_conn, address, lat, lng)
        logger.debug(f"[NOMINATIM] Found: {address} -> ({lat:.4f}, {lng:.4f})")
        await asyncio.sleep(1)  # respect Nominatim rate limit
        return (lat, lng)
```

### Nominatim Zipcode Fallback (Fallback 2)
```python
# Lines 250-283
async def geocode_zipcode_fallback(session, cache_conn, address, opa=None):
    """Fallback: extract zipcode and try geocoding that."""
    zipcode_match = re.search(r'\b(\d{5})\b', str(address))
    if not zipcode_match:
        logger.debug(f"[ZIPCODE FALLBACK] No zipcode found in: {address}")
        return (None, None)

    zipcode = zipcode_match.group(1)
    params = {
        "q": zipcode,
        "format": "jsonv2",
        "limit": 1,
    }

    async with session.get(NOMINATIM_URL, params=params) as resp:
        if resp.status != 200:
            return (None, None)

        data = await resp.json()
        if data:
            lat = float(data[0]["lat"])
            lng = float(data[0]["lon"])
            cache_set(cache_conn, zipcode, lat, lng)
            logger.debug(f"[ZIPCODE FALLBACK] Found {zipcode} -> ({lat:.4f}, {lng:.4f})")
            await asyncio.sleep(1)
            return (lat, lng)
    
    return (None, None)
```

### Geocoding Fallback Chain
```python
# Lines 189-247 in geocode_address()
async def geocode_address(session, cache_conn, address, opa=None):
    """Returns (lat, lng) or (None, None). 
       Tries OPA first, then full address, then zipcode."""
    
    # Step 1: Check cache
    cached = cache_get(cache_conn, address)
    if cached:
        return cached
    
    # Step 2: Try OPA (if provided)
    if opa:
        # OPA geocoding code...
        pass
    
    # Step 3: Try Nominatim full address
    logger.debug(f"[NOMINATIM] Querying: {address}")
    # Full address search...
    
    # Step 4: Try Nominatim zipcode
    return await geocode_zipcode_fallback(session, cache_conn, address, opa)
```

---

## 5. CLUSTERING CODE

### Haversine Distance Calculation
```python
# Lines 107-119
def haversine_distance(lat1, lng1, lat2, lng2):
    """Calculate distance between two coordinates in feet."""
    lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])

    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlng/2)**2
    c = 2 * asin(sqrt(a))
    r = 3959  # Radius of earth in miles

    return c * r * 5280  # Convert to feet
```

### Clustering Function
```python
# Lines 150-183
def cluster_properties(properties, max_distance_feet=300):
    """Cluster properties that are within max_distance_feet of each other."""
    if not properties:
        return []

    clusters = []
    visited = set()

    for i, prop in enumerate(properties):
        if i in visited or prop.get("lat") is None or prop.get("lng") is None:
            continue

        cluster = [prop]
        visited.add(i)

        # Find all properties within max_distance_feet
        for j, other_prop in enumerate(properties):
            if j <= i or j in visited:
                continue
            if other_prop.get("lat") is None or other_prop.get("lng") is None:
                continue

            distance = haversine_distance(
                prop["lat"], prop["lng"],
                other_prop["lat"], other_prop["lng"]
            )

            if distance <= max_distance_feet:
                cluster.append(other_prop)
                visited.add(j)

        clusters.append(cluster)

    return clusters
```

### Clustering in Map Generation
```python
# Lines 374-381
for neighborhood, props in neighborhoods.items():
    clusters = cluster_properties(props, max_distance_feet=300)
    neighborhood_markers[neighborhood] = {
        "count": len(props),
        "clusters": clusters,
        "properties": props
    }
```

---

## 6. MAP GENERATION CODE

### Main Map Creation Function
```python
# Lines 343-458
def create_interactive_map(results, map_path):
    """Create an interactive Folium map with neighborhood legend 
       and proximity clustering."""
    logger.info("Creating interactive map...")

    # Filter valid results
    valid_results = [r for r in results 
                    if r["lat"] is not None and r["lng"] is not None]
    
    # Calculate map center
    center_lat = sum(r["lat"] for r in valid_results) / len(valid_results)
    center_lng = sum(r["lng"] for r in valid_results) / len(valid_results)

    # Create map
    map_obj = folium.Map(
        location=[center_lat, center_lng],
        zoom_start=12,
        tiles="OpenStreetMap",
        prefer_canvas=True
    )

    # ... Group by neighborhood, create clusters ...
    
    # Create custom legend
    legend_html = _create_legend_html(neighborhood_markers)
    from folium import Element
    map_obj.get_root().html.add_child(Element(legend_html))

    # Add layer control
    folium.LayerControl().add_to(map_obj)

    # Save map
    map_obj.save(map_path)
    logger.info(f"✔ Interactive map saved to: {map_path}")
```

---

## 7. MARKER COLOR/ICON CODE

### Marker Styling Based on Status
```python
# Lines 506-516
def _get_marker_color_icon(status):
    """Determine marker color and icon based on status."""
    status = str(status).lower()
    if 'sold' in status:
        return 'green', 'check'
    elif 'withdrawn' in status or 'cancelled' in status:
        return 'gray', 'times'
    elif 'postponed' in status:
        return 'orange', 'clock'
    else:
        return 'blue', 'gavel'
```

### Single Property Marker
```python
# Lines 394-406
marker_color, marker_icon = _get_marker_color_icon(r['status'])

folium.Marker(
    location=[r['lat'], r['lng']],
    popup=popup,
    tooltip=f"{r['address']} - {r['status']}",
    icon=folium.Icon(color=marker_color, icon=marker_icon, prefix='fa')
).add_to(fg)
```

---

## 8. ASYNC PROCESSING CODE

### Concurrent Processing Configuration
```python
# Lines 677-678
async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}) as session:
    sem = asyncio.Semaphore(CONCURRENT_WORKERS)  # 5 concurrent workers
```

### Worker Task Creation
```python
# Lines 709-734
for i in range(max_len):
    addr = addresses[i]
    opa = opas[i]
    bk = books[i]

    if not addr:
        continue

    async def worker(addr=addr, opa=opa, bk=bk, ...):
        async with sem:
            lat, lng = await geocode_address(session, cache_conn, addr, opa)
            neighborhood = "Unknown"
            if lat and lng:
                neighborhood = await get_neighborhood(session, lat, lng)
            return { ... }

    tasks.append(worker())

# Wait for all tasks
results = await asyncio.gather(*tasks)
```

