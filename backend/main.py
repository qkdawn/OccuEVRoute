"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.schemas import HealthResponse, RecommendationRequest, RecommendationResponse
from backend.services.geo_data import shenzhen_boundary_geojson
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


@app.post("/api/recommendations", response_model=RecommendationResponse)
def recommendations(request: RecommendationRequest) -> RecommendationResponse:
    try:
        return recommend(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
