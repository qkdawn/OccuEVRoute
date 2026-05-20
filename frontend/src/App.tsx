import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { fetchBoundary, fetchRecommendations } from "./api";
import { RouteMap } from "./map/RouteMap";
import type { Algorithm, Basemap, BoundaryGeoJson, LayerVisibility, Point, RecommendationItem, SearchTraceKind } from "./types";

interface FormState {
  basemap: Basemap;
  algorithm: Algorithm;
  maxCandidates: number;
  maxSearchRadiusKm: number;
  maxDriveTimeMin: number;
  currentSocPercent: number;
  batteryCapacityKwh: number;
  consumptionKwhPer100Km: number;
  minArrivalSocPercent: number;
  minChargeCount: number;
  maxRoadSnapDistanceM: number;
  maxStartSnapDistanceM: number;
}

type PanelPlacement = "left" | "right";
type PanelId =
  | "search"
  | "vehicle"
  | "algorithm"
  | "layers"
  | "location"
  | "recommendations"
  | "route"
  | "playback";

interface PanelConfig {
  id: PanelId;
  title: string;
  eyebrow: string;
  placement: PanelPlacement;
  defaultOpen: boolean;
  enabled: boolean;
}

const DEFAULT_FORM: FormState = {
  basemap: "gaode",
  algorithm: "astar",
  maxCandidates: 20,
  maxSearchRadiusKm: 10,
  maxDriveTimeMin: 30,
  currentSocPercent: 50,
  batteryCapacityKwh: 60,
  consumptionKwhPer100Km: 18.8,
  minArrivalSocPercent: 10,
  minChargeCount: 1,
  maxRoadSnapDistanceM: 150,
  maxStartSnapDistanceM: 300,
};

const DEFAULT_LAYER_VISIBILITY: LayerVisibility = {
  boundary: true,
  stations: true,
  route: true,
  searchTrace: true,
  snapLines: true,
};

const PANELS: PanelConfig[] = [
  { id: "search", title: "Search configuration", eyebrow: "Plan", placement: "left", defaultOpen: true, enabled: true },
  { id: "vehicle", title: "Vehicle constraints", eyebrow: "Feasibility", placement: "left", defaultOpen: false, enabled: true },
  { id: "algorithm", title: "Algorithm configuration", eyebrow: "Advanced", placement: "left", defaultOpen: false, enabled: true },
  { id: "layers", title: "Layer display", eyebrow: "Map", placement: "left", defaultOpen: false, enabled: true },
  { id: "location", title: "Current location", eyebrow: "Input", placement: "right", defaultOpen: true, enabled: true },
  { id: "recommendations", title: "Recommendation list", eyebrow: "Output", placement: "right", defaultOpen: true, enabled: true },
  { id: "route", title: "Selected route detail", eyebrow: "Explain", placement: "right", defaultOpen: true, enabled: true },
  { id: "playback", title: "Search playback", eyebrow: "Diagnostics", placement: "right", defaultOpen: false, enabled: true },
];

const BASEMAP_LABELS: Record<Basemap, string> = {
  gaode: "Amap",
  carto: "CartoDB Light",
  osm: "OpenStreetMap",
};

const ALGORITHM_LABELS: Record<Algorithm, string> = {
  astar: "A*: Estimated-time guided search",
  ucs: "UCS: Shortest travel time",
  bfs: "Bidirectional BFS: Two-frontier baseline",
};

const LAYER_LABELS: Array<[keyof LayerVisibility, string, string]> = [
  ["boundary", "Shenzhen boundary", "Show the valid planning area."],
  ["stations", "Candidate stations", "Show ranked station markers."],
  ["route", "Selected route", "Show the currently selected route line."],
  ["searchTrace", "Search trace", "Show expanded search nodes and hull."],
  ["snapLines", "Snap lines", "Show start and station road-access offsets."],
];

const initialPanelState = Object.fromEntries(PANELS.map((panel) => [panel.id, panel.defaultOpen])) as Record<PanelId, boolean>;

export function App() {
  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  const [layerVisibility, setLayerVisibility] = useState<LayerVisibility>(DEFAULT_LAYER_VISIBILITY);
  const [openPanels, setOpenPanels] = useState<Record<PanelId, boolean>>(initialPanelState);
  const [selectedPoint, setSelectedPoint] = useState<Point | null>(null);
  const [submittedPoint, setSubmittedPoint] = useState<Point | null>(null);
  const [recommendations, setRecommendations] = useState<RecommendationItem[]>([]);
  const [selectedStationId, setSelectedStationId] = useState<number | null>(null);
  const [boundary, setBoundary] = useState<BoundaryGeoJson | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isPlaybackRunning, setIsPlaybackRunning] = useState(false);
  const [searchPlaybackProgress, setSearchPlaybackProgress] = useState(1);
  const [error, setError] = useState<string | null>(null);

  const selectedRecommendation = useMemo(() => {
    return recommendations.find((item) => item.station_id === selectedStationId) ?? recommendations[0] ?? null;
  }, [recommendations, selectedStationId]);

  const panelSummaries = useMemo<Record<PanelId, string>>(
    () => ({
      search: `${form.maxCandidates} candidates within ${form.maxSearchRadiusKm} km`,
      vehicle: `${form.currentSocPercent}% SOC, ${form.batteryCapacityKwh} kWh battery`,
      algorithm: `${form.algorithm.toUpperCase()}, snap ${form.maxStartSnapDistanceM}/${form.maxRoadSnapDistanceM} m`,
      layers: layerSummary(layerVisibility),
      location: selectedPoint ? `${selectedPoint.lat.toFixed(4)}, ${selectedPoint.lng.toFixed(4)}` : "Waiting for map click",
      recommendations: recommendations.length ? `${recommendations.length} ranked stations` : "No run yet",
      route: selectedRecommendation ? `${formatMetric(selectedRecommendation.drive_time_min)} min, ${formatMetric(selectedRecommendation.distance_km)} km` : "No route selected",
      playback: selectedRecommendation ? `${selectedRecommendation.expanded_nodes} expanded nodes` : "No trace yet",
    }),
    [form, layerVisibility, recommendations.length, selectedPoint, selectedRecommendation],
  );

  function updateForm<T extends keyof FormState>(key: T, value: FormState[T]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function updateLayer(key: keyof LayerVisibility, value: boolean) {
    setLayerVisibility((current) => ({ ...current, [key]: value }));
  }

  function togglePanel(id: PanelId) {
    setOpenPanels((current) => ({ ...current, [id]: !current[id] }));
  }

  function handlePointChange(point: Point) {
    setSelectedPoint(point);
    setRecommendations([]);
    setSelectedStationId(null);
    setIsPlaybackRunning(false);
    setSearchPlaybackProgress(1);
    setError(null);
  }

  function handleInvalidPoint() {
    setSelectedPoint(null);
    setRecommendations([]);
    setSelectedStationId(null);
    setIsPlaybackRunning(false);
    setSearchPlaybackProgress(1);
    setError("Choose a location inside the Shenzhen boundary.");
  }

  function resetPlanner() {
    setForm(DEFAULT_FORM);
    setLayerVisibility(DEFAULT_LAYER_VISIBILITY);
    setSelectedPoint(null);
    setSubmittedPoint(null);
    setRecommendations([]);
    setSelectedStationId(null);
    setIsPlaybackRunning(false);
    setSearchPlaybackProgress(1);
    setError(null);
  }

  useEffect(() => {
    fetchBoundary()
      .then(setBoundary)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load Shenzhen boundary."));
  }, []);

  async function handleRecommend() {
    if (!selectedPoint) return;
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetchRecommendations({
        lat: selectedPoint.lat,
        lng: selectedPoint.lng,
        algorithm: form.algorithm,
        max_candidates: form.maxCandidates,
        max_search_radius_km: form.maxSearchRadiusKm,
        max_drive_time_min: form.maxDriveTimeMin,
        current_soc: form.currentSocPercent / 100,
        battery_capacity_kwh: form.batteryCapacityKwh,
        consumption_kwh_per_km: form.consumptionKwhPer100Km / 100,
        min_arrival_soc: form.minArrivalSocPercent / 100,
        min_charge_count: form.minChargeCount,
        max_road_snap_distance_m: form.maxRoadSnapDistanceM,
        max_start_snap_distance_m: form.maxStartSnapDistanceM,
        top_k: form.maxCandidates,
      });
      setRecommendations(response.recommendations);
      setSubmittedPoint(selectedPoint);
      setSelectedStationId(response.recommendations[0]?.station_id ?? null);
      setSearchPlaybackProgress(1);
      setIsPlaybackRunning(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch recommendations.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    if (!isPlaybackRunning) return;
    const timer = window.setInterval(() => {
      setSearchPlaybackProgress((current) => {
        const next = Math.min(1, current + 0.035);
        if (next >= 1) window.clearInterval(timer);
        return next;
      });
    }, 70);
    return () => window.clearInterval(timer);
  }, [isPlaybackRunning]);

  useEffect(() => {
    if (searchPlaybackProgress >= 1) setIsPlaybackRunning(false);
  }, [searchPlaybackProgress]);

  return (
    <main className="app-shell">
      <aside className="control-panel">
        <WorkspaceHeader onReset={resetPlanner} />
        <PanelRenderer
          placement="left"
          openPanels={openPanels}
          panelSummaries={panelSummaries}
          onTogglePanel={togglePanel}
          renderPanel={(id) => {
            if (id === "search") {
              return (
                <SearchConfigurationPanel
                  form={form}
                  isLoading={isLoading}
                  canRecommend={Boolean(selectedPoint)}
                  onRecommend={handleRecommend}
                  onUpdateForm={updateForm}
                />
              );
            }
            if (id === "vehicle") {
              return <VehicleConstraintsPanel form={form} onUpdateForm={updateForm} />;
            }
            if (id === "algorithm") {
              return <AlgorithmConfigurationPanel form={form} onUpdateForm={updateForm} />;
            }
            if (id === "layers") {
              return <LayerDisplayPanel layerVisibility={layerVisibility} onUpdateLayer={updateLayer} />;
            }
            return null;
          }}
        />
      </aside>

      <section className="map-panel" aria-label="Route planning map">
        <div className="map-status-strip">
          <span>{selectedPoint ? "Start location selected" : "Choose a Shenzhen start location"}</span>
          <strong>{recommendations.length ? `${recommendations.length} candidates ranked` : "No run yet"}</strong>
        </div>
        <RouteMap
          basemap={form.basemap}
          boundary={boundary}
          selectedPoint={selectedPoint}
          recommendations={recommendations}
          selectedStationId={selectedStationId}
          searchPlaybackProgress={searchPlaybackProgress}
          layerVisibility={layerVisibility}
          onPointChange={handlePointChange}
          onInvalidPoint={handleInvalidPoint}
          onStationSelect={setSelectedStationId}
        />
      </section>

      <aside className="result-panel">
        {error && <div className="error-box">{error}</div>}
        <PanelRenderer
          placement="right"
          openPanels={openPanels}
          panelSummaries={panelSummaries}
          onTogglePanel={togglePanel}
          renderPanel={(id) => {
            if (id === "location") {
              return <LocationSummaryPanel selectedPoint={selectedPoint} submittedPoint={submittedPoint} />;
            }
            if (id === "recommendations") {
              return (
                <RecommendationListPanel
                  recommendations={recommendations}
                  selectedStationId={selectedStationId}
                  onStationSelect={setSelectedStationId}
                />
              );
            }
            if (id === "route") {
              return <SelectedRoutePanel selectedRecommendation={selectedRecommendation} />;
            }
            if (id === "playback") {
              return (
                <SearchPlaybackPanel
                  algorithm={form.algorithm}
                  selectedRecommendation={selectedRecommendation}
                  searchPlaybackProgress={searchPlaybackProgress}
                  isPlaybackRunning={isPlaybackRunning}
                  onReplay={() => {
                    setSearchPlaybackProgress(0);
                    setIsPlaybackRunning(true);
                  }}
                  onTogglePlayback={() => setIsPlaybackRunning((current) => !current)}
                  onProgressChange={(value) => {
                    setIsPlaybackRunning(false);
                    setSearchPlaybackProgress(value);
                  }}
                />
              );
            }
            return null;
          }}
        />
      </aside>
    </main>
  );
}

function WorkspaceHeader({ onReset }: { onReset: () => void }) {
  return (
    <header className="workspace-header">
      <div>
        <p className="eyebrow">OccuEVRoute</p>
        <h1>EV charging route planner</h1>
      </div>
      <button type="button" className="secondary-action" onClick={onReset}>
        Reset
      </button>
    </header>
  );
}

function PanelRenderer({
  placement,
  openPanels,
  panelSummaries,
  onTogglePanel,
  renderPanel,
}: {
  placement: PanelPlacement;
  openPanels: Record<PanelId, boolean>;
  panelSummaries: Record<PanelId, string>;
  onTogglePanel: (id: PanelId) => void;
  renderPanel: (id: PanelId) => ReactNode;
}) {
  return (
    <>
      {PANELS.filter((panel) => panel.enabled && panel.placement === placement).map((panel) => (
        <CollapsiblePanel
          key={panel.id}
          title={panel.title}
          eyebrow={panel.eyebrow}
          summary={panelSummaries[panel.id]}
          isOpen={openPanels[panel.id]}
          onToggle={() => onTogglePanel(panel.id)}
        >
          {renderPanel(panel.id)}
        </CollapsiblePanel>
      ))}
    </>
  );
}

function CollapsiblePanel({
  title,
  eyebrow,
  summary,
  isOpen,
  onToggle,
  children,
}: {
  title: string;
  eyebrow: string;
  summary: string;
  isOpen: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <section className="config-panel">
      <button type="button" className="panel-trigger" aria-expanded={isOpen} onClick={onToggle}>
        <span>
          <small>{eyebrow}</small>
          <strong>{title}</strong>
          {!isOpen && <em>{summary}</em>}
        </span>
        <span aria-hidden="true">{isOpen ? "-" : "+"}</span>
      </button>
      {isOpen && <div className="panel-body">{children}</div>}
    </section>
  );
}

function SearchConfigurationPanel({
  form,
  isLoading,
  canRecommend,
  onRecommend,
  onUpdateForm,
}: {
  form: FormState;
  isLoading: boolean;
  canRecommend: boolean;
  onRecommend: () => void;
  onUpdateForm: <T extends keyof FormState>(key: T, value: FormState[T]) => void;
}) {
  return (
    <>
      <SelectField label="Basemap" value={form.basemap} options={BASEMAP_LABELS} onChange={(value) => onUpdateForm("basemap", value as Basemap)} />
      <NumberField label="Candidate stations" value={form.maxCandidates} min={3} max={50} step={1} onChange={(value) => onUpdateForm("maxCandidates", value)} />
      <NumberField label="Max straight-line radius km" value={form.maxSearchRadiusKm} min={1} max={30} step={0.5} onChange={(value) => onUpdateForm("maxSearchRadiusKm", value)} />
      <NumberField label="Max driving time min" value={form.maxDriveTimeMin} min={5} max={90} step={5} onChange={(value) => onUpdateForm("maxDriveTimeMin", value)} />
      <button className="primary-action" disabled={!canRecommend || isLoading} onClick={onRecommend}>
        {isLoading ? "Calculating recommendations..." : "Recommend stations"}
      </button>
    </>
  );
}

function VehicleConstraintsPanel({
  form,
  onUpdateForm,
}: {
  form: FormState;
  onUpdateForm: <T extends keyof FormState>(key: T, value: FormState[T]) => void;
}) {
  return (
    <>
      <NumberField label="Current SOC %" value={form.currentSocPercent} min={1} max={100} step={1} onChange={(value) => onUpdateForm("currentSocPercent", value)} />
      <NumberField label="Battery capacity kWh" value={form.batteryCapacityKwh} min={20} max={150} step={1} onChange={(value) => onUpdateForm("batteryCapacityKwh", value)} />
      <NumberField label="Energy use kWh/100km" value={form.consumptionKwhPer100Km} min={8} max={35} step={0.1} onChange={(value) => onUpdateForm("consumptionKwhPer100Km", value)} />
      <NumberField label="Minimum arrival SOC %" value={form.minArrivalSocPercent} min={0} max={50} step={1} onChange={(value) => onUpdateForm("minArrivalSocPercent", value)} />
      <NumberField label="Minimum charger count" value={form.minChargeCount} min={1} max={100} step={1} onChange={(value) => onUpdateForm("minChargeCount", value)} />
    </>
  );
}

function AlgorithmConfigurationPanel({
  form,
  onUpdateForm,
}: {
  form: FormState;
  onUpdateForm: <T extends keyof FormState>(key: T, value: FormState[T]) => void;
}) {
  return (
    <>
      <SelectField label="Search algorithm" value={form.algorithm} options={ALGORITHM_LABELS} onChange={(value) => onUpdateForm("algorithm", value as Algorithm)} />
      <NumberField label="Max start snap distance m" value={form.maxStartSnapDistanceM} min={20} max={500} step={10} onChange={(value) => onUpdateForm("maxStartSnapDistanceM", value)} />
      <NumberField label="Max station snap distance m" value={form.maxRoadSnapDistanceM} min={20} max={500} step={10} onChange={(value) => onUpdateForm("maxRoadSnapDistanceM", value)} />
    </>
  );
}

function LayerDisplayPanel({
  layerVisibility,
  onUpdateLayer,
}: {
  layerVisibility: LayerVisibility;
  onUpdateLayer: (key: keyof LayerVisibility, value: boolean) => void;
}) {
  return (
    <div className="toggle-list">
      {LAYER_LABELS.map(([key, label, description]) => (
        <label className="toggle-row" key={key}>
          <input type="checkbox" checked={layerVisibility[key]} onChange={(event) => onUpdateLayer(key, event.target.checked)} />
          <span>
            <strong>{label}</strong>
            <small>{description}</small>
          </span>
        </label>
      ))}
    </div>
  );
}

function LocationSummaryPanel({ selectedPoint, submittedPoint }: { selectedPoint: Point | null; submittedPoint: Point | null }) {
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

function RecommendationListPanel({
  recommendations,
  selectedStationId,
  onStationSelect,
}: {
  recommendations: RecommendationItem[];
  selectedStationId: number | null;
  onStationSelect: (stationId: number) => void;
}) {
  if (!recommendations.length) {
    return <EmptyState title="No recommendations yet" message="Choose a location and run the planner to populate ranked charging stations." />;
  }

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Station</th>
            <th>time</th>
            <th>km</th>
            <th>SOC</th>
          </tr>
        </thead>
        <tbody>
          {recommendations.map((item, index) => (
            <tr
              key={`${item.station_id}-${index}`}
              className={[item.station_id === selectedStationId ? "selected-row" : "", index === 0 ? "top-row" : ""].filter(Boolean).join(" ")}
              onClick={() => item.station_id !== null && onStationSelect(item.station_id)}
            >
              <td data-label="#">{index === 0 ? "Top" : index + 1}</td>
              <td data-label="Station">{item.station_display_name ?? item.station_id}</td>
              <td data-label="Time">{formatMetric(item.drive_time_min)}</td>
              <td data-label="Distance">{formatMetric(item.distance_km)}</td>
              <td data-label="SOC">{item.arrival_soc === null ? "-" : `${(item.arrival_soc * 100).toFixed(1)}%`}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SelectedRoutePanel({ selectedRecommendation }: { selectedRecommendation: RecommendationItem | null }) {
  if (!selectedRecommendation) {
    return <EmptyState title="No selected route" message="Recommendation details will appear here after a successful planner run." />;
  }

  return (
    <>
      <div className="route-hero">
        <div>
          <span>Drive time</span>
          <strong>{formatMetric(selectedRecommendation.drive_time_min)} min</strong>
        </div>
        <div>
          <span>Distance</span>
          <strong>{formatMetric(selectedRecommendation.distance_km)} km</strong>
        </div>
        <div>
          <span>Arrival SOC</span>
          <strong>{selectedRecommendation.arrival_soc === null ? "-" : `${(selectedRecommendation.arrival_soc * 100).toFixed(1)}%`}</strong>
        </div>
      </div>
      <div className="metric-grid secondary-metrics">
        <Metric label="Start snap" value={`${formatMetric(selectedRecommendation.start_snap_distance_m)} m`} />
        <Metric label="Station snap" value={`${formatMetric(selectedRecommendation.road_snap_distance_m)} m`} />
        <Metric label="Nearby POI" value={formatPoiSummary(selectedRecommendation)} />
      </div>
    </>
  );
}

function SearchPlaybackPanel({
  algorithm,
  selectedRecommendation,
  searchPlaybackProgress,
  isPlaybackRunning,
  onReplay,
  onTogglePlayback,
  onProgressChange,
}: {
  algorithm: Algorithm;
  selectedRecommendation: RecommendationItem | null;
  searchPlaybackProgress: number;
  isPlaybackRunning: boolean;
  onReplay: () => void;
  onTogglePlayback: () => void;
  onProgressChange: (value: number) => void;
}) {
  if (!selectedRecommendation) {
    return <EmptyState title="No search trace yet" message="Run a recommendation to inspect expanded nodes and runtime." />;
  }

  return (
    <>
      <p className="panel-note">{playbackDescription(selectedRecommendation.search_trace.kind)}</p>
      <div className="metric-grid">
        <Metric label="Algorithm" value={algorithm.toUpperCase()} />
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
        <button type="button" onClick={onReplay}>
          Replay
        </button>
        <button type="button" onClick={onTogglePlayback}>
          {isPlaybackRunning ? "Pause" : "Play"}
        </button>
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

function SelectField<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: Record<T, string>;
  onChange: (value: T) => void;
}) {
  return (
    <label>
      {label}
      <select value={value} onChange={(event) => onChange(event.target.value as T)}>
        {Object.entries(options).map(([optionValue, optionLabel]) => (
          <option key={optionValue} value={optionValue}>
            {String(optionLabel)}
          </option>
        ))}
      </select>
    </label>
  );
}

function NumberField({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
}) {
  return (
    <label>
      {label}
      <input type="number" min={min} max={max} step={step} value={value} onChange={(event) => onChange(Number(event.target.value))} />
    </label>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function EmptyState({ title, message }: { title: string; message: string }) {
  return (
    <div className="empty-state">
      <strong>{title}</strong>
      <span>{message}</span>
    </div>
  );
}

function formatMetric(value: number | null) {
  return value === null ? "-" : value.toFixed(2);
}

function formatRuntime(seconds: number) {
  if (seconds < 1) return `${Math.round(seconds * 1000)} ms`;
  return `${seconds.toFixed(2)} s`;
}

function formatPoiSummary(item: RecommendationItem) {
  if (item.poi_total_count === null) return "-";
  return `${item.poi_total_count} / ${item.poi_lifestyle_services_count ?? 0} / ${item.poi_food_beverage_count ?? 0} / ${item.poi_business_residential_count ?? 0}`;
}

function playbackDescription(kind: SearchTraceKind) {
  if (kind === "bidirectional") {
    return "Replay the two road-search frontiers as they expand from the start and station access node.";
  }
  return "Replay the explored road area for the selected algorithm without changing the recommendation result.";
}

function traceLayerSize(item: RecommendationItem, role: "forward" | "backward") {
  return item.search_trace.layers.find((layer) => layer.role === role)?.coordinates.length ?? 0;
}

function layerSummary(layerVisibility: LayerVisibility) {
  const activeCount = Object.values(layerVisibility).filter(Boolean).length;
  return `${activeCount} of ${Object.keys(layerVisibility).length} layers visible`;
}
