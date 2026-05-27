import type { BoundaryGeoJson, LocationSearchResult, RecommendationRequest, RecommendationResponse } from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export async function fetchRecommendations(
  request: RecommendationRequest,
): Promise<RecommendationResponse> {
  const response = await fetch(`${API_BASE_URL}/api/recommendations`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response));
  }
  return response.json();
}

export async function fetchBoundary(): Promise<BoundaryGeoJson> {
  const response = await fetch(`${API_BASE_URL}/api/boundary`);
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response));
  }
  return response.json();
}

export async function searchLocations(query: string): Promise<LocationSearchResult[]> {
  const params = new URLSearchParams({ q: query, limit: "5" });
  const response = await fetch(`${API_BASE_URL}/api/location-search?${params.toString()}`);
  if (!response.ok) {
    throw new Error(await responseErrorMessage(response));
  }
  return response.json();
}

async function responseErrorMessage(response: Response): Promise<string> {
  const text = await response.text();
  if (!text) return `Request failed with ${response.status}`;
  try {
    const payload = JSON.parse(text) as { detail?: unknown };
    return typeof payload.detail === "string" ? payload.detail : text;
  } catch {
    return text;
  }
}
