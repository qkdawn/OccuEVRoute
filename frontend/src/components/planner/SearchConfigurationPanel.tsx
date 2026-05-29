import type { Point } from "../../types";
import { Button } from "../ui";
import { StartSearchField } from "./StartSearchField";

interface SearchConfigurationPanelProps {
  canRecommend: boolean;
  isLoading: boolean;
  onRecommend: () => void;
  onStartSelect: (point: Point) => void;
  selectedPoint: Point | null;
  submittedPoint: Point | null;
}

export function SearchConfigurationPanel({
  canRecommend,
  isLoading,
  onRecommend,
  onStartSelect,
  selectedPoint,
  submittedPoint,
}: SearchConfigurationPanelProps) {
  return (
    <div className="plan-action">
      <StartSearchField onSelect={onStartSelect} />
      <div className="plan-action-copy">
        <strong>{selectedPoint ? `${selectedPoint.lat.toFixed(5)}, ${selectedPoint.lng.toFixed(5)}` : "No start"}</strong>
        <span>{submittedPoint ? `Last run · ${submittedPoint.lat.toFixed(5)}, ${submittedPoint.lng.toFixed(5)}` : "Pick a start on map"}</span>
      </div>
      <Button variant="primary" disabled={!canRecommend} loading={isLoading} onClick={onRecommend}>
        Recommend stations
      </Button>
    </div>
  );
}
