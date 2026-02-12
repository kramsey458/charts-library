import { describe, expect, it } from "vitest";

import {
  buildChecklistSummary,
  buildEmptyChecklist,
  buildNotesPreview,
  chartHasFlag,
} from "../src/lib/chartHelpers.js";

describe("chartHelpers", () => {
  it("buildEmptyChecklist initializes all values to false", () => {
    const checklist = buildEmptyChecklist();
    expect(Object.values(checklist).every((value) => value === false)).toBe(true);
  });

  it("buildChecklistSummary returns selected labels", () => {
    const summary = buildChecklistSummary({ red_candle: true, yellow_candle: true });
    expect(summary).toMatch(/Red Candle/);
    expect(summary).toMatch(/Yellow Candle/);
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
