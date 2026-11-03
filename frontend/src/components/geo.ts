import type { LatLngBoundsExpression } from "leaflet";
import type { HeatmapFC } from "../types";

/** Bounding box [[south, west], [north, east]] of all polygon coordinates, or null. */
export function geoBounds(fc: HeatmapFC): LatLngBoundsExpression | null {
  let s = 90,
    w = 180,
    n = -90,
    e = -180,
    any = false;
  const visit = (c: unknown): void => {
    if (Array.isArray(c) && typeof c[0] === "number") {
      const [lon, lat] = c as number[];
      s = Math.min(s, lat);
      n = Math.max(n, lat);
      w = Math.min(w, lon);
      e = Math.max(e, lon);
      any = true;
    } else if (Array.isArray(c)) c.forEach(visit);
  };
  for (const f of fc.features) {
    if (f.geometry && "coordinates" in f.geometry) visit(f.geometry.coordinates);
  }
  return any ? [[s, w], [n, e]] : null;
}
