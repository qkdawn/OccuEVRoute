import type { Algorithm, LayerVisibility, RecommendationItem, SearchTraceKind } from "../../types";

export function algorithmShortLabel(algorithm: Algorithm) {
  if (algorithm === "bidirectional_bfs") return "Bidirectional BFS";
  if (algorithm === "alt_astar") return "ALT A*";
  if (algorithm === "ch_bidirectional_dijkstra") return "CH Dijkstra";
  if (algorithm === "astar") return "A*";
  return algorithm.toUpperCase();
}

export function formatMetric(value: number | null) {
  return value === null ? "-" : value.toFixed(2);
}

export function formatPercent(value: number | null) {
  return value === null ? "-" : `${(value * 100).toFixed(1)}%`;
}

export function formatRuntime(seconds: number) {
  if (seconds < 1) return `${Math.round(seconds * 1000)} ms`;
  return `${seconds.toFixed(2)} s`;
}

export function formatPoiSummary(item: RecommendationItem) {
  if (item.poi_total_count === null) return "-";
  return `${item.poi_total_count} / ${item.poi_lifestyle_services_count ?? 0} / ${item.poi_food_beverage_count ?? 0} / ${item.poi_business_residential_count ?? 0}`;
}

export function formatPredictionTime(value: string | null) {
  if (!value) return "-";
  return value.replace("T", " ");
}

export function layerSummary(layerVisibility: LayerVisibility) {
  const activeCount = Object.values(layerVisibility).filter(Boolean).length;
  return `${activeCount} of ${Object.keys(layerVisibility).length} layers visible`;
}

export function occupancyBadge(value: number | null): { label: string; tone: "success" | "warning" | "danger" | "neutral" } {
  if (value === null) return { label: "Unknown", tone: "neutral" };
  if (value < 0.35) return { label: "Low", tone: "success" };
  if (value <= 0.7) return { label: "Medium", tone: "warning" };
  return { label: "High", tone: "danger" };
}

export function playbackDescription(kind: SearchTraceKind) {
  if (kind === "bidirectional") {
    return "Replay the two road-search frontiers as they expand from the start and station access node.";
  }
  return "Replay the explored road area for the selected algorithm without changing the recommendation result.";
}

export function traceLayerSize(item: RecommendationItem, role: "forward" | "backward") {
  return item.search_trace.layers.find((layer) => layer.role === role)?.coordinates.length ?? 0;
}
