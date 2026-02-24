import { describe, expect, it } from "vitest";

import {
  buildChecklistSummary,
  buildEmptyChecklist,
  buildNotesPreview,
  chartHasFlag,
  normalizeAnalysis,
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

  it("normalizes analysis payload defaults", () => {
    expect(normalizeAnalysis({})).toEqual({
      status: "idle",
      model: "",
      prompt_version: "",
      text: "",
      error: "",
      started_at: "",
      completed_at: "",
    });

    expect(normalizeAnalysis({ status: "completed", text: "ok" }).status).toBe("completed");
  });
});
