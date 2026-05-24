import type { RecommendationItem } from "../../types";
import { EmptyState, Metric, StatusBadge } from "../ui";
import { DEMO_TIME_RULE, DEMO_WEEK_LABEL } from "./constants";
import { formatMetric, formatPercent, formatPredictionTime, occupancyBadge } from "./formatters";

interface DemoTimeExplanationPanelProps {
  selectedRecommendation: RecommendationItem | null;
}

export function DemoTimeExplanationPanel({ selectedRecommendation }: DemoTimeExplanationPanelProps) {
  if (!selectedRecommendation) {
    return <EmptyState title="No ML prediction yet" message="Run a recommendation to inspect the historical-time occupancy prediction for the selected station." />;
  }

  const occupancy = occupancyBadge(selectedRecommendation.predicted_occupancy_rate);

  return (
    <div className="demo-explanation">
      <div className="demo-rule">
        <span>Demo week</span>
        <strong>{DEMO_WEEK_LABEL}</strong>
        <p>{DEMO_TIME_RULE}</p>
      </div>
      <div className="metric-grid">
        <Metric label="Predicted occupancy" value={formatPercent(selectedRecommendation.predicted_occupancy_rate)} />
        <Metric label="Prediction horizon" value={`${formatMetric(selectedRecommendation.prediction_horizon_min)} min`} />
        <Metric label="Prediction time" value={formatPredictionTime(selectedRecommendation.prediction_time)} />
        <Metric label="Balanced score" value={formatMetric(selectedRecommendation.ml_rank_score)} />
        <Metric label="Source" value={selectedRecommendation.prediction_source || "-"} />
        <div className="ui-metric">
          <span>Occupancy risk</span>
          <strong>
            <StatusBadge tone={occupancy.tone}>{occupancy.label}</StatusBadge>
          </strong>
        </div>
      </div>
    </div>
  );
}
