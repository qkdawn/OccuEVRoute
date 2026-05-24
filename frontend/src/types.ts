export type Algorithm = "bfs" | "bidirectional_bfs" | "ucs" | "astar" | "alt_astar" | "ch_bidirectional_dijkstra";
export type Basemap = "gaode" | "carto" | "osm";
export type RankingMetric = "balanced" | "drive_time" | "distance" | "occupancy" | "arrival_soc";

export interface LayerVisibility {
  boundary: boolean;
  stations: boolean;
  route: boolean;
  searchTrace: boolean;
  snapLines: boolean;
}

export interface Point {
  lat: number;
  lng: number;
}

export type SearchTraceKind = "single" | "bidirectional";
export type SearchTraceRole = "single" | "forward" | "backward";

export interface SearchTraceLayer {
  role: SearchTraceRole;
  coordinates: [number, number][];
}

export interface SearchTrace {
  kind: SearchTraceKind;
  layers: SearchTraceLayer[];
  meeting_node_coordinate: [number, number] | null;
}

export interface RecommendationRequest {
  lat: number;
  lng: number;
  simulated_now?: string | null;
  algorithm: Algorithm;
  max_candidates: number;
  max_search_radius_km: number;
  max_drive_time_min: number;
  current_soc: number;
  battery_capacity_kwh: number;
  consumption_kwh_per_km: number;
  min_arrival_soc: number;
  min_charge_count: number;
  max_road_snap_distance_m: number;
  max_start_snap_distance_m: number;
  ranking_metric: RankingMetric;
  top_k: number;
}

export interface RecommendationItem {
  station_id: number | null;
  station_display_name: string | null;
  algorithm: Algorithm;
  station_latitude: number | null;
  station_longitude: number | null;
  station_road_latitude: number | null;
  station_road_longitude: number | null;
  start_node_latitude: number | null;
  start_node_longitude: number | null;
  start_snap_distance_m: number | null;
  route_coordinates: [number, number][];
  search_trace: SearchTrace;
  distance_km: number | null;
  drive_time_min: number | null;
  road_snap_distance_m: number | null;
  expanded_nodes: number;
  runtime_seconds: number;
  charge_count: number | null;
  poi_total_count: number | null;
  poi_lifestyle_services_count: number | null;
  poi_business_residential_count: number | null;
  poi_food_beverage_count: number | null;
  arrival_soc: number | null;
  predicted_occupancy_rate: number | null;
  prediction_horizon_min: number | null;
  prediction_time: string | null;
  prediction_source: string;
  ml_rank_score: number | null;
  passed_constraints: boolean;
  reject_reason: string;
}

export interface RecommendationResponse {
  recommendations: RecommendationItem[];
}

export type BoundaryGeometry =
  | {
      type: "Polygon";
      coordinates: number[][][];
    }
  | {
      type: "MultiPolygon";
      coordinates: number[][][][];
    };

export interface BoundaryFeature {
  type: "Feature";
  properties: Record<string, unknown>;
  geometry: BoundaryGeometry;
}

export interface BoundaryGeoJson {
  type: "FeatureCollection";
  features: BoundaryFeature[];
}
