import { NumberField } from "../ui";
import type { FormState, FormUpdate } from "./types";

interface VehicleConstraintsPanelProps {
  form: FormState;
  onUpdateForm: FormUpdate;
}

export function VehicleConstraintsPanel({ form, onUpdateForm }: VehicleConstraintsPanelProps) {
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
