import type { RecommendationItem } from "../../types";
import { EmptyState, StatusBadge } from "../ui";
import { algorithmShortLabel, formatMetric, occupancyBadge } from "./formatters";

interface RecommendationListPanelProps {
  onStationSelect: (stationId: number) => void;
  recommendations: RecommendationItem[];
  selectedStationId: number | null;
}

export function RecommendationListPanel({ onStationSelect, recommendations, selectedStationId }: RecommendationListPanelProps) {
  if (!recommendations.length) {
    return <EmptyState title="No recommendations yet" message="Choose a location and run the planner to populate ranked charging stations." />;
  }

  return (
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
            <span className="rank-token">{index === 0 ? "Top" : index + 1}</span>
            <span className="station-cell">
              <strong>{item.station_display_name ?? item.station_id}</strong>
              <small>{algorithmShortLabel(item.algorithm)}</small>
            </span>
            <span className="result-stat">
              <small>time</small>
              <strong>{formatMetric(item.drive_time_min)}</strong>
            </span>
            <span className="result-stat">
              <small>km</small>
              <strong>{formatMetric(item.distance_km)}</strong>
            </span>
            <span className="result-stat">
              <small>SOC</small>
              <strong>{item.arrival_soc === null ? "-" : `${(item.arrival_soc * 100).toFixed(1)}%`}</strong>
            </span>
            <span className="result-stat result-stat-badge">
              <small>occ</small>
              <StatusBadge tone={occupancy.tone}>{occupancy.label}</StatusBadge>
            </span>
          </button>
        );
      })}
    </div>
  );
}
