import type { Algorithm } from "../../types";
import { NumberField, SelectField } from "../ui";
import { ALGORITHM_LABELS } from "./constants";
import type { FormState, FormUpdate } from "./types";

interface AlgorithmConfigurationPanelProps {
  form: FormState;
  onUpdateForm: FormUpdate;
}

export function AlgorithmConfigurationPanel({ form, onUpdateForm }: AlgorithmConfigurationPanelProps) {
  return (
    <>
      <SelectField label="Search algorithm" value={form.algorithm} options={ALGORITHM_LABELS} onChange={(value) => onUpdateForm("algorithm", value as Algorithm)} />
      <NumberField label="Max start snap distance m" value={form.maxStartSnapDistanceM} min={20} max={500} step={10} onChange={(value) => onUpdateForm("maxStartSnapDistanceM", value)} />
      <NumberField label="Max station snap distance m" value={form.maxRoadSnapDistanceM} min={20} max={500} step={10} onChange={(value) => onUpdateForm("maxRoadSnapDistanceM", value)} />
    </>
  );
}
