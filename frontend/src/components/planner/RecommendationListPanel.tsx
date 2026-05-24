import type { RankingMetric, RecommendationItem } from "../../types";
import { EmptyState, NumberField, SelectField, StatusBadge } from "../ui";
import { RANKING_METRIC_LABELS } from "./constants";
import { algorithmShortLabel, formatMetric, occupancyBadge } from "./formatters";
import type { FormState, FormUpdate } from "./types";

interface RecommendationListPanelProps {
  form: FormState;
  onStationSelect: (stationId: number) => void;
  onUpdateForm: FormUpdate;
  recommendations: RecommendationItem[];
  selectedStationId: number | null;
}

export function RecommendationListPanel({ form, onStationSelect, onUpdateForm, recommendations, selectedStationId }: RecommendationListPanelProps) {
  return (
    <>
      <div className="ranking-config">
        <SelectField
          label="Ranking metric"
          value={form.rankingMetric}
          options={RANKING_METRIC_LABELS}
          onChange={(value) => onUpdateForm("rankingMetric", value as RankingMetric)}
        />
        <NumberField label="Ranked stations" value={form.maxCandidates} min={3} max={50} step={1} onChange={(value) => onUpdateForm("maxCandidates", value)} />
      </div>
      {!recommendations.length ? (
        <EmptyState title="No recommendations yet" message="Choose a location and run the planner to populate ranked charging stations." />
      ) : (
        <div className="ranking-list">
          {recommendations.map((item, index) => {
            const occupancy = occupancyBadge(item.predicted_occupancy_rate);
            return (
              <button
                type="button"
                key={item.station_id ?? `${item.station_latitude}-${item.station_longitude}`}
                className={["ranking-row", item.station_id === selectedStationId ? "selected-row" : "", index === 0 ? "top-row" : ""].filter(Boolean).join(" ")}
                onClick={() => item.station_id !== null && onStationSelect(item.station_id)}
              >
                <span className="ranking-row-main">
                  <span className="rank-token">{index === 0 ? "Top" : index + 1}</span>
                  <span className="station-cell">
                    <strong>{item.station_display_name ?? item.station_id}</strong>
                    <small>{algorithmShortLabel(item.algorithm)}</small>
                  </span>
                  <StatusBadge tone={occupancy.tone}>{occupancy.label}</StatusBadge>
                </span>
                <span className="ranking-metrics">
                  <span className="result-stat">
                    <small>time</small>
                    <strong>{formatMetric(item.drive_time_min)} min</strong>
                  </span>
                  <span className="result-stat">
                    <small>distance</small>
                    <strong>{formatMetric(item.distance_km)} km</strong>
                  </span>
                  <span className="result-stat">
                    <small>SOC</small>
                    <strong>{item.arrival_soc === null ? "-" : `${(item.arrival_soc * 100).toFixed(1)}%`}</strong>
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      )}
    </>
  );
}
