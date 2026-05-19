import { useEffect, useMemo, useState } from "react";
import { fetchBoundary, fetchRecommendations } from "./api";
import { RouteMap } from "./map/RouteMap";
import type { Algorithm, Basemap, BoundaryGeoJson, Point, RecommendationItem } from "./types";

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

const BASEMAP_LABELS: Record<Basemap, string> = {
  gaode: "Amap",
  carto: "CartoDB Light",
  osm: "OpenStreetMap",
};

const ALGORITHM_LABELS: Record<Algorithm, string> = {
  astar: "A*: Estimated-time guided search",
  ucs: "UCS: Shortest travel time",
  bfs: "BFS: Road-segment baseline",
};

export function App() {
  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  const [selectedPoint, setSelectedPoint] = useState<Point | null>(null);
  const [submittedPoint, setSubmittedPoint] = useState<Point | null>(null);
  const [recommendations, setRecommendations] = useState<RecommendationItem[]>([]);
  const [selectedStationId, setSelectedStationId] = useState<number | null>(null);
  const [boundary, setBoundary] = useState<BoundaryGeoJson | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedRecommendation = useMemo(() => {
    return recommendations.find((item) => item.station_id === selectedStationId) ?? recommendations[0] ?? null;
  }, [recommendations, selectedStationId]);

  function updateForm<T extends keyof FormState>(key: T, value: FormState[T]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function handlePointChange(point: Point) {
    setSelectedPoint(point);
    setRecommendations([]);
    setSelectedStationId(null);
    setError(null);
  }

  function handleInvalidPoint() {
    setSelectedPoint(null);
    setRecommendations([]);
    setSelectedStationId(null);
    setError("Please choose a location within Shenzhen.");
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
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch recommendations.");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="app-shell">
      <aside className="control-panel">
        <div>
          <p className="eyebrow">OccuEVRoute</p>
          <h1>EV Charging Route Planner</h1>
        </div>

        <label>
          Basemap
          <select value={form.basemap} onChange={(event) => updateForm("basemap", event.target.value as Basemap)}>
            {Object.entries(BASEMAP_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>

        <label>
          Search Algorithm
          <select value={form.algorithm} onChange={(event) => updateForm("algorithm", event.target.value as Algorithm)}>
            {Object.entries(ALGORITHM_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>

        <NumberField label="Candidate Stations" value={form.maxCandidates} min={3} max={50} step={1} onChange={(value) => updateForm("maxCandidates", value)} />
        <NumberField label="Max Straight-Line Radius km" value={form.maxSearchRadiusKm} min={1} max={30} step={0.5} onChange={(value) => updateForm("maxSearchRadiusKm", value)} />
        <NumberField label="Max Driving Time min" value={form.maxDriveTimeMin} min={5} max={90} step={5} onChange={(value) => updateForm("maxDriveTimeMin", value)} />
        <NumberField label="Current SOC %" value={form.currentSocPercent} min={1} max={100} step={1} onChange={(value) => updateForm("currentSocPercent", value)} />
        <NumberField label="Battery Capacity kWh" value={form.batteryCapacityKwh} min={20} max={150} step={1} onChange={(value) => updateForm("batteryCapacityKwh", value)} />
        <NumberField label="Energy Use kWh/100km" value={form.consumptionKwhPer100Km} min={8} max={35} step={0.1} onChange={(value) => updateForm("consumptionKwhPer100Km", value)} />
        <NumberField label="Minimum Arrival SOC %" value={form.minArrivalSocPercent} min={0} max={50} step={1} onChange={(value) => updateForm("minArrivalSocPercent", value)} />
        <NumberField label="Minimum Charger Count" value={form.minChargeCount} min={1} max={100} step={1} onChange={(value) => updateForm("minChargeCount", value)} />
        <NumberField label="Max Start Snap Distance m" value={form.maxStartSnapDistanceM} min={20} max={500} step={10} onChange={(value) => updateForm("maxStartSnapDistanceM", value)} />
        <NumberField label="Max Station Snap Distance m" value={form.maxRoadSnapDistanceM} min={20} max={500} step={10} onChange={(value) => updateForm("maxRoadSnapDistanceM", value)} />

        <button className="primary-action" disabled={!selectedPoint || isLoading} onClick={handleRecommend}>
          {isLoading ? "Calculating..." : "Recommend Stations"}
        </button>
      </aside>

      <section className="map-panel">
        <RouteMap
          basemap={form.basemap}
          boundary={boundary}
          selectedPoint={selectedPoint}
          recommendations={recommendations}
          selectedStationId={selectedStationId}
          onPointChange={handlePointChange}
          onInvalidPoint={handleInvalidPoint}
          onStationSelect={setSelectedStationId}
        />
      </section>

      <aside className="result-panel">
        <section className="summary-block">
          <p className="eyebrow">Current Location</p>
          <strong>{selectedPoint ? `${selectedPoint.lat.toFixed(6)}, ${selectedPoint.lng.toFixed(6)}` : "Click the map to choose a location"}</strong>
          {submittedPoint && (
            <span>
              Recommended for: {submittedPoint.lat.toFixed(6)}, {submittedPoint.lng.toFixed(6)}
            </span>
          )}
        </section>

        {error && <div className="error-box">{error}</div>}

        <label>
          Show Route To
          <select
            value={selectedStationId ?? ""}
            disabled={!recommendations.length}
            onChange={(event) => setSelectedStationId(Number(event.target.value))}
          >
            {recommendations.map((item, index) => (
              <option key={`${item.station_id}-${index}`} value={item.station_id ?? ""}>
                Top {index + 1} - {item.station_display_name ?? item.station_id} - {formatMetric(item.drive_time_min)} min -{" "}
                {formatMetric(item.distance_km)} km
              </option>
            ))}
          </select>
        </label>

        <section className="summary-block">
          <p className="eyebrow">Selected Route</p>
          {selectedRecommendation ? (
            <div className="metric-grid">
              <Metric label="Time" value={`${formatMetric(selectedRecommendation.drive_time_min)} min`} />
              <Metric label="Distance" value={`${formatMetric(selectedRecommendation.distance_km)} km`} />
              <Metric label="Arrival SOC" value={selectedRecommendation.arrival_soc === null ? "-" : `${(selectedRecommendation.arrival_soc * 100).toFixed(1)}%`} />
              <Metric label="Start Snap" value={`${formatMetric(selectedRecommendation.start_snap_distance_m)} m`} />
              <Metric label="Station Snap" value={`${formatMetric(selectedRecommendation.road_snap_distance_m)} m`} />
              <Metric label="Nearby POI" value={formatPoiSummary(selectedRecommendation)} />
            </div>
          ) : (
            <span>No recommendations yet</span>
          )}
        </section>

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
                  className={item.station_id === selectedStationId ? "selected-row" : ""}
                  onClick={() => item.station_id !== null && setSelectedStationId(item.station_id)}
                >
                  <td>{index + 1}</td>
                  <td>{item.station_display_name ?? item.station_id}</td>
                  <td>{formatMetric(item.drive_time_min)}</td>
                  <td>{formatMetric(item.distance_km)}</td>
                  <td>{item.arrival_soc === null ? "-" : `${(item.arrival_soc * 100).toFixed(1)}%`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </aside>
    </main>
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
      <input
        type="number"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
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

function formatMetric(value: number | null) {
  return value === null ? "-" : value.toFixed(2);
}

function formatPoiSummary(item: RecommendationItem) {
  if (item.poi_total_count === null) return "-";
  return `${item.poi_total_count} / ${item.poi_lifestyle_services_count ?? 0} / ${item.poi_food_beverage_count ?? 0} / ${item.poi_business_residential_count ?? 0}`;
}
