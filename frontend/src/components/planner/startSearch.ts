import type { LocationSearchResult, Point } from "../../types";

export interface StartSearchResult {
  id: string;
  label: string;
  point: Point;
}

export function coordinateSearchResult(query: string): StartSearchResult | null {
  const parsed = parseCoordinate(query);
  if (!parsed) return null;
  return { id: "coordinate", label: "Use coordinates", point: parsed };
}

export function startSearchResult(result: LocationSearchResult, index: number): StartSearchResult {
  return {
    id: `${result.lat},${result.lng},${index}`,
    label: result.label,
    point: { lat: result.lat, lng: result.lng },
  };
}

function parseCoordinate(query: string): Point | null {
  const match = query.trim().match(/^(-?\d+(?:\.\d+)?)\s*[,，\s]\s*(-?\d+(?:\.\d+)?)$/);
  if (!match) return null;

  const first = Number(match[1]);
  const second = Number(match[2]);
  if (!Number.isFinite(first) || !Number.isFinite(second)) return null;

  if (Math.abs(first) <= 90 && Math.abs(second) <= 180) return { lat: first, lng: second };
  if (Math.abs(second) <= 90 && Math.abs(first) <= 180) return { lat: second, lng: first };
  return null;
}
