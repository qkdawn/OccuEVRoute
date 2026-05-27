"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.schemas import HealthResponse, LocationSearchResult, RecommendationRequest, RecommendationResponse
from backend.services.geo_data import shenzhen_boundary_geojson
from backend.services.location_search import search_locations
from backend.services.recommendations import recommend, warmup_data


@asynccontextmanager
async def lifespan(app: FastAPI):
    warmup_data()
    yield


app = FastAPI(title="OccuEVRoute API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/api/boundary")
def boundary():
    return shenzhen_boundary_geojson()


@app.get("/api/location-search", response_model=list[LocationSearchResult])
def location_search(q: str, limit: int = 5) -> list[LocationSearchResult]:
    try:
        return search_locations(q, limit)
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Location search timed out.") from exc
    except OSError as exc:
        raise HTTPException(status_code=502, detail="Location search is unavailable.") from exc


@app.post("/api/recommendations", response_model=RecommendationResponse)
def recommendations(request: RecommendationRequest) -> RecommendationResponse:
    try:
        return recommend(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
