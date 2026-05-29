import L from "leaflet";
import markerIcon from "leaflet/dist/images/marker-icon.png";
import markerIcon2x from "leaflet/dist/images/marker-icon-2x.png";
import markerShadow from "leaflet/dist/images/marker-shadow.png";
import { useEffect, useMemo, useRef } from "react";
import type {
  Basemap,
  BoundaryGeoJson,
  BoundaryGeometry,
  LayerVisibility,
  Point,
  RecommendationItem,
  SearchTraceLayer,
  SearchTraceRole,
} from "../types";
import { pointInBoundary } from "./boundary";
import { fromMapPoint, toMapPoint } from "./coordinates";
import { createStationIcon } from "./stationIcons";

L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
});

const DEFAULT_CENTER: Point = { lat: 22.65, lng: 114.05 };
const MIN_ZOOM = 10;

const BASEMAPS: Record<Basemap, { url: string; attribution: string }> = {
  gaode: {
    url: "https://webrd02.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}",
    attribution: "Amap",
  },
  carto: {
    url: "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
    attribution: "&copy; OpenStreetMap contributors &copy; CARTO",
  },
  osm: {
    url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution: "&copy; OpenStreetMap contributors",
  },
};

const TRACE_ROLE_STYLES: Record<SearchTraceRole, TraceStyle> = {
  single: { stroke: "#376f7d", fill: "#8fb9c2", hullFill: "#c9dee3" },
  forward: { stroke: "#2563eb", fill: "#93c5fd", hullFill: "#bfdbfe" },
  backward: { stroke: "#b45309", fill: "#fbbf24", hullFill: "#fde68a" },
};
const SEARCH_TRACE_COMPLETE_AT = 0.82;
const CH_FRONTIER_POINT_LIMIT = 10;

interface TraceStyle {
  stroke: string;
  fill: string;
  hullFill: string;
}

interface RouteMapProps {
  basemap: Basemap;
  boundary: BoundaryGeoJson | null;
  selectedPoint: Point | null;
  recommendations: RecommendationItem[];
  selectedStationId: number | null;
  searchPlaybackProgress: number;
  layerVisibility: LayerVisibility;
  onPointChange: (point: Point) => void;
  onInvalidPoint: () => void;
  onStationSelect: (stationId: number) => void;
}

export function RouteMap({
  basemap,
  boundary,
  selectedPoint,
  recommendations,
  selectedStationId,
  searchPlaybackProgress,
  layerVisibility,
  onPointChange,
  onInvalidPoint,
  onStationSelect,
}: RouteMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const boundaryRef = useRef<BoundaryGeoJson | null>(boundary);
  const tileLayerRef = useRef<L.TileLayer | null>(null);
  const selectedMarkerRef = useRef<L.Marker | null>(null);
  const boundaryMaskRef = useRef<L.Polygon | null>(null);
  const boundaryLayerRef = useRef<L.GeoJSON | null>(null);
  const stationLayerRef = useRef<L.LayerGroup | null>(null);
  const routeLayerRef = useRef<L.Polyline | null>(null);
  const searchTraceLayerRef = useRef<L.LayerGroup | null>(null);
  const startSnapLayerRef = useRef<L.Polyline | null>(null);
  const stationSnapLayerRef = useRef<L.Polyline | null>(null);
  const resetControlRef = useRef<L.Control | null>(null);
  const basemapRef = useRef<Basemap>(basemap);
  const selectedPointRef = useRef<Point | null>(selectedPoint);
  const selectedRecommendationRef = useRef<RecommendationItem | null>(null);
  const hasFitBoundaryRef = useRef(false);

  useEffect(() => {
    boundaryRef.current = boundary;
  }, [boundary]);

  useEffect(() => {
    selectedPointRef.current = selectedPoint;
  }, [selectedPoint]);

  const selectedRecommendation = useMemo(() => {
    return recommendations.find((item) => item.station_id === selectedStationId) ?? recommendations[0] ?? null;
  }, [recommendations, selectedStationId]);

  useEffect(() => {
    selectedRecommendationRef.current = selectedRecommendation;
  }, [selectedRecommendation]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = L.map(containerRef.current, { maxBoundsViscosity: 1.0, minZoom: MIN_ZOOM, zoomControl: false }).setView(
      toLeaflet(toMapPoint(DEFAULT_CENTER, basemapRef.current)),
      MIN_ZOOM,
    );
    L.control.zoom({ position: "bottomright" }).addTo(map);
    stationLayerRef.current = L.layerGroup().addTo(map);
    searchTraceLayerRef.current = L.layerGroup().addTo(map);
    resetControlRef.current = createResetViewControl(() => resetMapView(map, basemapRef.current, boundaryRef.current, selectedPointRef.current, selectedRecommendationRef.current));
    resetControlRef.current.addTo(map);
    map.on("click", (event) => {
      const point = fromMapPoint({ lat: event.latlng.lat, lng: event.latlng.lng }, basemapRef.current);
      if (boundaryRef.current && !pointInBoundary(point, boundaryRef.current)) {
        onInvalidPoint();
        return;
      }
      onPointChange(point);
    });
    mapRef.current = map;
  }, [onInvalidPoint, onPointChange]);

  useEffect(() => {
    basemapRef.current = basemap;
    const map = mapRef.current;
    if (!map) return;
    if (tileLayerRef.current) tileLayerRef.current.remove();
    const config = BASEMAPS[basemap];
    tileLayerRef.current = L.tileLayer(config.url, {
      attribution: config.attribution,
      maxZoom: 19,
    }).addTo(map);
  }, [basemap]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (!selectedPoint) {
      if (selectedMarkerRef.current) {
        selectedMarkerRef.current.remove();
        selectedMarkerRef.current = null;
      }
      return;
    }
    const mapPoint = toMapPoint(selectedPoint, basemap);
    if (!selectedMarkerRef.current) {
      selectedMarkerRef.current = L.marker(toLeaflet(mapPoint), { title: "Current location" }).addTo(map);
      map.setView(toLeaflet(mapPoint), 13);
    } else {
      selectedMarkerRef.current.setLatLng(toLeaflet(mapPoint));
    }
  }, [basemap, selectedPoint]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !boundary) return;
    if (boundaryMaskRef.current) boundaryMaskRef.current.remove();
    if (boundaryLayerRef.current) boundaryLayerRef.current.remove();
    const mapBoundary = boundaryToMapGeoJson(boundary, basemap);
    if (layerVisibility.boundary) {
      boundaryMaskRef.current = L.polygon(boundaryMaskRings(mapBoundary), {
        color: "transparent",
        fillColor: "#0d546c",
        fillOpacity: 0.18,
        fillRule: "evenodd",
        interactive: false,
        stroke: false,
      }).addTo(map);
      boundaryLayerRef.current = L.geoJSON(mapBoundary, {
        interactive: false,
        style: {
          color: "#5e99a0",
          weight: 2,
          opacity: 0.9,
          fillOpacity: 0,
        },
      }).addTo(map);
      boundaryMaskRef.current.bringToBack();
      boundaryLayerRef.current.bringToBack();
    } else {
      boundaryMaskRef.current = null;
      boundaryLayerRef.current = null;
    }
    const bounds = boundaryBounds(mapBoundary);
    if (bounds.isValid()) {
      const paddedBounds = bounds.pad(0.15);
      map.setMaxBounds(paddedBounds);
      map.setMinZoom(MIN_ZOOM);
      if (!hasFitBoundaryRef.current) {
        map.fitBounds(bounds, { animate: false, padding: [20, 20] });
        hasFitBoundaryRef.current = true;
      }
    }
  }, [basemap, boundary, layerVisibility.boundary]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !stationLayerRef.current) return;

    stationLayerRef.current.clearLayers();
    searchTraceLayerRef.current?.clearLayers();
    removePolyline(routeLayerRef);
    removePolyline(startSnapLayerRef);
    removePolyline(stationSnapLayerRef);

    if (layerVisibility.stations) {
      recommendations.forEach((item, index) => {
        if (item.station_id === null || item.station_latitude === null || item.station_longitude === null) return;
        const isSelected = item.station_id === selectedRecommendation?.station_id;
        const marker = L.marker(toLeaflet(toMapPoint({ lat: item.station_latitude, lng: item.station_longitude }, basemap)), {
          icon: createStationIcon(isSelected, item.charge_count),
          title: item.station_display_name ?? `station_id=${item.station_id}`,
        });
        marker.bindPopup(stationPopup(item, index + 1), {
          className: "station-popup",
          closeButton: false,
          maxWidth: 260,
          offset: [0, -8],
        });
        marker.on("click", () => onStationSelect(item.station_id as number));
        marker.addTo(stationLayerRef.current as L.LayerGroup);
      });
    }

    if (!selectedPoint || !selectedRecommendation?.route_coordinates.length) return;
    const isChTrace = selectedRecommendation.algorithm === "ch_bidirectional_dijkstra";
    const traceProgress = Math.min(searchPlaybackProgress / SEARCH_TRACE_COMPLETE_AT, 1);
    const routeProgress =
      searchPlaybackProgress <= SEARCH_TRACE_COMPLETE_AT
        ? 0
        : (searchPlaybackProgress - SEARCH_TRACE_COMPLETE_AT) / (1 - SEARCH_TRACE_COMPLETE_AT);

    if (layerVisibility.searchTrace && searchTraceLayerRef.current) {
      if (selectedRecommendation.search_trace.kind === "bidirectional") {
        renderTrace(
          searchTraceLayerRef.current,
          getTraceLayer(selectedRecommendation, "forward"),
          traceProgress,
          basemap,
          TRACE_ROLE_STYLES.forward,
          chTraceOptions(isChTrace),
        );
        renderTrace(
          searchTraceLayerRef.current,
          getTraceLayer(selectedRecommendation, "backward"),
          traceProgress,
          basemap,
          TRACE_ROLE_STYLES.backward,
          chTraceOptions(isChTrace),
        );
        if (traceProgress >= 1 && selectedRecommendation.search_trace.meeting_node_coordinate) {
          const [lat, lng] = selectedRecommendation.search_trace.meeting_node_coordinate;
          L.circleMarker(toLeaflet(toMapPoint({ lat, lng }, basemap)), {
            radius: 7,
            color: "#111827",
            weight: 2,
            fillColor: "#ffffff",
            fillOpacity: 0.92,
            interactive: false,
          })
            .bindTooltip("Meeting node", { direction: "top", opacity: 0.86 })
            .addTo(searchTraceLayerRef.current);
        }
      } else {
        renderTrace(
          searchTraceLayerRef.current,
          getTraceLayer(selectedRecommendation, "single"),
          traceProgress,
          basemap,
          TRACE_ROLE_STYLES.single,
        );
      }
    }

    if (layerVisibility.route) {
      const routeCoordinates = isChTrace
        ? selectedRecommendation.route_coordinates
        : visibleRouteCoordinates(selectedRecommendation.route_coordinates, routeProgress);
      routeLayerRef.current = L.polyline(
        routeCoordinates.map(([lat, lng]) => toLeaflet(toMapPoint({ lat, lng }, basemap))),
        { color: "#2563eb", weight: 5, opacity: 0.86 },
      ).addTo(map);
    }

    if (
      layerVisibility.snapLines &&
      selectedRecommendation.start_node_latitude !== null &&
      selectedRecommendation.start_node_longitude !== null
    ) {
      startSnapLayerRef.current = L.polyline(
        [
          toLeaflet(toMapPoint(selectedPoint, basemap)),
          toLeaflet(
            toMapPoint(
              {
                lat: selectedRecommendation.start_node_latitude,
                lng: selectedRecommendation.start_node_longitude,
              },
              basemap,
            ),
          ),
        ],
        { color: "#f97316", weight: 4, opacity: 0.92, dashArray: "8,8" },
      ).addTo(map);
    }

    if (
      layerVisibility.snapLines &&
      selectedRecommendation.station_road_latitude !== null &&
      selectedRecommendation.station_road_longitude !== null &&
      selectedRecommendation.station_latitude !== null &&
      selectedRecommendation.station_longitude !== null
    ) {
      stationSnapLayerRef.current = L.polyline(
        [
          toLeaflet(
            toMapPoint(
              {
                lat: selectedRecommendation.station_road_latitude,
                lng: selectedRecommendation.station_road_longitude,
              },
              basemap,
            ),
          ),
          toLeaflet(
            toMapPoint(
              {
                lat: selectedRecommendation.station_latitude,
                lng: selectedRecommendation.station_longitude,
              },
              basemap,
            ),
          ),
        ],
        { color: "#f97316", weight: 4, opacity: 0.92, dashArray: "8,8" },
      ).addTo(map);
    }
  }, [basemap, layerVisibility, onStationSelect, recommendations, searchPlaybackProgress, selectedPoint, selectedRecommendation]);

  return <div className="map-canvas" ref={containerRef} />;
}

function toLeaflet(point: Point): L.LatLngExpression {
  return [point.lat, point.lng];
}

function removePolyline(ref: React.MutableRefObject<L.Polyline | null>) {
  if (ref.current) {
    ref.current.remove();
    ref.current = null;
  }
}

function createResetViewControl(onReset: () => void) {
  const ResetControl = L.Control.extend({
    options: { position: "bottomright" },
    onAdd() {
      const container = L.DomUtil.create("div", "leaflet-bar leaflet-control map-reset-control");
      const button = L.DomUtil.create("button", "", container);
      button.type = "button";
      button.title = "Reset view";
      button.setAttribute("aria-label", "Reset map view");
      button.innerHTML =
        '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4.5v2.1M12 17.4v2.1M4.5 12h2.1M17.4 12h2.1"/><circle cx="12" cy="12" r="5.4"/><circle cx="12" cy="12" r="1.8"/></svg>';
      L.DomEvent.disableClickPropagation(container);
      L.DomEvent.disableScrollPropagation(container);
      L.DomEvent.on(button, "click", (event) => {
        L.DomEvent.preventDefault(event);
        onReset();
      });
      return container;
    },
  });
  return new ResetControl();
}

function resetMapView(
  map: L.Map,
  basemap: Basemap,
  boundary: BoundaryGeoJson | null,
  selectedPoint: Point | null,
  selectedRecommendation: RecommendationItem | null,
) {
  const routeBounds = selectedRecommendation?.route_coordinates.length
    ? L.latLngBounds(selectedRecommendation.route_coordinates.map(([lat, lng]) => toLeaflet(toMapPoint({ lat, lng }, basemap))))
    : null;
  if (routeBounds?.isValid()) {
    map.fitBounds(routeBounds.pad(0.18), { animate: true, padding: [28, 28] });
    return;
  }
  if (selectedPoint) {
    map.setView(toLeaflet(toMapPoint(selectedPoint, basemap)), 13, { animate: true });
    return;
  }
  if (boundary) {
    const bounds = boundaryBounds(boundaryToMapGeoJson(boundary, basemap));
    if (bounds.isValid()) {
      map.fitBounds(bounds, { animate: true, padding: [20, 20] });
      return;
    }
  }
  map.setView(toLeaflet(toMapPoint(DEFAULT_CENTER, basemap)), MIN_ZOOM, { animate: true });
}

function getTraceLayer(item: RecommendationItem, role: SearchTraceRole) {
  return item.search_trace.layers.find((layer) => layer.role === role) ?? null;
}

function visibleRouteCoordinates(coordinates: [number, number][], progress: number) {
  if (progress <= 0) return [];
  const visibleCount = Math.max(2, Math.ceil(coordinates.length * Math.min(progress, 1)));
  return coordinates.slice(0, visibleCount);
}

interface TraceRenderOptions {
  hullAroundFrontier: boolean;
  hullDashArray?: string;
  hullFillOpacity: number;
  pointLimit: number;
  showEdges: boolean;
  showHull: boolean;
}

function chTraceOptions(isChTrace: boolean): TraceRenderOptions | undefined {
  if (!isChTrace) return undefined;
  return {
    hullAroundFrontier: true,
    hullDashArray: "5,5",
    hullFillOpacity: 0,
    pointLimit: CH_FRONTIER_POINT_LIMIT,
    showEdges: false,
    showHull: true,
  };
}

function renderTrace(
  layer: L.LayerGroup,
  traceLayer: SearchTraceLayer | null,
  progress: number,
  basemap: Basemap,
  colors: TraceStyle,
  options: TraceRenderOptions = { hullAroundFrontier: false, hullFillOpacity: 0.16, pointLimit: 18, showEdges: true, showHull: true },
) {
  if (!traceLayer) return;
  const visibleNodeCount = Math.max(0, Math.ceil(traceLayer.coordinates.length * progress));
  const visibleEdgeCount = Math.max(0, Math.ceil(traceLayer.edges.length * progress));
  const visibleTracePoints = traceLayer.coordinates.slice(0, visibleNodeCount).map(([lat, lng]) => toMapPoint({ lat, lng }, basemap));
  if (!visibleTracePoints.length && visibleEdgeCount === 0) return;

  const frontierPoints = visibleTracePoints.slice(-options.pointLimit);
  const hull = convexHull(options.hullAroundFrontier ? frontierPoints : visibleTracePoints);
  if (options.showHull && hull.length >= 3) {
    L.polygon(hull.map(toLeaflet), {
      color: colors.stroke,
      weight: 1.4,
      opacity: 0.34,
      fillColor: colors.hullFill,
      fillOpacity: options.hullFillOpacity,
      dashArray: options.hullDashArray,
      interactive: false,
    }).addTo(layer);
  }

  if (options.showEdges) {
    traceLayer.edges.slice(0, visibleEdgeCount).forEach((edge) => {
      const points = edge.map(([lat, lng]) => toLeaflet(toMapPoint({ lat, lng }, basemap)));
      if (points.length < 2) return;
      L.polyline(points, {
        color: colors.stroke,
        weight: 1.6,
        opacity: 0.34,
        lineCap: "round",
        lineJoin: "round",
        smoothFactor: 1,
        interactive: false,
      }).addTo(layer);
    });
  }

  frontierPoints.forEach((point, index, frontier) => {
    const opacity = 0.18 + (index / Math.max(frontier.length - 1, 1)) * 0.36;
    L.circleMarker(toLeaflet(point), {
      radius: options.showHull ? 2.5 : 3.7,
      color: colors.stroke,
      weight: options.showHull ? 0 : 1.4,
      fillColor: colors.fill,
      fillOpacity: options.showHull ? opacity : 0.82,
      interactive: false,
    }).addTo(layer);
  });
}

function convexHull(points: Point[]): Point[] {
  const unique = Array.from(new Map(points.map((point) => [`${point.lng},${point.lat}`, point])).values()).sort(
    (a, b) => a.lng - b.lng || a.lat - b.lat,
  );
  if (unique.length <= 2) return unique;

  const lower: Point[] = [];
  unique.forEach((point) => {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], point) <= 0) {
      lower.pop();
    }
    lower.push(point);
  });

  const upper: Point[] = [];
  [...unique].reverse().forEach((point) => {
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], point) <= 0) {
      upper.pop();
    }
    upper.push(point);
  });

  lower.pop();
  upper.pop();
  return [...lower, ...upper];
}

function cross(origin: Point, a: Point, b: Point) {
  return (a.lng - origin.lng) * (b.lat - origin.lat) - (a.lat - origin.lat) * (b.lng - origin.lng);
}

function stationPopup(item: RecommendationItem, rank: number) {
  const stationName = escapeHtml(item.station_display_name ?? `Station ${item.station_id}`);
  const occupancy = formatPercent(item.predicted_occupancy_rate);
  const arrival = item.arrival_soc === null ? "-" : `${(item.arrival_soc * 100).toFixed(1)}%`;
  const snap = item.road_snap_distance_m === null ? "-" : `${item.road_snap_distance_m.toFixed(0)} m`;

  return (
    `<div class="station-popup-card">` +
    `<div class="station-popup-head">` +
    `<span>Top ${rank}</span>` +
    `<strong>${stationName}</strong>` +
    `</div>` +
    `<div class="station-popup-grid">` +
    stationPopupMetric("Time", `${formatMetric(item.drive_time_min)} min`) +
    stationPopupMetric("Distance", `${formatMetric(item.distance_km)} km`) +
    stationPopupMetric("Occupancy", occupancy || "-") +
    stationPopupMetric("Arrival", arrival) +
    `</div>` +
    `<div class="station-popup-foot">` +
    `<span>${item.charge_count ?? "-"} chargers</span>` +
    `<span>${snap} snap</span>` +
    `<span>${formatPoiSummary(item) || "-"} POI</span>` +
    `</div>` +
    `</div>`
  );
}

function formatMetric(value: number | null) {
  return value === null ? "-" : value.toFixed(2);
}

function formatPercent(value: number | null) {
  return value === null ? "" : `${(value * 100).toFixed(1)}%`;
}

function formatPoiSummary(item: RecommendationItem) {
  if (item.poi_total_count === null) return "";
  return `${item.poi_total_count} / ${item.poi_lifestyle_services_count ?? 0} / ${item.poi_food_beverage_count ?? 0} / ${item.poi_business_residential_count ?? 0}`;
}

function stationPopupMetric(label: string, value: string) {
  return `<span><small>${label}</small><strong>${value}</strong></span>`;
}

function escapeHtml(value: string) {
  return value.replace(/[&<>"']/g, (char) => {
    const entities: Record<string, string> = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    };
    return entities[char];
  });
}

function boundaryToMapGeoJson(boundary: BoundaryGeoJson, basemap: Basemap): BoundaryGeoJson {
  return {
    ...boundary,
    features: boundary.features.map((feature) => ({
      ...feature,
      geometry: transformGeometry(feature.geometry, basemap),
    })),
  };
}

function transformGeometry(geometry: BoundaryGeometry, basemap: Basemap): BoundaryGeometry {
  if (geometry.type === "Polygon") {
    return {
      type: "Polygon",
      coordinates: [geometry.coordinates[0].map((coordinate) => transformCoordinate(coordinate, basemap))],
    };
  }
  return {
    type: "MultiPolygon",
    coordinates: geometry.coordinates.map((polygon) =>
      [polygon[0].map((coordinate) => transformCoordinate(coordinate, basemap))],
    ),
  };
}

function transformCoordinate(coordinate: number[], basemap: Basemap): number[] {
  const point = toMapPoint({ lng: coordinate[0], lat: coordinate[1] }, basemap);
  return [point.lng, point.lat];
}

function boundaryMaskRings(boundary: BoundaryGeoJson): L.LatLngExpression[][] {
  const worldRing: L.LatLngExpression[] = [
    [-90, -180],
    [-90, 180],
    [90, 180],
    [90, -180],
  ];
  const holes: L.LatLngExpression[][] = [];
  boundary.features.forEach((feature) => {
    collectOuterRings(feature.geometry).forEach((ring) => {
      holes.push(ring.map((coordinate) => [coordinate[1], coordinate[0]]));
    });
  });
  return [worldRing, ...holes];
}

function collectOuterRings(geometry: BoundaryGeometry): number[][][] {
  if (geometry.type === "Polygon") return geometry.coordinates.length ? [geometry.coordinates[0]] : [];
  return geometry.coordinates.flatMap((polygon) => (polygon.length ? [polygon[0]] : []));
}

function boundaryBounds(boundary: BoundaryGeoJson): L.LatLngBounds {
  const bounds = L.latLngBounds([]);
  boundary.features.forEach((feature) => {
    extendBoundsWithGeometry(bounds, feature.geometry);
  });
  return bounds;
}

function extendBoundsWithGeometry(bounds: L.LatLngBounds, geometry: BoundaryGeometry) {
  if (geometry.type === "Polygon") {
    geometry.coordinates.forEach((ring) => {
      extendBoundsWithRing(bounds, ring);
    });
    return;
  }
  geometry.coordinates.forEach((polygon) => {
    polygon.forEach((ring) => {
      extendBoundsWithRing(bounds, ring);
    });
  });
}

function extendBoundsWithRing(bounds: L.LatLngBounds, ring: number[][]) {
  ring.forEach((coordinate) => {
    bounds.extend([coordinate[1], coordinate[0]]);
  });
}

