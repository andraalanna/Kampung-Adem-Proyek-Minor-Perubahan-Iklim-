import type { Feature, Geometry } from "geojson";
import type { Layer, PathOptions } from "leaflet";
import { useEffect } from "react";
import { GeoJSON, MapContainer, TileLayer, useMap } from "react-leaflet";
import { useNavigate } from "react-router-dom";
import { c, date, dt, LST_BREAKS, LST_RAMP, lstColor, pct, STATUS_META, STATUS_ORDER } from "../format";
import type { HeatmapFC, HeatProps } from "../types";
import { geoBounds } from "./geo";

export type MapLayer = "status" | "lst";

function FitBounds({ data }: { data: HeatmapFC }) {
  const map = useMap();
  useEffect(() => {
    const b = geoBounds(data);
    if (b) map.fitBounds(b, { padding: [20, 20] });
  }, [data, map]);
  return null;
}

function popupHtml(p: HeatProps, layer: MapLayer): string {
  const m = STATUS_META[p.status];
  const est = p.is_estimate
    ? `<div style="color:#6b7280">Perkiraan (${p.estimate_method === "idw" ? "dari sensor terdekat" : "tanpa sensor"}), tidak memicu WhatsApp</div>`
    : `<div style="color:#6b7280">${p.n_sensors} sensor, keyakinan ${p.confidence}</div>`;
  const lst =
    layer === "lst"
      ? `<div>Suhu permukaan (LST satelit): <b>${c(p.lst_c)}</b><br/><span style="color:#6b7280">Citra ${date(p.lst_scene_date)}. Bukan suhu udara.</span></div>`
      : "";
  return `<div style="min-width:200px;font-size:13px">
    <div style="font-weight:600;margin-bottom:4px">${p.name}</div>
    <div style="margin-bottom:4px"><span style="background:${m.color};color:${m.text};border-radius:9999px;padding:1px 8px;font-size:12px;font-weight:600">${m.icon} ${m.label}</span></div>
    <div>Indeks panas: <b>${c(p.heat_index_c)}</b></div>
    <div>Suhu udara: ${c(p.air_temp_c)} · Kelembapan: ${pct(p.rh_pct)}</div>
    ${est}${lst}
    <div style="color:#6b7280;margin-top:4px">${dt(p.ts)}</div>
    <a href="/rw/${p.rw_id}" data-rw="${p.rw_id}">Lihat detail</a>
  </div>`;
}

export default function HeatMap({
  data,
  layer = "status",
  height = 480,
}: {
  data: HeatmapFC;
  layer?: MapLayer;
  height?: number;
}) {
  const navigate = useNavigate();

  const style = (f?: Feature<Geometry, HeatProps>): PathOptions => {
    const p = f!.properties;
    const fill = layer === "lst" ? lstColor(p.lst_c) : STATUS_META[p.status].color;
    return {
      color: "#ffffff",
      weight: 2,
      fillColor: fill,
      fillOpacity: p.is_estimate && layer === "status" ? 0.35 : 0.75,
      dashArray: p.is_estimate ? "4 4" : undefined,
    };
  };

  const onEach = (f: Feature<Geometry, HeatProps>, l: Layer) => {
    l.bindPopup(popupHtml(f.properties, layer));
    l.on("popupopen", (e) => {
      const a = (e.popup.getElement() as HTMLElement | undefined)?.querySelector("a[data-rw]");
      a?.addEventListener("click", (ev) => {
        ev.preventDefault();
        navigate(`/rw/${f.properties.rw_id}`);
      });
    });
    l.on("mouseover", () => (l as unknown as { setStyle: (s: PathOptions) => void }).setStyle({ weight: 4 }));
    l.on("mouseout", () => (l as unknown as { setStyle: (s: PathOptions) => void }).setStyle({ weight: 2 }));
  };

  const withGeom = { ...data, features: data.features.filter((f) => f.geometry) };

  return (
    <div className="relative">
      <MapContainer
        center={[-7.2575, 112.7521]}
        zoom={14}
        style={{ height, borderRadius: 8 }}
        scrollWheelZoom
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          className="grayscale-[60%]"
        />
        <GeoJSON
          key={`${layer}-${data.generated_at}`}
          data={withGeom as unknown as GeoJSON.FeatureCollection}
          style={style as never}
          onEachFeature={onEach as never}
        />
        <FitBounds data={withGeom} />
      </MapContainer>
      <Legend data={data} layer={layer} />
    </div>
  );
}

function Legend({ data, layer }: { data: HeatmapFC; layer: MapLayer }) {
  return (
    <div className="absolute top-2 right-2 z-[1000] rounded-md bg-white/95 p-2 text-xs shadow">
      {layer === "status" ? (
        <>
          <div className="mb-1 font-semibold">Status RW (indeks panas)</div>
          {STATUS_ORDER.map((s) => (
            <div key={s} className="flex items-center gap-1.5">
              <span className="inline-block h-3 w-3 rounded-sm" style={{ background: STATUS_META[s].color }} />
              <span aria-hidden>{STATUS_META[s].icon}</span>
              {STATUS_META[s].label}
            </div>
          ))}
          <div className="mt-1 flex items-center gap-1.5">
            <span className="inline-block h-3 w-3 rounded-sm border border-dashed border-gray-500" />
            Perkiraan (tanpa sensor di RW)
          </div>
        </>
      ) : (
        <>
          <div className="mb-1 font-semibold">Suhu permukaan (LST), bukan suhu udara</div>
          {LST_RAMP.map((col, i) => (
            <div key={col} className="flex items-center gap-1.5">
              <span className="inline-block h-3 w-3 rounded-sm" style={{ background: col }} />
              {i === 0
                ? `< ${LST_BREAKS[0]} °C`
                : i === LST_RAMP.length - 1
                  ? `≥ ${LST_BREAKS[i - 1]} °C`
                  : `${LST_BREAKS[i - 1]} - ${LST_BREAKS[i]} °C`}
            </div>
          ))}
          <div className="mt-1 text-ink-3">Citra satelit: {date(data.lst_scene_date)}</div>
        </>
      )}
      <div className="mt-1 border-t border-gray-200 pt-1 text-ink-3">Data: {dt(data.generated_at)}</div>
    </div>
  );
}
