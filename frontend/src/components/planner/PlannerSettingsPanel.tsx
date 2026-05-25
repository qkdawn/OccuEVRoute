import type { Algorithm, Basemap, LayerVisibility } from "../../types";
import { NumberField, SelectField } from "../ui";
import { ALGORITHM_LABELS, BASEMAP_LABELS } from "./constants";
import { LayerDisplayPanel } from "./LayerDisplayPanel";
import type { FormState, FormUpdate } from "./types";

interface PlannerSettingsPanelProps {
  form: FormState;
  layerVisibility: LayerVisibility;
  onUpdateForm: FormUpdate;
  onUpdateLayer: (key: keyof LayerVisibility, value: boolean) => void;
}

export function PlannerSettingsPanel({ form, layerVisibility, onUpdateForm, onUpdateLayer }: PlannerSettingsPanelProps) {
  return (
    <div className="settings-panel">
      <section className="settings-group">
        <h3>Map</h3>
        <SelectField label="Basemap" value={form.basemap} options={BASEMAP_LABELS} onChange={(value) => onUpdateForm("basemap", value as Basemap)} />
        <LayerDisplayPanel layerVisibility={layerVisibility} onUpdateLayer={onUpdateLayer} />
      </section>

      <section className="settings-group">
        <h3>Recommendations</h3>
        <NumberField label="Recommendation limit" value={form.maxCandidates} min={3} max={50} step={1} onChange={(value) => onUpdateForm("maxCandidates", value)} />
      </section>

      <section className="settings-group">
        <h3>Vehicle</h3>
        <NumberField label="Current SOC %" value={form.currentSocPercent} min={1} max={100} step={1} onChange={(value) => onUpdateForm("currentSocPercent", value)} />
        <NumberField label="Battery capacity kWh" value={form.batteryCapacityKwh} min={20} max={150} step={1} onChange={(value) => onUpdateForm("batteryCapacityKwh", value)} />
        <NumberField label="Energy use kWh/100km" value={form.consumptionKwhPer100Km} min={8} max={35} step={0.1} onChange={(value) => onUpdateForm("consumptionKwhPer100Km", value)} />
        <NumberField label="Minimum arrival SOC %" value={form.minArrivalSocPercent} min={0} max={50} step={1} onChange={(value) => onUpdateForm("minArrivalSocPercent", value)} />
        <NumberField label="Minimum charger count" value={form.minChargeCount} min={1} max={100} step={1} onChange={(value) => onUpdateForm("minChargeCount", value)} />
      </section>

      <section className="settings-group">
        <h3>Algorithm</h3>
        <SelectField label="Search algorithm" value={form.algorithm} options={ALGORITHM_LABELS} onChange={(value) => onUpdateForm("algorithm", value as Algorithm)} />
        <NumberField label="Max start snap distance m" value={form.maxStartSnapDistanceM} min={20} max={500} step={10} onChange={(value) => onUpdateForm("maxStartSnapDistanceM", value)} />
        <NumberField label="Max station snap distance m" value={form.maxRoadSnapDistanceM} min={20} max={500} step={10} onChange={(value) => onUpdateForm("maxRoadSnapDistanceM", value)} />
      </section>
    </div>
  );
}
