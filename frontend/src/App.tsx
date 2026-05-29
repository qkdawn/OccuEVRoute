import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { fetchBoundary, fetchRecommendations } from "./api";
import {
  algorithmShortLabel,
  DemoTimeExplanationPanel,
  type FormState,
  formatMetric,
  PlannerSettingsPanel,
  RecommendationListPanel,
  SearchConfigurationPanel,
  SearchPlaybackPanel,
  SelectedRoutePanel,
  WorkspaceHeader,
} from "./components/planner";
import { Panel } from "./components/ui";
import { pointInBoundary } from "./map/boundary";
import { RouteMap } from "./map/RouteMap";
import type { BoundaryGeoJson, LayerVisibility, Point, RankingMetric, RecommendationItem } from "./types";

type PanelPlacement = "left" | "right";
type PanelId =
  | "search"
  | "recommendations"
  | "route"
  | "demoTime"
  | "playback";

interface PanelConfig {
  defaultOpen: boolean;
  enabled: boolean;
  eyebrow: string;
  id: PanelId;
  placement: PanelPlacement;
  title: string;
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
  rankingMetric: "balanced",
};

const DEFAULT_LAYER_VISIBILITY: LayerVisibility = {
  boundary: true,
  stations: true,
  route: true,
  searchTrace: true,
  snapLines: true,
};

const EMPTY_RANKING_ORDERS: Record<RankingMetric, number[]> = {
  balanced: [],
  drive_time: [],
  distance: [],
  occupancy: [],
  arrival_soc: [],
};

const PANELS: PanelConfig[] = [
  { id: "search", title: "Plan route", eyebrow: "Plan", placement: "left", defaultOpen: true, enabled: true },
  { id: "recommendations", title: "Stations", eyebrow: "Output", placement: "right", defaultOpen: true, enabled: true },
  { id: "route", title: "Route", eyebrow: "Explain", placement: "right", defaultOpen: true, enabled: true },
  { id: "demoTime", title: "Demand", eyebrow: "Prediction", placement: "right", defaultOpen: false, enabled: true },
  { id: "playback", title: "Trace", eyebrow: "Diagnostics", placement: "right", defaultOpen: false, enabled: true },
];

const initialPanelState = Object.fromEntries(PANELS.map((panel) => [panel.id, panel.defaultOpen])) as Record<PanelId, boolean>;

export function App() {
  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  const [layerVisibility, setLayerVisibility] = useState<LayerVisibility>(DEFAULT_LAYER_VISIBILITY);
  const [openPanels, setOpenPanels] = useState<Record<PanelId, boolean>>(initialPanelState);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [selectedPoint, setSelectedPoint] = useState<Point | null>(null);
  const [submittedPoint, setSubmittedPoint] = useState<Point | null>(null);
  const [recommendations, setRecommendations] = useState<RecommendationItem[]>([]);
  const [rankingOrders, setRankingOrders] = useState<Record<RankingMetric, number[]>>(EMPTY_RANKING_ORDERS);
  const [selectedStationId, setSelectedStationId] = useState<number | null>(null);
  const [boundary, setBoundary] = useState<BoundaryGeoJson | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isPlaybackRunning, setIsPlaybackRunning] = useState(false);
  const [searchPlaybackProgress, setSearchPlaybackProgress] = useState(1);
  const [error, setError] = useState<string | null>(null);

  const rankedRecommendations = useMemo(() => {
    return rankRecommendations(recommendations, rankingOrders[form.rankingMetric]).slice(0, form.maxCandidates);
  }, [form.maxCandidates, form.rankingMetric, recommendations, rankingOrders]);

  const selectedRecommendation = useMemo(() => {
    return rankedRecommendations.find((item) => item.station_id === selectedStationId) ?? rankedRecommendations[0] ?? null;
  }, [rankedRecommendations, selectedStationId]);

  const panelSummaries = useMemo<Record<PanelId, string>>(
    () => ({
      search: selectedPoint ? `${selectedPoint.lat.toFixed(3)}, ${selectedPoint.lng.toFixed(3)}` : "No start",
      recommendations: rankedRecommendations.length ? `${rankedRecommendations.length} stations` : form.rankingMetric.replace("_", " "),
      route: selectedRecommendation ? `${formatMetric(selectedRecommendation.drive_time_min)} min · ${formatMetric(selectedRecommendation.distance_km)} km` : "None",
      demoTime: selectedRecommendation ? `${formatMetric(selectedRecommendation.prediction_horizon_min)} min` : "None",
      playback: selectedRecommendation ? `${selectedRecommendation.expanded_nodes} nodes` : "None",
    }),
    [form.rankingMetric, rankedRecommendations.length, selectedPoint, selectedRecommendation],
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
    setRankingOrders(EMPTY_RANKING_ORDERS);
    setSelectedStationId(null);
    setIsPlaybackRunning(false);
    setSearchPlaybackProgress(1);
    setError(null);
  }

  function handleSearchPointSelect(point: Point) {
    if (boundary && !pointInBoundary(point, boundary)) {
      handleInvalidPoint();
      return;
    }
    handlePointChange(point);
  }

  function handleInvalidPoint() {
    setSelectedPoint(null);
    setRecommendations([]);
    setRankingOrders(EMPTY_RANKING_ORDERS);
    setSelectedStationId(null);
    setIsPlaybackRunning(false);
    setSearchPlaybackProgress(1);
    setError("Choose a location inside the Shenzhen boundary.");
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
        ranking_metric: form.rankingMetric,
        top_k: form.maxCandidates,
      });
      setRecommendations(response.recommendations);
      setRankingOrders(response.ranking_orders);
      setSubmittedPoint(selectedPoint);
      setSelectedStationId(response.ranking_orders[form.rankingMetric][0] ?? response.recommendations[0]?.station_id ?? null);
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
        <WorkspaceHeader />
        <PanelRenderer
          placement="left"
          openPanels={openPanels}
          panelSummaries={panelSummaries}
          onTogglePanel={togglePanel}
          renderPanel={(id) => {
            if (id === "search") {
              return (
                <SearchConfigurationPanel
                  isLoading={isLoading}
                  canRecommend={Boolean(selectedPoint)}
                  onRecommend={handleRecommend}
                  onStartSelect={handleSearchPointSelect}
                  selectedPoint={selectedPoint}
                  submittedPoint={submittedPoint}
                />
              );
            }
            return null;
          }}
        />
        <div className="settings-dock">
          <button type="button" className="settings-button" aria-expanded={isSettingsOpen} onClick={() => setIsSettingsOpen((current) => !current)}>
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M4 7h10" />
              <path d="M18 7h2" />
              <path d="M4 17h2" />
              <path d="M10 17h10" />
              <circle cx="16" cy="7" r="2" />
              <circle cx="8" cy="17" r="2" />
            </svg>
            <span>Settings</span>
          </button>
          {isSettingsOpen && (
            <div className="settings-popover">
              <PlannerSettingsPanel form={form} layerVisibility={layerVisibility} onUpdateForm={updateForm} onUpdateLayer={updateLayer} />
            </div>
          )}
        </div>
      </aside>

      <section className="map-panel" aria-label="Route planning map">
        <div className="map-status-strip">
          <span>{selectedPoint ? "Start selected" : "Choose Shenzhen start"}</span>
          <strong>{algorithmShortLabel(form.algorithm)}</strong>
          <span>{rankedRecommendations.length ? `${rankedRecommendations.length} ranked` : "No run"}</span>
          {selectedRecommendation && <span>{`${selectedRecommendation.expanded_nodes} expanded`}</span>}
          {selectedRecommendation && <span>{`${(selectedRecommendation.runtime_seconds * 1000).toFixed(1)} ms`}</span>}
        </div>
        <RouteMap
          basemap={form.basemap}
          boundary={boundary}
          selectedPoint={selectedPoint}
          recommendations={rankedRecommendations}
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
            if (id === "recommendations") {
              return (
                <RecommendationListPanel
                  form={form}
                  recommendations={rankedRecommendations}
                  selectedStationId={selectedStationId}
                  onStationSelect={setSelectedStationId}
                  onUpdateForm={updateForm}
                />
              );
            }
            if (id === "route") return <SelectedRoutePanel selectedRecommendation={selectedRecommendation} />;
            if (id === "demoTime") return <DemoTimeExplanationPanel selectedRecommendation={selectedRecommendation} />;
            if (id === "playback") {
              return (
                <SearchPlaybackPanel
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

function rankRecommendations(recommendations: RecommendationItem[], order: number[]) {
  if (!recommendations.length || !order.length) return recommendations;
  const byStationId = new Map(recommendations.map((item) => [item.station_id, item]));
  const ranked = order.flatMap((stationId) => {
    const item = byStationId.get(stationId);
    return item ? [item] : [];
  });
  const rankedIds = new Set(ranked.map((item) => item.station_id));
  const unranked = recommendations.filter((item) => !rankedIds.has(item.station_id));
  return [...ranked, ...unranked];
}

function PanelRenderer({
  placement,
  openPanels,
  panelSummaries,
  onTogglePanel,
  renderPanel,
}: {
  openPanels: Record<PanelId, boolean>;
  panelSummaries: Record<PanelId, string>;
  placement: PanelPlacement;
  onTogglePanel: (id: PanelId) => void;
  renderPanel: (id: PanelId) => ReactNode;
}) {
  return (
    <>
      {PANELS.filter((panel) => panel.enabled && panel.placement === placement).map((panel) => (
        <Panel
          key={panel.id}
          title={panel.title}
          eyebrow={panel.eyebrow}
          summary={panelSummaries[panel.id]}
          isOpen={openPanels[panel.id]}
          onToggle={() => onTogglePanel(panel.id)}
        >
          {renderPanel(panel.id)}
        </Panel>
      ))}
    </>
  );
}
