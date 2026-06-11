import { useEffect, useRef, useState } from 'react';
import { useSelector } from 'react-redux';
import type { RootState } from '../store';
import L from 'leaflet';
import mapboxgl from 'mapbox-gl';

// Circle coordinate mappings for revenue circles in Lakhimpur
const CIRCLE_COORDS: Record<string, [number, number]> = {
  'Gogamukh': [27.2700, 94.1300],
  'Sisiborgaon': [27.2100, 94.0700],
  'Naoboicha': [27.2500, 94.0200],
  'Bihpuria': [26.9800, 93.9000],
  'Lakhimpur': [27.2300, 94.1000],
  'Laluk': [27.2200, 93.9200],
  'Kadam': [27.2800, 94.0500],
  'Dhakuakhana': [27.1200, 94.2800],
};

// SVG Path Constants for Custom Markers
const HELI_PATH = 'M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10 10-4.5 10-10S17.5 2 12 2zm1 15.5c0 .3-.2.5-.5.5s-.5-.2-.5-.5V14h1v3.5zm3-5.5h-2.1l1.5 2.1c.1.2.1.5-.1.7-.2.2-.5.2-.7.1L12.5 12h-1l-2.2 2.9c-.2.1-.5.1-.7-.1-.2-.2-.2-.5-.1-.7l1.5-2.1H8c-.6 0-1-.4-1-1s.4-1 1-1h6c.6 0 1 .4 1 1s-.4 1-1 1z';
const BOAT_PATH = 'M4 16h16c.6 0 1-.4 1-1s-.4-1-1-1h-1v-4c0-1.1-.9-2-2-2h-3v-2c0-.6-.4-1-1-1s-1 .4-1 1v2H9c-1.1 0-2 .9-2 2v4H6c-.6 0-1 .4-1 1s.4 1 1 1zm8-10a2 2 0 1 0 0-4 2 2 0 0 0 0 4zm-9 12h18c.6 0 1-.4 1-1v-1H2v1c0 .6.4 1 1 1z';
const TRUCK_PATH = 'M20 8h-3V4H3c-1.1 0-2 .9-2 2v11h2c0 1.66 1.34 3 3 3s3-1.34 3-3h6c0 1.66 1.34 3 3 3s3-1.34 3-3h2v-5l-3-4zM6 18.5c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zm12 0c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5z';
const MED_PATH = 'M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-2 10h-4v4h-2v-4H7v-2h4V7h2v4h4v2z';
const SHELTER_PATH = 'M12 3L2 12h3v8h6v-6h2v6h6v-8h3L12 3zm0 7.5a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3z';

const statusColors = {
  available: '#22d3ee',   // Cyan
  dispatched: '#eab308',  // Yellow
  maintenance: '#64748b', // Slate
};

// Helper function to generate a circle polygon for Mapbox
function createGeoJSONCircle(center: [number, number], radiusInKm: number, points = 64) {
  const [longitude, latitude] = center;
  const km = radiusInKm;
  const ret = [];
  const distanceX = km / (111.32 * Math.cos((latitude * Math.PI) / 180));
  const distanceY = km / 110.57;

  for (let i = 0; i < points; i++) {
    const theta = (i / points) * (2 * Math.PI);
    const x = distanceX * Math.cos(theta);
    const y = distanceY * Math.sin(theta);
    ret.push([longitude + x, latitude + y]);
  }
  ret.push(ret[0]); // Close polygon
  return {
    type: 'Feature',
    geometry: {
      type: 'Polygon',
      coordinates: [ret]
    },
    properties: {}
  };
}

export function LiveMap() {
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  
  // Leaflet Refs
  const leafletMapRef = useRef<L.Map | null>(null);
  const markerGroupRef = useRef<L.FeatureGroup | null>(null);
  const overlayGroupRef = useRef<L.FeatureGroup | null>(null);
  const linesGroupRef = useRef<L.FeatureGroup | null>(null);

  // Mapbox Refs
  const mapboxMapRef = useRef<mapboxgl.Map | null>(null);
  const mapboxMarkersRef = useRef<mapboxgl.Marker[]>([]);
  const [mapboxStyleLoaded, setMapboxStyleLoaded] = useState(false);

  const { resources, shelters, sosQueue, alerts } = useSelector((state: RootState) => state.disaster);

  // Extract Mapbox token
  const mapboxToken = (import.meta.env.VITE_MAPBOX_TOKEN || '').trim();
  const hasMapboxToken = mapboxToken.startsWith('pk.');

  // Initialize Map (Leaflet or Mapbox)
  useEffect(() => {
    if (!mapContainerRef.current) return;

    // Lakhimpur coordinates
    const startCoords: [number, number] = [27.23, 94.10];

    if (hasMapboxToken) {
      // Mapbox GL JS Map
      if (mapboxMapRef.current) return;

      mapboxgl.accessToken = mapboxToken;
      const map = new mapboxgl.Map({
        container: mapContainerRef.current,
        style: 'mapbox://styles/mapbox/satellite-streets-v12',
        center: [startCoords[1], startCoords[0]], // [lng, lat]
        zoom: 11,
      });

      map.addControl(new mapboxgl.NavigationControl({ showCompass: false }), 'bottom-right');

      map.on('style.load', () => {
        setMapboxStyleLoaded(true);
      });

      mapboxMapRef.current = map;
    } else {
      // Leaflet Map fallback
      if (leafletMapRef.current) return;

      const map = L.map(mapContainerRef.current, {
        center: startCoords,
        zoom: 12,
        zoomControl: false,
      });

      L.control.zoom({ position: 'bottomright' }).addTo(map);

      // High-tech dark mode tile layer (CartoDB Dark Matter)
      L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
        maxZoom: 20,
      }).addTo(map);

      markerGroupRef.current = L.featureGroup().addTo(map);
      overlayGroupRef.current = L.featureGroup().addTo(map);
      linesGroupRef.current = L.featureGroup().addTo(map);

      leafletMapRef.current = map;
    }

    return () => {
      if (mapboxMapRef.current) {
        mapboxMapRef.current.remove();
        mapboxMapRef.current = null;
        setMapboxStyleLoaded(false);
      }
      if (leafletMapRef.current) {
        leafletMapRef.current.remove();
        leafletMapRef.current = null;
      }
    };
  }, [hasMapboxToken, mapboxToken]);

  // Update map content when data changes
  useEffect(() => {
    const severityColors = {
      low: '#10b981',      // Green
      moderate: '#f97316', // Orange
      high: '#ef4444',     // Red
      critical: '#7f1d1d', // Dark Red
    };

    if (hasMapboxToken) {
      const map = mapboxMapRef.current;
      if (!map || !mapboxStyleLoaded) return;

      // 1. Clear Mapbox markers
      mapboxMarkersRef.current.forEach((m) => m.remove());
      mapboxMarkersRef.current = [];

      // 2. Clear Mapbox layers and sources
      const style = map.getStyle();
      if (style && style.layers) {
        style.layers.forEach((layer) => {
          if (layer.id.startsWith('alert-') || layer.id.startsWith('line-sos-')) {
            map.removeLayer(layer.id);
          }
        });
      }
      if (style && style.sources) {
        Object.keys(style.sources).forEach((sourceId) => {
          if (sourceId.startsWith('alert-') || sourceId.startsWith('line-sos-')) {
            map.removeSource(sourceId);
          }
        });
      }

      // 3. Draw prediction zones (Alerts)
      alerts.forEach((alert, alertIdx) => {
        const color = severityColors[alert.severity] || '#3b82f6';
        alert.affected_circles.forEach((circleName) => {
          const coords = CIRCLE_COORDS[circleName];
          if (coords) {
            const radiusKm = alert.severity === 'critical' ? 4 : alert.severity === 'high' ? 3 : 2;
            const sourceId = `alert-${alertIdx}-${circleName}`;
            const circleGeoJSON = createGeoJSONCircle([coords[1], coords[0]], radiusKm);

            map.addSource(sourceId, {
              type: 'geojson',
              data: circleGeoJSON as any,
            });

            map.addLayer({
              id: `${sourceId}-fill`,
              type: 'fill',
              source: sourceId,
              paint: {
                'fill-color': color,
                'fill-opacity': 0.15,
              },
            });

            map.addLayer({
              id: `${sourceId}-stroke`,
              type: 'line',
              source: sourceId,
              paint: {
                'line-color': color,
                'line-width': 1.5,
                'line-dasharray': [3, 3],
              },
            });
          }
        });
      });

      // 4. Draw Shelters
      Object.values(shelters).forEach((shelter) => {
        const occupancyPct = (shelter.current_occupancy / shelter.capacity) * 100;
        const statusColor = occupancyPct < 70 ? '#10b981' : occupancyPct <= 85 ? '#eab308' : '#ef4444';

        const el = document.createElement('div');
        el.className = 'custom-div-icon';
        el.innerHTML = `
          <div class="relative flex items-center justify-center w-8 h-8 rounded-lg bg-slate-900 border-2 border-slate-700 shadow-lg cursor-pointer hover:scale-110 transition-transform">
            <svg class="w-5 h-5" viewBox="0 0 24 24" fill="${statusColor}">
              <path d="${SHELTER_PATH}"/>
            </svg>
            <div class="absolute -bottom-1 -right-1 w-3.5 h-3.5 rounded-full border border-slate-900 flex items-center justify-center text-[8px] font-bold text-slate-950 font-mono" style="background-color: ${statusColor}">
              ${Math.round(occupancyPct)}
            </div>
          </div>
        `;

        const popupContent = `
          <div class="p-2 text-slate-100 font-sans min-w-[180px]">
            <h4 class="font-bold text-sm text-cyan-400 mb-2">${shelter.name}</h4>
            <div class="space-y-1.5 text-xs">
              <div class="flex justify-between items-center bg-slate-950/40 p-1 px-1.5 rounded">
                <span class="text-slate-400">Occupancy:</span>
                <span class="font-bold font-mono text-slate-200">${shelter.current_occupancy}/${shelter.capacity} (${Math.round(occupancyPct)}%)</span>
              </div>
              <div class="w-full bg-slate-800 rounded-full h-1.5">
                <div class="h-1.5 rounded-full" style="width: ${Math.min(occupancyPct, 100)}%; background-color: ${statusColor}"></div>
              </div>
              <div class="grid grid-cols-3 gap-1 pt-1.5 font-mono text-[10px] text-center">
                <div class="bg-slate-800/60 p-1 rounded">
                  <div class="text-[9px] text-slate-400">FOOD</div>
                  <div class="font-bold text-slate-200">${shelter.food_stock}u</div>
                </div>
                <div class="bg-slate-800/60 p-1 rounded">
                  <div class="text-[9px] text-slate-400">WATER</div>
                  <div class="font-bold text-slate-200">${shelter.water_stock}L</div>
                </div>
                <div class="bg-slate-800/60 p-1 rounded">
                  <div class="text-[9px] text-slate-400">MED</div>
                  <div class="font-bold text-slate-200">${shelter.medicine_stock}k</div>
                </div>
              </div>
            </div>
          </div>
        `;

        const marker = new mapboxgl.Marker({ element: el })
          .setLngLat([shelter.lng, shelter.lat])
          .setPopup(new mapboxgl.Popup({ offset: 15, className: 'mapbox-custom-popup' }).setHTML(popupContent))
          .addTo(map);

        mapboxMarkersRef.current.push(marker);
      });

      // 5. Draw SOS Events
      sosQueue.forEach((sos) => {
        if (sos.status === 'rescued') return;
        const colorHex = sos.triage_level === 1 ? '#ef4444' : sos.triage_level <= 3 ? '#f97316' : '#eab308';

        const el = document.createElement('div');
        el.className = 'custom-div-icon';
        el.innerHTML = `
          <div class="relative flex items-center justify-center w-8 h-8">
            <span class="absolute w-6 h-6 rounded-full opacity-75 ${sos.triage_level === 1 ? 'animate-radar-red' : 'animate-radar-cyan'}" style="background-color: ${colorHex}55"></span>
            <div class="relative w-4 h-4 rounded-full flex items-center justify-center border-2 border-slate-900 shadow" style="background-color: ${colorHex}">
              <span class="text-[8px] font-bold text-slate-950 font-mono">${sos.people_count}</span>
            </div>
          </div>
        `;

        const popupContent = `
          <div class="p-2 text-slate-100 font-sans min-w-[200px]">
            <div class="flex items-center justify-between mb-2">
              <span class="px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                sos.triage_level === 1 ? 'bg-red-500/20 text-red-400 border border-red-500/30' : 'bg-orange-500/20 text-orange-400 border border-orange-500/30'
              }">Triage L${sos.triage_level}</span>
              <span class="text-xs font-mono text-slate-400">SOS #${sos.id}</span>
            </div>
            <div class="space-y-1 text-xs">
              <div><span class="text-slate-400">Phone:</span> <span class="font-mono">${sos.phone}</span></div>
              <div><span class="text-slate-400">Survivors:</span> <span class="font-bold text-slate-200 font-mono">${sos.people_count}</span></div>
              <div class="bg-slate-950/50 p-1.5 rounded mt-1.5 border border-slate-800 text-slate-300">
                ${sos.injury_description || 'Stranded survivor. Immediate rescue required.'}
              </div>
              <div class="pt-2 text-slate-400 flex items-center gap-1.5">
                <span class="w-1.5 h-1.5 rounded-full ${sos.status === 'assigned' ? 'bg-cyan-500 animate-pulse' : 'bg-yellow-500'}"></span>
                <span class="uppercase tracking-wider text-[10px] font-semibold">${sos.status}</span>
                ${sos.assigned_resource_name ? `<span class="text-cyan-400 font-mono">(${sos.assigned_resource_name} - ~${sos.eta_minutes}m)</span>` : ''}
              </div>
            </div>
          </div>
        `;

        const marker = new mapboxgl.Marker({ element: el })
          .setLngLat([sos.lng, sos.lat])
          .setPopup(new mapboxgl.Popup({ offset: 15, className: 'mapbox-custom-popup' }).setHTML(popupContent))
          .addTo(map);

        mapboxMarkersRef.current.push(marker);

        // Draw active rescue lines
        if (sos.status === 'assigned' && sos.assigned_resource_id) {
          const assignedRes = resources[sos.assigned_resource_id];
          if (assignedRes) {
            const sourceId = `line-sos-${sos.id}`;
            map.addSource(sourceId, {
              type: 'geojson',
              data: {
                type: 'Feature',
                properties: {},
                geometry: {
                  type: 'LineString',
                  coordinates: [
                    [assignedRes.lng, assignedRes.lat],
                    [sos.lng, sos.lat],
                  ],
                },
              },
            });

            map.addLayer({
              id: `${sourceId}-layer`,
              type: 'line',
              source: sourceId,
              paint: {
                'line-color': '#06b6d4',
                'line-width': 2,
                'line-dasharray': [3, 3],
              },
            });
          }
        }
      });

      // 6. Draw Resources
      Object.values(resources).forEach((resource) => {
        const color = statusColors[resource.status] || '#cbd5e1';

        let svgPath = TRUCK_PATH;
        if (resource.type === 'helicopter') svgPath = HELI_PATH;
        else if (resource.type === 'boat') svgPath = BOAT_PATH;
        else if (resource.type === 'medical_team') svgPath = MED_PATH;

        const el = document.createElement('div');
        el.className = 'custom-div-icon';
        el.innerHTML = `
          <div class="relative flex items-center justify-center w-8 h-8 rounded-full bg-slate-950 border-2 cursor-pointer shadow-lg hover:scale-110 transition-transform" style="border-color: ${color}">
            <svg class="w-4 h-4" viewBox="0 0 24 24" fill="${color}">
              <path d="${svgPath}"/>
            </svg>
            <span class="absolute -top-1 -right-1 px-1 rounded bg-slate-900 text-[8px] font-extrabold border border-slate-700 font-mono" style="color: ${color}">
              ${resource.name}
            </span>
          </div>
        `;

        const popupContent = `
          <div class="p-2 text-slate-100 font-sans min-w-[180px]">
            <div class="flex items-center justify-between mb-1.5">
              <h4 class="font-bold text-sm text-slate-100">${resource.name} (${resource.type.toUpperCase().replace('_', ' ')})</h4>
              <span class="px-1.5 py-0.5 rounded text-[9px] font-mono font-bold uppercase" style="background-color: ${color}22; color: ${color}; border: 1px solid ${color}44">
                ${resource.status}
              </span>
            </div>
            <div class="space-y-1 text-xs">
              <div class="text-[10px] text-slate-400 font-mono">POS: ${resource.lat.toFixed(4)}, ${resource.lng.toFixed(4)}</div>
              <div class="border-t border-slate-800 pt-1.5 mt-1">
                <span class="text-slate-400 font-semibold block mb-1">Equipment / Inventory:</span>
                ${
                  Object.keys(resource.inventory).length > 0
                    ? `<div class="grid grid-cols-2 gap-1 font-mono text-[10px]">
                        ${Object.entries(resource.inventory).map(([k, v]) => `
                          <div class="bg-slate-900/50 p-1 rounded text-center border border-slate-800/40">
                            <span class="text-slate-500 uppercase">${k.replace('_', ' ')}:</span>
                            <span class="font-bold text-slate-300 ml-1">${v}</span>
                          </div>
                        `).join('')}
                       </div>`
                    : '<span class="text-slate-500 italic text-[10px]">No equipment loaded</span>'
                }
              </div>
            </div>
          </div>
        `;

        const marker = new mapboxgl.Marker({ element: el })
          .setLngLat([resource.lng, resource.lat])
          .setPopup(new mapboxgl.Popup({ offset: 15, className: 'mapbox-custom-popup' }).setHTML(popupContent))
          .addTo(map);

        mapboxMarkersRef.current.push(marker);
      });

    } else {
      // Leaflet update logic
      const map = leafletMapRef.current;
      const markerGroup = markerGroupRef.current;
      const overlayGroup = overlayGroupRef.current;
      const linesGroup = linesGroupRef.current;

      if (!map || !markerGroup || !overlayGroup || !linesGroup) return;

      markerGroup.clearLayers();
      overlayGroup.clearLayers();
      linesGroup.clearLayers();

      // Draw alerts
      alerts.forEach((alert) => {
        const color = severityColors[alert.severity] || '#3b82f6';
        alert.affected_circles.forEach((circleName) => {
          const coords = CIRCLE_COORDS[circleName];
          if (coords) {
            const radius = alert.severity === 'critical' ? 4000 : alert.severity === 'high' ? 3000 : 2000;
            L.circle(coords, {
              radius,
              color,
              weight: 1.5,
              fillColor: color,
              fillOpacity: 0.18,
              dashArray: '5, 5',
            })
              .bindPopup(`
                <div class="p-1 text-slate-100 font-sans">
                  <div class="flex items-center gap-2 mb-1">
                    <span class="w-2 h-2 rounded-full" style="background-color: ${color}"></span>
                    <span class="font-bold uppercase tracking-wider text-xs">${alert.severity} Risk</span>
                  </div>
                  <h4 class="text-sm font-semibold mb-1">${circleName} Circle</h4>
                  <div class="text-xs text-slate-400 font-mono">
                    <div>FHI Score: ${alert.fhi_score?.toFixed(2) || '0.00'}</div>
                    <div>Discharge: ${alert.discharge_q || '0'} m³/s</div>
                  </div>
                </div>
              `)
              .addTo(overlayGroup);
          }
        });
      });

      // Draw Shelters
      Object.values(shelters).forEach((shelter) => {
        const occupancyPct = (shelter.current_occupancy / shelter.capacity) * 100;
        const statusColor = occupancyPct < 70 ? '#10b981' : occupancyPct <= 85 ? '#eab308' : '#ef4444';

        const customIcon = L.divIcon({
          className: 'custom-div-icon',
          html: `
            <div class="relative flex items-center justify-center w-8 h-8 rounded-lg bg-slate-900 border-2 border-slate-700 shadow-lg cursor-pointer hover:scale-110 transition-transform">
              <svg class="w-5 h-5" viewBox="0 0 24 24" fill="${statusColor}">
                <path d="${SHELTER_PATH}"/>
              </svg>
              <div class="absolute -bottom-1 -right-1 w-3.5 h-3.5 rounded-full border border-slate-900 flex items-center justify-center text-[8px] font-bold text-slate-950 font-mono" style="background-color: ${statusColor}">
                ${Math.round(occupancyPct)}
              </div>
            </div>
          `,
          iconSize: [32, 32],
          iconAnchor: [16, 16],
        });

        L.marker([shelter.lat, shelter.lng], { icon: customIcon })
          .bindPopup(`
            <div class="p-2 text-slate-100 font-sans min-w-[180px]">
              <h4 class="font-bold text-sm text-cyan-400 mb-2">${shelter.name}</h4>
              <div class="space-y-1.5 text-xs">
                <div class="flex justify-between items-center bg-slate-950/40 p-1 px-1.5 rounded">
                  <span class="text-slate-400">Occupancy:</span>
                  <span class="font-bold font-mono text-slate-200">${shelter.current_occupancy}/${shelter.capacity} (${Math.round(occupancyPct)}%)</span>
                </div>
                <div class="w-full bg-slate-800 rounded-full h-1.5">
                  <div class="h-1.5 rounded-full" style="width: ${Math.min(occupancyPct, 100)}%; background-color: ${statusColor}"></div>
                </div>
                <div class="grid grid-cols-3 gap-1 pt-1.5 font-mono text-[10px] text-center">
                  <div class="bg-slate-800/60 p-1 rounded">
                    <div class="text-[9px] text-slate-400">FOOD</div>
                    <div class="font-bold text-slate-200">${shelter.food_stock}u</div>
                  </div>
                  <div class="bg-slate-800/60 p-1 rounded">
                    <div class="text-[9px] text-slate-400">WATER</div>
                    <div class="font-bold text-slate-200">${shelter.water_stock}L</div>
                  </div>
                  <div class="bg-slate-800/60 p-1 rounded">
                    <div class="text-[9px] text-slate-400">MED</div>
                    <div class="font-bold text-slate-200">${shelter.medicine_stock}k</div>
                  </div>
                </div>
              </div>
            </div>
          `)
          .addTo(markerGroup);
      });

      // Draw SOS Events
      sosQueue.forEach((sos) => {
        if (sos.status === 'rescued') return;
        const colorHex = sos.triage_level === 1 ? '#ef4444' : sos.triage_level <= 3 ? '#f97316' : '#eab308';

        const customIcon = L.divIcon({
          className: 'custom-div-icon',
          html: `
            <div class="relative flex items-center justify-center w-8 h-8">
              <span class="absolute w-6 h-6 rounded-full opacity-75 ${sos.triage_level === 1 ? 'animate-radar-red' : 'animate-radar-cyan'}" style="background-color: ${colorHex}55"></span>
              <div class="relative w-4 h-4 rounded-full flex items-center justify-center border-2 border-slate-900 shadow" style="background-color: ${colorHex}">
                <span class="text-[8px] font-bold text-slate-950 font-mono">${sos.people_count}</span>
              </div>
            </div>
          `,
          iconSize: [32, 32],
          iconAnchor: [16, 16],
        });

        L.marker([sos.lat, sos.lng], { icon: customIcon })
          .bindPopup(`
            <div class="p-2 text-slate-100 font-sans min-w-[200px]">
              <div class="flex items-center justify-between mb-2">
                <span class="px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                  sos.triage_level === 1 ? 'bg-red-500/20 text-red-400 border border-red-500/30' : 'bg-orange-500/20 text-orange-400 border border-orange-500/30'
                }">Triage L${sos.triage_level}</span>
                <span class="text-xs font-mono text-slate-400">SOS #${sos.id}</span>
              </div>
              <div class="space-y-1 text-xs">
                <div><span class="text-slate-400">Phone:</span> <span class="font-mono">${sos.phone}</span></div>
                <div><span class="text-slate-400">Survivors:</span> <span class="font-bold text-slate-200 font-mono">${sos.people_count}</span></div>
                <div class="bg-slate-950/50 p-1.5 rounded mt-1.5 border border-slate-800 text-slate-300">
                  ${sos.injury_description || 'Stranded survivor. Immediate rescue required.'}
                </div>
                <div class="pt-2 text-slate-400 flex items-center gap-1.5">
                  <span class="w-1.5 h-1.5 rounded-full ${sos.status === 'assigned' ? 'bg-cyan-500 animate-pulse' : 'bg-yellow-500'}"></span>
                  <span class="uppercase tracking-wider text-[10px] font-semibold">${sos.status}</span>
                  ${sos.assigned_resource_name ? `<span class="text-cyan-400 font-mono">(${sos.assigned_resource_name} - ~${sos.eta_minutes}m)</span>` : ''}
                </div>
              </div>
            </div>
          `)
          .addTo(markerGroup);

        if (sos.status === 'assigned' && sos.assigned_resource_id) {
          const assignedRes = resources[sos.assigned_resource_id];
          if (assignedRes) {
            L.polyline([[assignedRes.lat, assignedRes.lng], [sos.lat, sos.lng]], {
              color: '#06b6d4',
              weight: 2,
              opacity: 0.8,
              dashArray: '6, 6',
            }).addTo(linesGroup);
          }
        }
      });

      // Draw Resources
      Object.values(resources).forEach((resource) => {
        const color = statusColors[resource.status] || '#cbd5e1';

        let svgPath = TRUCK_PATH;
        if (resource.type === 'helicopter') svgPath = HELI_PATH;
        else if (resource.type === 'boat') svgPath = BOAT_PATH;
        else if (resource.type === 'medical_team') svgPath = MED_PATH;

        const customIcon = L.divIcon({
          className: 'custom-div-icon',
          html: `
            <div class="relative flex items-center justify-center w-8 h-8 rounded-full bg-slate-950 border-2 cursor-pointer shadow-lg hover:scale-110 transition-transform" style="border-color: ${color}">
              <svg class="w-4 h-4" viewBox="0 0 24 24" fill="${color}">
                <path d="${svgPath}"/>
              </svg>
              <span class="absolute -top-1 -right-1 px-1 rounded bg-slate-900 text-[8px] font-extrabold border border-slate-700 font-mono" style="color: ${color}">
                ${resource.name}
              </span>
            </div>
          `,
          iconSize: [32, 32],
          iconAnchor: [16, 16],
        });

        L.marker([resource.lat, resource.lng], { icon: customIcon })
          .bindPopup(`
            <div class="p-2 text-slate-100 font-sans min-w-[180px]">
              <div class="flex items-center justify-between mb-1.5">
                <h4 class="font-bold text-sm text-slate-100">${resource.name} (${resource.type.toUpperCase().replace('_', ' ')})</h4>
                <span class="px-1.5 py-0.5 rounded text-[9px] font-mono font-bold uppercase" style="background-color: ${color}22; color: ${color}; border: 1px solid ${color}44">
                  ${resource.status}
                </span>
              </div>
              <div class="space-y-1 text-xs">
                <div class="text-[10px] text-slate-400 font-mono">POS: ${resource.lat.toFixed(4)}, ${resource.lng.toFixed(4)}</div>
                <div class="border-t border-slate-800 pt-1.5 mt-1">
                  <span class="text-slate-400 font-semibold block mb-1">Equipment / Inventory:</span>
                  ${
                    Object.keys(resource.inventory).length > 0
                      ? `<div class="grid grid-cols-2 gap-1 font-mono text-[10px]">
                          ${Object.entries(resource.inventory).map(([k, v]) => `
                            <div class="bg-slate-900/50 p-1 rounded text-center border border-slate-800/40">
                              <span class="text-slate-500 uppercase">${k.replace('_', ' ')}:</span>
                              <span class="font-bold text-slate-300 ml-1">${v}</span>
                            </div>
                          `).join('')}
                         </div>`
                      : '<span class="text-slate-500 italic text-[10px]">No equipment loaded</span>'
                  }
                </div>
              </div>
            </div>
          `)
          .addTo(markerGroup);
      });
    }
  }, [resources, shelters, sosQueue, alerts, hasMapboxToken, mapboxStyleLoaded]);

  return (
    <div className="relative w-full h-full rounded-xl overflow-hidden border border-slate-800/70 shadow-2xl">
      <div ref={mapContainerRef} className="w-full h-full" />
      
      {/* Map Legend Overlay */}
      <div className="absolute bottom-4 left-4 z-[1000] eoc-card p-3 rounded-lg border border-slate-800 text-[10px] space-y-2 max-w-[160px]">
        <h5 className="font-display font-bold uppercase tracking-wider text-slate-400 mb-1 border-b border-slate-800 pb-1">COMMAND LEGEND</h5>
        <div className="space-y-1.5 text-slate-300 font-medium">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-safe-green inline-block border border-white/20"></span>
            <span>Safe Area (&lt;70%)</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-watch-yellow inline-block border border-white/20"></span>
            <span>Watch Zone (70-85%)</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-moderate-orange inline-block border border-white/20"></span>
            <span>Moderate Risk</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-risk-red inline-block border border-white/20"></span>
            <span>High Risk / Full</span>
          </div>
        </div>
      </div>
    </div>
  );
}
