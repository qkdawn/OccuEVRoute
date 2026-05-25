import type { Algorithm, Basemap, LayerVisibility, RankingMetric } from "../../types";

export const BASEMAP_LABELS: Record<Basemap, string> = {
  gaode: "Amap",
  carto: "CartoDB Light",
  osm: "OpenStreetMap",
};

export const ALGORITHM_LABELS: Record<Algorithm, string> = {
  bfs: "BFS: Unweighted baseline",
  bidirectional_bfs: "Bidirectional BFS: Two-frontier search",
  ch_bidirectional_dijkstra: "CH Dijkstra: Contracted bidirectional query",
  ucs: "UCS: Travel-time baseline",
  astar: "A*: Straight-line heuristic",
  alt_astar: "ALT A*: Landmark heuristic",
};

export const RANKING_METRIC_LABELS: Record<RankingMetric, string> = {
  balanced: "Balanced: time + predicted occupancy",
  drive_time: "Shortest drive time",
  distance: "Shortest distance",
  occupancy: "Lowest predicted occupancy",
  arrival_soc: "Highest arrival SOC",
};

export const LAYER_LABELS: Array<[keyof LayerVisibility, string, string]> = [
  ["boundary", "Shenzhen boundary", "Show the valid planning area."],
  ["stations", "Candidate stations", "Show ranked station markers."],
  ["route", "Selected route", "Show the currently selected route line."],
  ["searchTrace", "Search trace", "Show expanded search nodes and hull."],
  ["snapLines", "Snap lines", "Show start and station road-access offsets."],
];

export const DEMO_WEEK_LABEL = "2023-02-06 ~ 2023-02-12";
