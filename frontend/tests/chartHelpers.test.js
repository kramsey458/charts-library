import { afterEach, describe, expect, it, vi } from "vitest";

import {
  buildChecklistSummary,
  buildEmptyChecklist,
  buildNotesPreview,
  chartHasFlag,
  fetchJson,
} from "../src/lib/chartHelpers.js";

describe("chartHelpers", () => {
  it("buildEmptyChecklist initializes all values to false", () => {
    const checklist = buildEmptyChecklist();
    expect(Object.values(checklist).every((value) => value === false)).toBe(true);
  });

  it("buildChecklistSummary returns selected labels", () => {
    const summary = buildChecklistSummary({ red_candle: true, trend_bearish: true, macd_minus_cross: true });
    expect(summary).toMatch(/Red Candle/);
    expect(summary).toMatch(/Trend Bearish/);
    expect(summary).toMatch(/MACD - Cross/);
  });

  it("buildNotesPreview truncates long notes", () => {
    const preview = buildNotesPreview("x".repeat(150));
    expect(preview).toHaveLength(103);
    expect(preview.endsWith("...")).toBe(true);
  });

  it("chartHasFlag handles missing checklist safely", () => {
    expect(chartHasFlag({ checklist: { trend_bullish: true } }, "trend_bullish")).toBe(true);
    expect(chartHasFlag({}, "trend_bullish")).toBe(false);
  });
});


afterEach(() => {
  vi.restoreAllMocks();
});

describe("fetchJson", () => {
  it("surfaces nested error envelope message", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ error: { code: "SESSION_EXPIRED", message: "Session expired." } }), { status: 400 })
    );

    await expect(fetchJson("/api/pipeline/jobs", { method: "POST" })).rejects.toThrow("Session expired.");
  });
});
