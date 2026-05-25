import L from "leaflet";
import chargerLargeIcon from "../assets/charger-icons/charger-large.png";
import chargerMediumIcon from "../assets/charger-icons/charger-medium.png";
import chargerSmallIcon from "../assets/charger-icons/charger-small.png";

type StationIconTier = "small" | "medium" | "large";

const CHARGER_ICON_BY_TIER: Record<StationIconTier, string> = {
  small: chargerSmallIcon,
  medium: chargerMediumIcon,
  large: chargerLargeIcon,
};

export function createStationIcon(selected: boolean, chargeCount: number | null) {
  const tier = stationIconTier(chargeCount);
  const size = stationIconSize(selected, tier);
  const iconUrl = CHARGER_ICON_BY_TIER[tier];

  return L.divIcon({
    className: "",
    html: `
      <div class="station-image-marker tier-${tier}${selected ? " selected" : ""}" style="width:${size}px;height:${size}px">
        <img src="${iconUrl}" alt="" aria-hidden="true" style="width:${size}px;height:${size}px" />
      </div>
    `,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

function stationIconTier(chargeCount: number | null): StationIconTier {
  const count = chargeCount ?? 0;
  if (count <= 8) return "small";
  if (count <= 24) return "medium";
  return "large";
}

function stationIconSize(selected: boolean, tier: StationIconTier) {
  const baseSize = tier === "small" ? 28 : tier === "medium" ? 34 : 42;
  return selected ? Math.min(baseSize + 8, 52) : baseSize;
}
