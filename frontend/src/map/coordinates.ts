import type { Basemap, Point } from "../types";

const GAODE_BASEMAP: Basemap = "gaode";

function outsideChina(point: Point): boolean {
  return !(point.lng >= 72.004 && point.lng <= 137.8347 && point.lat >= 0.8293 && point.lat <= 55.8271);
}

function transformLat(x: number, y: number): number {
  let value = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * Math.sqrt(Math.abs(x));
  value += ((20.0 * Math.sin(6.0 * x * Math.PI) + 20.0 * Math.sin(2.0 * x * Math.PI)) * 2.0) / 3.0;
  value += ((20.0 * Math.sin(y * Math.PI) + 40.0 * Math.sin((y / 3.0) * Math.PI)) * 2.0) / 3.0;
  value += ((160.0 * Math.sin((y / 12.0) * Math.PI) + 320 * Math.sin((y * Math.PI) / 30.0)) * 2.0) / 3.0;
  return value;
}

function transformLng(x: number, y: number): number {
  let value = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * Math.sqrt(Math.abs(x));
  value += ((20.0 * Math.sin(6.0 * x * Math.PI) + 20.0 * Math.sin(2.0 * x * Math.PI)) * 2.0) / 3.0;
  value += ((20.0 * Math.sin(x * Math.PI) + 40.0 * Math.sin((x / 3.0) * Math.PI)) * 2.0) / 3.0;
  value += ((150.0 * Math.sin((x / 12.0) * Math.PI) + 300.0 * Math.sin((x / 30.0) * Math.PI)) * 2.0) / 3.0;
  return value;
}

function gcjDelta(point: Point): Point {
  const a = 6378245.0;
  const ee = 0.006693421622965943;
  const x = point.lng - 105.0;
  const y = point.lat - 35.0;
  let dlat = transformLat(x, y);
  let dlng = transformLng(x, y);
  const radlat = (point.lat / 180.0) * Math.PI;
  let magic = Math.sin(radlat);
  magic = 1 - ee * magic * magic;
  const sqrtMagic = Math.sqrt(magic);
  dlat = (dlat * 180.0) / (((a * (1 - ee)) / (magic * sqrtMagic)) * Math.PI);
  dlng = (dlng * 180.0) / ((a / sqrtMagic) * Math.cos(radlat) * Math.PI);
  return { lat: dlat, lng: dlng };
}

function wgs84ToGcj02(point: Point): Point {
  if (outsideChina(point)) return point;
  const delta = gcjDelta(point);
  return { lat: point.lat + delta.lat, lng: point.lng + delta.lng };
}

function gcj02ToWgs84(point: Point): Point {
  if (outsideChina(point)) return point;
  const delta = gcjDelta(point);
  return { lat: point.lat - delta.lat, lng: point.lng - delta.lng };
}

export function toMapPoint(point: Point, basemap: Basemap): Point {
  return basemap === GAODE_BASEMAP ? wgs84ToGcj02(point) : point;
}

export function fromMapPoint(point: Point, basemap: Basemap): Point {
  return basemap === GAODE_BASEMAP ? gcj02ToWgs84(point) : point;
}
