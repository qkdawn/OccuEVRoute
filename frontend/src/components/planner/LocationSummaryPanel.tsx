import type { Point } from "../../types";

interface LocationSummaryPanelProps {
  selectedPoint: Point | null;
  submittedPoint: Point | null;
}

export function LocationSummaryPanel({ selectedPoint, submittedPoint }: LocationSummaryPanelProps) {
  return (
    <div className="summary-copy">
      <strong>{selectedPoint ? `${selectedPoint.lat.toFixed(6)}, ${selectedPoint.lng.toFixed(6)}` : "No start location selected"}</strong>
      {submittedPoint && (
        <span>
          Latest recommendation run: {submittedPoint.lat.toFixed(6)}, {submittedPoint.lng.toFixed(6)}
        </span>
      )}
    </div>
  );
}
