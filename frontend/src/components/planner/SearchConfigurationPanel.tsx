import type { Basemap, RankingMetric } from "../../types";
import { Button, NumberField, SelectField } from "../ui";
import { BASEMAP_LABELS, RANKING_METRIC_LABELS } from "./constants";
import type { FormState, FormUpdate } from "./types";

interface SearchConfigurationPanelProps {
  canRecommend: boolean;
  form: FormState;
  isLoading: boolean;
  onRecommend: () => void;
  onUpdateForm: FormUpdate;
}

export function SearchConfigurationPanel({ canRecommend, form, isLoading, onRecommend, onUpdateForm }: SearchConfigurationPanelProps) {
  return (
    <>
      <SelectField label="Basemap" value={form.basemap} options={BASEMAP_LABELS} onChange={(value) => onUpdateForm("basemap", value as Basemap)} />
      <NumberField label="Candidate stations" value={form.maxCandidates} min={3} max={50} step={1} onChange={(value) => onUpdateForm("maxCandidates", value)} />
      <NumberField label="Max straight-line radius km" value={form.maxSearchRadiusKm} min={1} max={30} step={0.5} onChange={(value) => onUpdateForm("maxSearchRadiusKm", value)} />
      <NumberField label="Max driving time min" value={form.maxDriveTimeMin} min={5} max={90} step={5} onChange={(value) => onUpdateForm("maxDriveTimeMin", value)} />
      <SelectField
        label="Ranking metric"
        value={form.rankingMetric}
        options={RANKING_METRIC_LABELS}
        onChange={(value) => onUpdateForm("rankingMetric", value as RankingMetric)}
      />
      <Button variant="primary" disabled={!canRecommend} loading={isLoading} onClick={onRecommend}>
        Recommend stations
      </Button>
    </>
  );
}
