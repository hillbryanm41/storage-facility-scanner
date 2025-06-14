#!/usr/bin/env python3
"""
Self-Storage Facility Scanner - Fixed Single-Window Version
Includes multiple mapping options and better iframe integration
"""

from flask import Flask, render_template, request, jsonify, session
import json
import math
import time
from typing import List, Tuple, Dict
import uuid
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'storage-scanner-secret-key-2024')

# In-memory storage for scanning sessions
scanning_sessions = {}

class GridCalculator:
    """Calculate systematic grid coverage for the scanning area"""
    
    @staticmethod
    def calculate_scan_grid(center_lat: float, center_lon: float, 
                          radius_miles: float, zoom_level: int) -> List[Dict]:
        """Calculate grid points with metadata for web display"""
        
        # Viewport sizes at different zoom levels (approximate)
        viewport_degrees = {
            15: 0.02,   # ~1.4 miles
            16: 0.01,   # ~0.7 miles  
            17: 0.005,  # ~0.35 miles
            18: 0.0025, # ~0.17 miles
            19: 0.00125 # ~0.09 miles
        }
        
        view_size = viewport_degrees.get(zoom_level, 0.0025)
        radius_deg = radius_miles / 69.0  # Convert miles to degrees
        
        # Calculate step size with 20% overlap for thoroughness
        step_size = view_size * 0.8
        grid_size = int(2 * radius_deg / step_size) + 1
        
        grid_points = []
        point_id = 0
        
        for row in range(grid_size):
            lat = center_lat - radius_deg + (row * step_size)
            
            # Alternate scanning direction for efficiency (like reading a book)
            cols = range(grid_size) if row % 2 == 0 else range(grid_size - 1, -1, -1)
            
            for col in cols:
                lon = center_lon - radius_deg + (col * step_size)
                
                # Only include points within the circular radius
                distance = GridCalculator._distance_miles(center_lat, center_lon, lat, lon)
                if distance <= radius_miles:
                    grid_points.append({
                        'id': point_id,
                        'lat': round(lat, 6),
                        'lon': round(lon, 6),
                        'row': row,
                        'col': col,
                        'distance_from_center': round(distance, 2),
                        'google_maps_url': f"https://maps.google.com/@{lat},{lon},{zoom_level}z",
                        'google_embed_url': f"https://www.google.com/maps/embed?pb=!1m14!1m12!1m3!1d3000!2d{lon}!3d{lat}!2m3!1f0!2f0!3f0!3m2!1i1024!2i768!4f13.1!5e0!3m2!1sen!2sus!4v1",
                        'openstreetmap_url': f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}&zoom={zoom_level}",
                        'bing_maps_url': f"https://www.bing.com/maps?cp={lat}~{lon}&lvl={zoom_level}"
                    })
                    point_id += 1
        
        return grid_points
    
    @staticmethod
    def _distance_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between coordinates in miles using Haversine formula"""
        R = 3959  # Earth's radius in miles
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        
        a = (math.sin(dlat/2) * math.sin(dlat/2) + 
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * 
             math.sin(dlon/2) * math.sin(dlon/2))
        
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return R * c


@app.route('/')
def index():
    """Main scanner interface"""
    return render_template('scanner.html')


@app.route('/setup_scan', methods=['POST'])
def setup_scan():
    """Setup a new scanning session"""
    try:
        data = request.json
        
        # Validate and convert input
        center_lat = float(data['center_lat'])
        center_lon = float(data['center_lon'])
        radius_miles = float(data['radius_miles'])
        zoom_level = int(data['zoom_level'])
        speed_seconds = float(data['speed_seconds'])
        
        # Generate unique session ID
        session_id = str(uuid.uuid4())
        
        # Calculate grid points for systematic coverage
        grid_points = GridCalculator.calculate_scan_grid(
            center_lat, center_lon, radius_miles, zoom_level
        )
        
        # Store session data in memory
        scanning_sessions[session_id] = {
            'id': session_id,
            'center_lat': center_lat,
            'center_lon': center_lon,
            'radius_miles': radius_miles,
            'zoom_level': zoom_level,
            'speed_seconds': speed_seconds,
            'grid_points': grid_points,
            'current_index': 0,
            'is_running': False,
            'is_paused': False,
            'bookmarks': [],
            'created_at': datetime.now().isoformat(),
            'last_activity': datetime.now().isoformat()
        }
        
        # Store session ID in user's browser session
        session['session_id'] = session_id
        
        return jsonify({
            'success': True,
            'session_id': session_id,
            'total_points': len(grid_points),
            'estimated_time_minutes': len(grid_points) * speed_seconds / 60
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/get_current_location')
def get_current_location():
    """Get current scanning location and progress"""
    session_id = session.get('session_id')
    
    if not session_id or session_id not in scanning_sessions:
        return jsonify({'error': 'No active scanning session'})
    
    scan_session = scanning_sessions[session_id]
    current_index = scan_session['current_index']
    grid_points = scan_session['grid_points']
    
    if current_index < len(grid_points):
        current_point = grid_points[current_index]
        progress = (current_index / len(grid_points)) * 100
        
        return jsonify({
            'success': True,
            'current_point': current_point,
            'current_index': current_index,
            'total_points': len(grid_points),
            'progress_percent': round(progress, 1),
            'is_running': scan_session['is_running'],
            'is_paused': scan_session['is_paused']
        })
    else:
        return jsonify({
            'success': True,
            'completed': True,
            'progress_percent': 100
        })


@app.route('/control_scan', methods=['POST'])
def control_scan():
    """Control scanning operations (start, pause, navigate)"""
    session_id = session.get('session_id')
    
    if not session_id or session_id not in scanning_sessions:
        return jsonify({'error': 'No active scanning session'})
    
    action = request.json.get('action')
    scan_session = scanning_sessions[session_id]
    
    if action == 'start':
        scan_session['is_running'] = True
        scan_session['is_paused'] = False
    elif action == 'pause':
        scan_session['is_paused'] = True
    elif action == 'resume':
        scan_session['is_paused'] = False
    elif action == 'stop':
        scan_session['is_running'] = False
        scan_session['is_paused'] = False
    elif action == 'next':
        scan_session['current_index'] = min(
            scan_session['current_index'] + 1,
            len(scan_session['grid_points']) - 1
        )
    elif action == 'previous':
        scan_session['current_index'] = max(scan_session['current_index'] - 1, 0)
    elif action == 'jump':
        index = request.json.get('index', 0)
        scan_session['current_index'] = max(0, min(index, len(scan_session['grid_points']) - 1))
    
    scan_session['last_activity'] = datetime.now().isoformat()
    
    return jsonify({'success': True})


@app.route('/add_bookmark', methods=['POST'])
def add_bookmark():
    """Add a bookmark for current location"""
    session_id = session.get('session_id')
    
    if not session_id or session_id not in scanning_sessions:
        return jsonify({'error': 'No active scanning session'})
    
    scan_session = scanning_sessions[session_id]
    current_index = scan_session['current_index']
    
    if current_index < len(scan_session['grid_points']):
        current_point = scan_session['grid_points'][current_index]
        note = request.json.get('note', 'Potential storage facility')
        
        bookmark = {
            'id': str(uuid.uuid4()),
            'lat': current_point['lat'],
            'lon': current_point['lon'],
            'note': note,
            'grid_index': current_index,
            'timestamp': datetime.now().isoformat(),
            'google_maps_url': current_point['google_maps_url'],
            'street_view_url': f"https://maps.google.com/@{current_point['lat']},{current_point['lon']},3a,75y,0h,90t/data=!3m7!1e1"
        }
        
        scan_session['bookmarks'].append(bookmark)
        scan_session['last_activity'] = datetime.now().isoformat()
        
        return jsonify({'success': True, 'bookmark': bookmark})
    
    return jsonify({'error': 'Invalid location for bookmarking'})


@app.route('/get_bookmarks')
def get_bookmarks():
    """Get all bookmarks for current session"""
    session_id = session.get('session_id')
    
    if not session_id or session_id not in scanning_sessions:
        return jsonify({'error': 'No active scanning session'})
    
    bookmarks = scanning_sessions[session_id]['bookmarks']
    return jsonify({'success': True, 'bookmarks': bookmarks})


@app.route('/export_bookmarks')
def export_bookmarks():
    """Export bookmarks and scan data as JSON"""
    session_id = session.get('session_id')
    
    if not session_id or session_id not in scanning_sessions:
        return jsonify({'error': 'No active scanning session'})
    
    scan_session = scanning_sessions[session_id]
    
    export_data = {
        'scan_info': {
            'center_lat': scan_session['center_lat'],
            'center_lon': scan_session['center_lon'],
            'radius_miles': scan_session['radius_miles'],
            'zoom_level': scan_session['zoom_level'],
            'total_points_scanned': scan_session['current_index'],
            'scan_date': scan_session['created_at']
        },
        'bookmarks': scan_session['bookmarks'],
        'summary': {
            'total_bookmarks': len(scan_session['bookmarks']),
            'areas_scanned': scan_session['current_index'],
            'completion_percentage': (scan_session['current_index'] / len(scan_session['grid_points'])) * 100
        }
    }
    
    return jsonify(export_data)


if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    import os
    os.makedirs('templates', exist_ok=True)
    
    # Write the improved HTML template
    with open('templates/scanner.html', 'w', encoding='utf-8') as f:
        template_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Self-Storage Facility Scanner</title>
    <style>
        body { 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            margin: 0; padding: 20px; background-color: #f8f9fa; line-height: 1.6;
        }
        .container { 
            max-width: 1400px; margin: 0 auto; background: white; 
            padding: 30px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.1); 
        }
        .header { text-align: center; margin-bottom: 30px; }
        .header h1 { color: #2c3e50; font-size: 2.5em; margin-bottom: 10px; }
        .header p { color: #6c757d; font-size: 1.1em; }
        
        .section { 
            margin-bottom: 25px; padding: 20px; border: 2px solid #e9ecef; 
            border-radius: 8px; background-color: #ffffff;
        }
        .section h3 { margin-top: 0; color: #495057; border-bottom: 2px solid #e9ecef; padding-bottom: 10px; }
        
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; margin-bottom: 8px; font-weight: 600; color: #495057; }
        .form-group input, .form-group select { 
            width: 250px; padding: 12px; border: 2px solid #ced4da; 
            border-radius: 6px; font-size: 14px; transition: border-color 0.2s;
        }
        .form-group input:focus, .form-group select:focus {
            outline: none; border-color: #007bff; box-shadow: 0 0 0 3px rgba(0,123,255,0.1);
        }
        
        .controls { display: flex; gap: 12px; margin: 20px 0; flex-wrap: wrap; }
        .btn { 
            padding: 12px 24px; border: none; border-radius: 6px; cursor: pointer; 
            font-size: 14px; font-weight: 600; transition: all 0.2s; text-decoration: none;
            display: inline-block; text-align: center;
        }
        .btn:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0,0,0,0.15); }
        .btn-primary { background-color: #007bff; color: white; }
        .btn-success { background-color: #28a745; color: white; }
        .btn-warning { background-color: #ffc107; color: #212529; }
        .btn-danger { background-color: #dc3545; color: white; }
        .btn-secondary { background-color: #6c757d; color: white; }
        .btn-info { background-color: #17a2b8; color: white; }
        
        .progress-container { margin: 20px 0; }
        .progress-bar { 
            width: 100%; height: 24px; background-color: #e9ecef; 
            border-radius: 12px; overflow: hidden; position: relative;
        }
        .progress-fill { 
            height: 100%; background: linear-gradient(90deg, #007bff, #0056b3); 
            transition: width 0.3s ease; border-radius: 12px;
        }
        .progress-text { text-align: center; margin-top: 8px; font-weight: 600; color: #495057; }
        
        .current-location { 
            padding: 20px; background: linear-gradient(135deg, #e3f2fd, #bbdefb); 
            border-left: 6px solid #2196f3; margin: 20px 0; border-radius: 6px;
        }
        .current-location strong { color: #1565c0; }
        
        .bookmark-item { 
            padding: 15px; margin: 10px 0; background-color: #f8f9fa; 
            border-left: 4px solid #28a745; border-radius: 6px;
        }
        .bookmark-item a { color: #007bff; text-decoration: none; margin-right: 15px; }
        .bookmark-item a:hover { text-decoration: underline; }
        
        .status { 
            padding: 15px; margin: 15px 0; border-radius: 6px; 
            font-weight: 600; text-align: center;
        }
        .status.running { background-color: #d4edda; color: #155724; border: 2px solid #c3e6cb; }
        .status.paused { background-color: #fff3cd; color: #856404; border: 2px solid #ffeaa7; }
        .status.stopped { background-color: #f8d7da; color: #721c24; border: 2px solid #f1b0b7; }
        
        .maps-container { 
            display: grid; grid-template-columns: 1fr 1fr; gap: 15px; 
            margin: 20px 0; min-height: 400px;
        }
        .maps-frame { 
            width: 100%; height: 400px; border: 2px solid #dee2e6; 
            border-radius: 8px;
        }
        .map-option { 
            background: #f8f9fa; padding: 15px; border-radius: 8px; 
            border: 2px solid #e9ecef; margin: 10px 0;
        }
        .map-option h4 { margin: 0 0 10px 0; color: #495057; }
        .map-links { display: flex; gap: 10px; flex-wrap: wrap; }
        
        .hidden { display: none; }
        .bookmark-note { width: 350px; margin-right: 10px; }
        
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }
        .stat-card { background: #f8f9fa; padding: 15px; border-radius: 8px; text-align: center; }
        .stat-number { font-size: 2em; font-weight: bold; color: #007bff; }
        .stat-label { color: #6c757d; font-size: 0.9em; }
        
        .auto-advance { 
            background: #e7f3ff; padding: 15px; border-radius: 8px; 
            border-left: 4px solid #007bff; margin: 15px 0;
        }
        .coordinate-display {
            font-family: monospace; font-size: 1.1em; color: #495057;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏢 Self-Storage Facility Scanner</h1>
            <p>Systematically discover storage facilities in any area</p>
        </div>
        
        <!-- Setup Section -->
        <div class="section" id="setup-section">
            <h3>📍 Configure Scanning Area</h3>
            <div class="form-group">
                <label for="center-lat">Center Latitude:</label>
                <input type="number" step="0.000001" id="center-lat" value="35.4922086" placeholder="e.g., 35.4922086">
            </div>
            <div class="form-group">
                <label for="center-lon">Center Longitude:</label>
                <input type="number" step="0.000001" id="center-lon" value="-94.2260868" placeholder="e.g., -94.2260868">
            </div>
            <div class="form-group">
                <label for="radius">Search Radius (miles):</label>
                <input type="number" step="0.1" id="radius" value="6" min="1" max="20">
            </div>
            <div class="form-group">
                <label for="zoom">Detail Level (Zoom):</label>
                <select id="zoom">
                    <option value="15">15 - Wide overview (1.4 mi view)</option>
                    <option value="16">16 - Neighborhood (0.7 mi view)</option>
                    <option value="17">17 - Block level (0.35 mi view)</option>
                    <option value="18" selected>18 - Building detail (0.17 mi view)</option>
                    <option value="19">19 - Maximum detail (0.09 mi view)</option>
                </select>
            </div>
            <div class="form-group">
                <label for="speed">Scanning Speed (seconds per location):</label>
                <input type="number" step="0.5" id="speed" value="3.0" min="1" max="10">
            </div>
            <button class="btn btn-primary" onclick="setupScan()">🚀 Calculate Scanning Grid</button>
        </div>
        
        <!-- Scanning Section -->
        <div class="section hidden" id="scanning-section">
            <h3>🎮 Scanning Controls</h3>
            
            <div id="status" class="status stopped">Ready to begin scanning</div>
            
            <div class="controls">
                <button class="btn btn-success" onclick="startScan()">▶️ Start Scanning</button>
                <button class="btn btn-warning" onclick="pauseScan()">⏸️ Pause</button>
                <button class="btn btn-success" onclick="resumeScan()">⏯️ Resume</button>
                <button class="btn btn-danger" onclick="stopScan()">⏹️ Stop</button>
            </div>
            
            <div class="controls">
                <button class="btn btn-secondary" onclick="previousLocation()">⏪ Previous Location</button>
                <button class="btn btn-secondary" onclick="nextLocation()">⏩ Next Location</button>
                <button class="btn btn-info" onclick="jumpToLocation()">🎯 Jump to Location</button>
            </div>
            
            <!-- Auto-advance toggle -->
            <div class="auto-advance">
                <label style="display: flex; align-items: center; gap: 10px;">
                    <input type="checkbox" id="auto-advance" onchange="toggleAutoAdvance()">
                    <strong>🤖 Auto-advance every <span id="speed-display">3</span> seconds</strong>
                </label>
                <small style="color: #6c757d;">When enabled, automatically moves to the next location for hands-free scanning</small>
            </div>
            
            <div class="progress-container">
                <div class="progress-bar">
                    <div class="progress-fill" id="progress-fill" style="width: 0%"></div>
                </div>
                <div class="progress-text" id="progress-text">0% complete</div>
            </div>
            
            <div class="current-location" id="current-location">
                <strong>📍 Current Location:</strong> <span class="coordinate-display" id="location-coords">Scanning not started</span><br>
                <strong>📊 Position:</strong> <span id="location-index">0 / 0</span><br>
                <strong>🎯 Distance from center:</strong> <span id="distance-from-center">-</span> miles
            </div>
            
            <!-- Multiple Map Options -->
            <div class="map-option">
                <h4>🗺️ Quick Map Access</h4>
                <div class="map-links">
                    <button class="btn btn-primary" onclick="openInGoogleMaps()">🔍 Google Maps</button>
                    <button class="btn btn-info" onclick="openInBingMaps()">🌍 Bing Maps</button>
                    <button class="btn btn-secondary" onclick="openInOpenStreetMap()">📍 OpenStreetMap</button>
                    <button class="btn btn-success" onclick="openStreetView()">👁️ Street View</button>
                </div>
                <small style="color: #6c757d;">Click any button to open current location in a new tab</small>
            </div>
            
            <!-- Embedded Maps Grid -->
            <div class="maps-container">
                <div>
                    <h4 style="margin: 0 0 10px 0;">📍 OpenStreetMap (Embedded)</h4>
                    <iframe id="osm-frame" class="maps-frame" src="" allowfullscreen="" loading="lazy" 
                            title="OpenStreetMap showing current scanning location"></iframe>
                </div>
                <div>
                    <h4 style="margin: 0 0 10px 0;">🌍 Alternative View</h4>
                    <iframe id="alt-frame" class="maps-frame" src="" allowfullscreen="" loading="lazy" 
                            title="Alternative map view"></iframe>
                </div>
            </div>
            
            <!-- Bookmark Section -->
            <div style="margin-top: 25px; padding: 20px; background-color: #f8f9fa; border-radius: 8px;">
                <h4>📍 Bookmark Current Location</h4>
                <p style="color: #6c757d; margin-bottom: 15px;">
                    Spotted a potential storage facility? Add a bookmark with notes for later review.
                </p>
                <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
                    <input type="text" id="bookmark-note" class="bookmark-note" 
                           placeholder="Describe what you see (e.g., 'Multiple buildings with garage doors')">
                    <button class="btn btn-success" onclick="addBookmark()">📍 Add Bookmark</button>
                </div>
            </div>
        </div>
        
        <!-- Bookmarks Section -->
        <div class="section hidden" id="bookmarks-section">
            <h3>📚 Discovered Locations</h3>
            <div class="stats-grid" id="stats-grid">
                <div class="stat-card">
                    <div class="stat-number" id="bookmark-count">0</div>
                    <div class="stat-label">Bookmarks</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="areas-scanned">0</div>
                    <div class="stat-label">Areas Scanned</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="completion-percent">0%</div>
                    <div class="stat-label">Complete</div>
                </div>
            </div>
            
            <div id="bookmarks-list"></div>
            
            <div style="margin-top: 20px;">
                <button class="btn btn-primary" onclick="exportBookmarks()">💾 Export Results</button>
                <button class="btn btn-secondary" onclick="clearBookmarks()">🗑️ Clear All Bookmarks</button>
            </div>
        </div>
    </div>

    <script>
        let scanInterval = null;
        let autoAdvanceInterval = null;
        let currentSession = null;
        let currentPoint = null;
        
        async function setupScan() {
            const centerLat = parseFloat(document.getElementById('center-lat').value);
            const centerLon = parseFloat(document.getElementById('center-lon').value);
            const radius = parseFloat(document.getElementById('radius').value);
            const zoom = parseInt(document.getElementById('zoom').value);
            const speed = parseFloat(document.getElementById('speed').value);
            
            // Update speed display
            document.getElementById('speed-display').textContent = speed;
            
            // Validation
            if (isNaN(centerLat) || isNaN(centerLon) || isNaN(radius) || isNaN(speed)) {
                alert('Please fill in all fields with valid numbers.');
                return;
            }
            
            if (radius < 1 || radius > 20) {
                alert('Radius must be between 1 and 20 miles.');
                return;
            }
            
            try {
                const response = await fetch('/setup_scan', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        center_lat: centerLat,
                        center_lon: centerLon,
                        radius_miles: radius,
                        zoom_level: zoom,
                        speed_seconds: speed
                    })
                });
                
                const result = await response.json();
                
                if (result.success) {
                    currentSession = result.session_id;
                    document.getElementById('setup-section').style.display = 'none';
                    document.getElementById('scanning-section').classList.remove('hidden');
                    document.getElementById('bookmarks-section').classList.remove('hidden');
                    
                    updateStatus();
                    updateStats();
                    alert(`✅ Scan setup complete!\\n\\n📊 ${result.total_points} locations to scan\\n⏱️ Estimated time: ${result.estimated_time_minutes.toFixed(1)} minutes\\n\\nClick "Start Scanning" when ready!`);
                } else {
                    alert('❌ Setup failed: ' + result.error);
                }
            } catch (error) {
                alert('❌ Setup failed: ' + error.message);
            }
        }
        
        function toggleAutoAdvance() {
            const checkbox = document.getElementById('auto-advance');
            const speed = parseFloat(document.getElementById('speed').value) * 1000; // Convert to milliseconds
            
            if (checkbox.checked) {
                autoAdvanceInterval = setInterval(() => {
                    nextLocation();
                }, speed);
                document.getElementById('status').textContent = '🤖 Auto-scanning in progress...';
            } else {
                if (autoAdvanceInterval) {
                    clearInterval(autoAdvanceInterval);
                    autoAdvanceInterval = null;
                }
            }
        }
        
        async function startScan() {
            await controlScan('start');
            scanInterval = setInterval(updateStatus, 1000);
            document.getElementById('status').className = 'status running';
            document.getElementById('status').textContent = '▶️ Scanning in progress... Watch for storage facilities!';
        }
        
        async function pauseScan() {
            await controlScan('pause');
            if (scanInterval) {
                clearInterval(scanInterval);
                scanInterval = null;
            }
            document.getElementById('status').className = 'status paused';
            document.getElementById('status').textContent = '⏸️ Scan paused - Click Resume to continue';
        }
        
        async function resumeScan() {
            await controlScan('resume');
            scanInterval = setInterval(updateStatus, 1000);
            document.getElementById('status').className = 'status running';
            document.getElementById('status').textContent = '▶️ Scanning resumed... Watch for storage facilities!';
        }
        
        async function stopScan() {
            await controlScan('stop');
            if (scanInterval) {
                clearInterval(scanInterval);
                scanInterval = null;
            }
            if (autoAdvanceInterval) {
                clearInterval(autoAdvanceInterval);
                autoAdvanceInterval = null;
            }
            document.getElementById('auto-advance').checked = false;
            document.getElementById('status').className = 'status stopped';
            document.getElementById('status').textContent = '⏹️ Scan stopped';
        }
        
        async function nextLocation() {
            await controlScan('next');
            updateStatus();
        }
        
        async function previousLocation() {
            await controlScan('previous');
            updateStatus();
        }
        
        async function jumpToLocation() {
            const index = prompt('Enter location number (1 to ' + document.getElementById('location-index').textContent.split(' / ')[1] + '):');
            if (index && !isNaN(index)) {
                await controlScan('jump', parseInt(index) - 1);
                updateStatus();
            }
        }
        
        function openInGoogleMaps() {
            if (currentPoint) {
                window.open(currentPoint.google_maps_url, '_blank');
            }
        }
        
        function openInBingMaps() {
            if (currentPoint) {
                window.open(currentPoint.bing_maps_url, '_blank');
            }
        }
        
        function openInOpenStreetMap() {
            if (currentPoint) {
                window.open(currentPoint.openstreetmap_url, '_blank');
            }
        }
        
        function openStreetView() {
            if (currentPoint) {
                const streetViewUrl = `https://maps.google.com/@${currentPoint.lat},${currentPoint.lon},3a,75y,0h,90t/data=!3m7!1e1`;
                window.open(streetViewUrl, '_blank');
            }
        }
        
        async function controlScan(action, index = null) {
            try {
                const body = { action: action };
                if (index !== null) body.index = index;
                
                await fetch('/control_scan', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(body)
                });
            } catch (error) {
                console.error('Control action failed:', error);
            }
        }
        
        async function updateStatus() {
            try {
                const response = await fetch('/get_current_location');
                const result = await response.json();
                
                if (result.success) {
                    if (result.completed) {
                        document.getElementById('progress-fill').style.width = '100%';
                        document.getElementById('progress-text').textContent = '🎉 100% complete - Scan finished!';
                        if (scanInterval) {
                            clearInterval(scanInterval);
                            scanInterval = null;
                        }
                        if (autoAdvanceInterval) {
                            clearInterval(autoAdvanceInterval);
                            autoAdvanceInterval = null;
                        }
                        document.getElementById('auto-advance').checked = false;
                        document.getElementById('status').className = 'status stopped';
                        document.getElementById('status').textContent = '✅ Scan completed! Review your bookmarks below.';
                    } else {
                        currentPoint = result.current_point;
                        document.getElementById('progress-fill').style.width = result.progress_percent + '%';
                        document.getElementById('progress-text').textContent = `${result.progress_percent}% complete`;
                        document.getElementById('location-coords').textContent = `${currentPoint.lat}, ${currentPoint.lon}`;
                        document.getElementById('location-index').textContent = `${result.current_index + 1} / ${result.total_points}`;
                        document.getElementById('distance-from-center').textContent = currentPoint.distance_from_center;
                        
                        // Update embedded maps
                        updateEmbeddedMaps(currentPoint);
                    }
                    updateStats();
                }
            } catch (error) {
                console.error('Status update failed:', error);
            }
        }
        
        function updateEmbeddedMaps(point) {
            // Update OpenStreetMap iframe
            const osmUrl = `https://www.openstreetmap.org/export/embed.html?bbox=${point.lon-0.005},${point.lat-0.005},${point.lon+0.005},${point.lat+0.005}&layer=mapnik&marker=${point.lat},${point.lon}`;
            document.getElementById('osm-frame').src = osmUrl;
            
            // Update alternative map (Bing Maps embed)
            const bingEmbedUrl = `https://www.bing.com/maps/embed?h=400&w=500&cp=${point.lat}~${point.lon}&lvl=18&typ=s&sty=r&src=SHELL&FORM=MBEDV8`;
            document.getElementById('alt-frame').src = bingEmbedUrl;
        }
        
        async function addBookmark() {
            const note = document.getElementById('bookmark-note').value || 'Potential storage facility';
            
            try {
                const response = await fetch('/add_bookmark', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({note: note})
                });
                
                const result = await response.json();
                
                if (result.success) {
                    document.getElementById('bookmark-note').value = '';
                    updateBookmarks();
                    updateStats();
                    
                    // Visual feedback
                    const btn = document.querySelector('button[onclick="addBookmark()"]');
                    const originalText = btn.textContent;
                    btn.textContent = '✅ Bookmarked!';
                    btn.style.backgroundColor = '#28a745';
                    setTimeout(() => {
                        btn.textContent = originalText;
                        btn.style.backgroundColor = '';
                    }, 2000);
                } else {
                    alert('❌ Bookmark failed: ' + result.error);
                }
            } catch (error) {
                alert('❌ Bookmark failed: ' + error.message);
            }
        }
        
        async function updateBookmarks() {
            try {
                const response = await fetch('/get_bookmarks');
                const result = await response.json();
                
                if (result.success) {
                    const bookmarksList = document.getElementById('bookmarks-list');
                    bookmarksList.innerHTML = '';
                    
                    if (result.bookmarks.length === 0) {
                        bookmarksList.innerHTML = '<p style="color: #6c757d; text-align: center; padding: 20px;">No bookmarks yet. Start scanning and bookmark interesting locations!</p>';
                        return;
                    }
                    
                    result.bookmarks.forEach((bookmark, index) => {
                        const div = document.createElement('div');
                        div.className = 'bookmark-item';
                        div.innerHTML = `
                            <div style="display: flex; justify-content: between; align-items: flex-start;">
                                <div style="flex-grow: 1;">
                                    <strong>📍 Location ${index + 1}:</strong> ${bookmark.note}<br>
                                    <strong>🌍 Coordinates:</strong> <span class="coordinate-display">${bookmark.lat}, ${bookmark.lon}</span><br>
                                    <strong>🕒 Time:</strong> ${new Date(bookmark.timestamp).toLocaleString()}<br>
                                    <div style="margin-top: 10px;">
                                        <a href="${bookmark.google_maps_url}" target="_blank">🗺️ Google Maps</a>
                                        <a href="${bookmark.street_view_url}" target="_blank">👁️ Street View</a>
                                        <button class="btn btn-info" style="padding: 5px 10px; font-size: 12px;" onclick="jumpToBookmark(${bookmark.grid_index})">🎯 Go to Location</button>
                                    </div>
                                </div>
                            </div>
                        `;
                        bookmarksList.appendChild(div);
                    });
                }
            } catch (error) {
                console.error('Bookmark update failed:', error);
            }
        }
        
        async function jumpToBookmark(gridIndex) {
            await controlScan('jump', gridIndex);
            updateStatus();
        }
        
        async function updateStats() {
            try {
                const bookmarksResponse = await fetch('/get_bookmarks');
                const statusResponse = await fetch('/get_current_location');
                
                const bookmarksResult = await bookmarksResponse.json();
                const statusResult = await statusResponse.json();
                
                if (bookmarksResult.success) {
                    document.getElementById('bookmark-count').textContent = bookmarksResult.bookmarks.length;
                }
                
                if (statusResult.success) {
                    document.getElementById('areas-scanned').textContent = statusResult.current_index || 0;
                    document.getElementById('completion-percent').textContent = 
                        (statusResult.progress_percent || 0).toFixed(0) + '%';
                }
            } catch (error) {
                console.error('Stats update failed:', error);
            }
        }
        
        async function exportBookmarks() {
            try {
                const response = await fetch('/export_bookmarks');
                const result = await response.json();
                
                const blob = new Blob([JSON.stringify(result, null, 2)], {type: 'application/json'});
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `storage_facility_scan_${new Date().toISOString().split('T')[0]}.json`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
                
                alert('📁 Results exported successfully!');
            } catch (error) {
                alert('❌ Export failed: ' + error.message);
            }
        }
        
        async function clearBookmarks() {
            if (confirm('Are you sure you want to clear all bookmarks? This cannot be undone.')) {
                location.reload();
            }
        }
        
        // Auto-update bookmarks and stats every 5 seconds
        setInterval(() => {
            if (currentSession) {
                updateBookmarks();
                updateStats();
            }
        }, 5000);
        
        // Initialize on page load
        document.addEventListener('DOMContentLoaded', function() {
            document.getElementById('center-lat').focus();
        });
        
        // Keyboard shortcuts
        document.addEventListener('keydown', function(e) {
            if (e.ctrlKey || e.metaKey) {
                switch(e.key) {
                    case 'ArrowLeft':
                        e.preventDefault();
                        previousLocation();
                        break;
                    case 'ArrowRight':
                        e.preventDefault();
                        nextLocation();
                        break;
                    case ' ':
                        e.preventDefault();
                        addBookmark();
                        break;
                }
            }
        });
    </script>
</body>
</html>'''
        f.write(template_content)
    
    print("🚀 Starting Self-Storage Facility Scanner...")
    print("📍 Access the app at: http://localhost:5000")
    print("🌐 Ready for deployment!")
    
    # Get port from environment variable (Railway sets this)
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
