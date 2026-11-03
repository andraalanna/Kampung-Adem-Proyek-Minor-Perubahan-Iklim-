import { describe, expect, it } from "vitest";
import { c, lstColor, LST_RAMP, withGaps } from "./format";

describe("format", () => {
  it("formats degrees with Indonesian decimal comma", () => {
    expect(c(35.14)).toBe("35,1 °C");
    expect(c(null)).toBe("-");
  });

  it("maps LST to the one-hue ramp", () => {
    expect(lstColor(28)).toBe(LST_RAMP[0]);
    expect(lstColor(42)).toBe(LST_RAMP[3]);
    expect(lstColor(60)).toBe(LST_RAMP[4]);
  });

  it("inserts a null point at gaps instead of filling values", () => {
    const pts = [
      { ts: "2026-11-02T10:00:00+07:00", v: 1 },
      { ts: "2026-11-02T10:10:00+07:00", v: 2 },
      { ts: "2026-11-02T11:00:00+07:00", v: 3 },
    ];
    const out = withGaps(pts, 10 * 60 * 1000);
    expect(out).toHaveLength(4);
    expect("v" in out[2]).toBe(false);
  });
});
