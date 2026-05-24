import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { fetchBoundary, fetchRecommendations } from "./api";
import {
  AlgorithmConfigurationPanel,
  algorithmShortLabel,
  DemoTimeExplanationPanel,
  type FormState,
  formatMetric,
  LayerDisplayPanel,
  LocationSummaryPanel,
  layerSummary,
  RecommendationListPanel,
  SearchConfigurationPanel,
  SearchPlaybackPanel,
  SelectedRoutePanel,
  VehicleConstraintsPanel,
  WorkspaceHeader,
} from "./components/planner";
import { Panel } from "./components/ui";
import { RouteMap } from "./map/RouteMap";
import type { BoundaryGeoJson, LayerVisibility, Point, RankingMetric, RecommendationItem } from "./types";

type PanelPlacement = "left" | "right";
type PanelId =
  | "search"
  | "vehicle"
  | "algorithm"
  | "layers"
  | "location"
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
  { id: "search", title: "Search configuration", eyebrow: "Plan", placement: "left", defaultOpen: true, enabled: true },
  { id: "vehicle", title: "Vehicle constraints", eyebrow: "Feasibility", placement: "left", defaultOpen: false, enabled: true },
  { id: "algorithm", title: "Algorithm configuration", eyebrow: "Advanced", placement: "left", defaultOpen: false, enabled: true },
  { id: "layers", title: "Layer display", eyebrow: "Map", placement: "left", defaultOpen: false, enabled: true },
  { id: "location", title: "Current location", eyebrow: "Input", placement: "right", defaultOpen: true, enabled: true },
  { id: "recommendations", title: "Recommendation list", eyebrow: "Output", placement: "right", defaultOpen: true, enabled: true },
  { id: "route", title: "Selected route detail", eyebrow: "Explain", placement: "right", defaultOpen: true, enabled: true },
  { id: "demoTime", title: "Demo time / ML explanation", eyebrow: "Prediction", placement: "right", defaultOpen: false, enabled: true },
  { id: "playback", title: "Search playback", eyebrow: "Diagnostics", placement: "right", defaultOpen: false, enabled: true },
];

const initialPanelState = Object.fromEntries(PANELS.map((panel) => [panel.id, panel.defaultOpen])) as Record<PanelId, boolean>;

export function App() {
  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  const [layerVisibility, setLayerVisibility] = useState<LayerVisibility>(DEFAULT_LAYER_VISIBILITY);
  const [openPanels, setOpenPanels] = useState<Record<PanelId, boolean>>(initialPanelState);
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
      search: `${form.maxSearchRadiusKm} km radius, ${form.maxDriveTimeMin} min cap`,
      vehicle: `${form.currentSocPercent}% SOC, ${form.batteryCapacityKwh} kWh battery`,
      algorithm: `${form.algorithm.toUpperCase()}, snap ${form.maxStartSnapDistanceM}/${form.maxRoadSnapDistanceM} m`,
      layers: layerSummary(layerVisibility),
      location: selectedPoint ? `${selectedPoint.lat.toFixed(4)}, ${selectedPoint.lng.toFixed(4)}` : "Waiting for map click",
      recommendations: rankedRecommendations.length ? `${rankedRecommendations.length} ranked by ${form.rankingMetric.replace("_", " ")}` : `${form.rankingMetric.replace("_", " ")} ranking`,
      route: selectedRecommendation ? `${formatMetric(selectedRecommendation.drive_time_min)} min, ${formatMetric(selectedRecommendation.distance_km)} km` : "No route selected",
      demoTime: selectedRecommendation ? `${formatMetric(selectedRecommendation.prediction_horizon_min)} min horizon` : "No prediction yet",
      playback: selectedRecommendation ? `${selectedRecommendation.expanded_nodes} expanded nodes` : "No trace yet",
    }),
    [form, layerVisibility, rankedRecommendations.length, selectedPoint, selectedRecommendation],
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

  function handleInvalidPoint() {
    setSelectedPoint(null);
    setRecommendations([]);
    setRankingOrders(EMPTY_RANKING_ORDERS);
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
    setRankingOrders(EMPTY_RANKING_ORDERS);
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
            if (id === "vehicle") return <VehicleConstraintsPanel form={form} onUpdateForm={updateForm} />;
            if (id === "algorithm") return <AlgorithmConfigurationPanel form={form} onUpdateForm={updateForm} />;
            if (id === "layers") return <LayerDisplayPanel layerVisibility={layerVisibility} onUpdateLayer={updateLayer} />;
            return null;
          }}
        />
      </aside>

      <section className="map-panel" aria-label="Route planning map">
        <div className="map-status-strip">
          <span>{selectedPoint ? "Start selected" : "Choose Shenzhen start"}</span>
          <strong>{algorithmShortLabel(form.algorithm)}</strong>
          <span>{rankedRecommendations.length ? `${rankedRecommendations.length} ranked` : "No run"}</span>
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
            if (id === "location") return <LocationSummaryPanel selectedPoint={selectedPoint} submittedPoint={submittedPoint} />;
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
