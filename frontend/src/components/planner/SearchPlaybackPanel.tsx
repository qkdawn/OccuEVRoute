import type { RecommendationItem } from "../../types";
import { Button, EmptyState, Metric } from "../ui";
import { algorithmShortLabel, formatRuntime, traceLayerSize } from "./formatters";

interface SearchPlaybackPanelProps {
  isPlaybackRunning: boolean;
  onProgressChange: (value: number) => void;
  onReplay: () => void;
  onTogglePlayback: () => void;
  searchPlaybackProgress: number;
  selectedRecommendation: RecommendationItem | null;
}

export function SearchPlaybackPanel({
  isPlaybackRunning,
  onProgressChange,
  onReplay,
  onTogglePlayback,
  searchPlaybackProgress,
  selectedRecommendation,
}: SearchPlaybackPanelProps) {
  if (!selectedRecommendation) {
    return <EmptyState title="No trace" message="Run the planner." />;
  }

  return (
    <>
      <div className="metric-grid">
        <Metric label="Algorithm" value={algorithmShortLabel(selectedRecommendation.algorithm)} />
        <Metric label="Expanded" value={`${selectedRecommendation.expanded_nodes}`} />
        <Metric label="Runtime" value={formatRuntime(selectedRecommendation.runtime_seconds)} />
        {selectedRecommendation.search_trace.kind === "bidirectional" && (
          <>
            <Metric label="Forward" value={`${traceLayerSize(selectedRecommendation, "forward")}`} />
            <Metric label="Backward" value={`${traceLayerSize(selectedRecommendation, "backward")}`} />
            <Metric label="Meeting" value={selectedRecommendation.search_trace.meeting_node_coordinate ? "Found" : "-"} />
          </>
        )}
      </div>
      <div className="playback-controls">
        <Button variant="secondary" onClick={onReplay}>
          Replay
        </Button>
        <Button variant="secondary" onClick={onTogglePlayback}>
          {isPlaybackRunning ? "Pause" : "Play"}
        </Button>
        <input
          type="range"
          min={0}
          max={1}
          step={0.01}
          value={searchPlaybackProgress}
          onChange={(event) => onProgressChange(Number(event.target.value))}
          aria-label="Search playback progress"
        />
      </div>
    </>
  );
}
