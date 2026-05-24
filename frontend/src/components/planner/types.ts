import type { Algorithm, Basemap, RankingMetric } from "../../types";

export interface FormState {
  algorithm: Algorithm;
  basemap: Basemap;
  batteryCapacityKwh: number;
  consumptionKwhPer100Km: number;
  currentSocPercent: number;
  maxCandidates: number;
  maxDriveTimeMin: number;
  maxRoadSnapDistanceM: number;
  maxSearchRadiusKm: number;
  maxStartSnapDistanceM: number;
  minArrivalSocPercent: number;
  minChargeCount: number;
  rankingMetric: RankingMetric;
}

export type FormUpdate = <T extends keyof FormState>(key: T, value: FormState[T]) => void;
