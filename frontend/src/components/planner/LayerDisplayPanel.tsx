import type { LayerVisibility } from "../../types";
import { LAYER_LABELS } from "./constants";

interface LayerDisplayPanelProps {
  layerVisibility: LayerVisibility;
  onUpdateLayer: (key: keyof LayerVisibility, value: boolean) => void;
}

export function LayerDisplayPanel({ layerVisibility, onUpdateLayer }: LayerDisplayPanelProps) {
  return (
    <div className="toggle-list">
      {LAYER_LABELS.map(([key, label, description]) => (
        <label className="toggle-row" key={key}>
          <input type="checkbox" checked={layerVisibility[key]} onChange={(event) => onUpdateLayer(key, event.target.checked)} />
          <span className="toggle-control" aria-hidden="true" />
          <span>
            <strong>{label}</strong>
            <small>{description}</small>
          </span>
        </label>
      ))}
    </div>
  );
}
