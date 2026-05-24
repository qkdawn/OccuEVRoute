import type { RecommendationItem } from "../../types";
import { EmptyState, Metric } from "../ui";
import { formatMetric, formatPercent, formatPoiSummary } from "./formatters";

interface SelectedRoutePanelProps {
  selectedRecommendation: RecommendationItem | null;
}

export function SelectedRoutePanel({ selectedRecommendation }: SelectedRoutePanelProps) {
  if (!selectedRecommendation) {
    return <EmptyState title="No selected route" message="Recommendation details will appear here after a successful planner run." />;
  }

  return (
    <>
      <div className="route-hero">
        <Metric label="Drive time" value={`${formatMetric(selectedRecommendation.drive_time_min)} min`} />
        <Metric label="Distance" value={`${formatMetric(selectedRecommendation.distance_km)} km`} />
        <Metric label="Arrival SOC" value={selectedRecommendation.arrival_soc === null ? "-" : `${(selectedRecommendation.arrival_soc * 100).toFixed(1)}%`} />
      </div>
      <div className="metric-grid secondary-metrics">
        <Metric label="Start snap" value={`${formatMetric(selectedRecommendation.start_snap_distance_m)} m`} />
        <Metric label="Station snap" value={`${formatMetric(selectedRecommendation.road_snap_distance_m)} m`} />
        <Metric label="Nearby POI" value={formatPoiSummary(selectedRecommendation)} />
        <Metric label="Predicted occupancy" value={formatPercent(selectedRecommendation.predicted_occupancy_rate)} />
        <Metric label="Prediction horizon" value={`${formatMetric(selectedRecommendation.prediction_horizon_min)} min`} />
        <Metric label="ML rank score" value={formatMetric(selectedRecommendation.ml_rank_score)} />
      </div>
    </>
  );
}
