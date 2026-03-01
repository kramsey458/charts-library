import { afterEach, describe, expect, it, vi } from "vitest";

import {
  buildChecklistSummary,
  buildEmptyChecklist,
  buildNotesPreview,
  chartHasFlag,
  cycleChartTimeframe,
  decodeChartTimeframe,
  encodeNotesWithTimeframe,
  getNextTimeframe,
  normalizeAnalysis,
} from "../src/lib/chartHelpers.js";

describe("chartHelpers", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

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


  it("encodes and decodes timeframe marker in notes", () => {
    const encoded = encodeNotesWithTimeframe("My note", "W");
    expect(encoded).toContain("[[TF:W]]");

    const decoded = decodeChartTimeframe({ notes: encoded, timeframe: "" });
    expect(decoded.notes).toBe("My note");
    expect(decoded.timeframe).toBe("W");
  });

  it("returns next timeframe in D -> W -> M -> D sequence", () => {
    expect(getNextTimeframe("D")).toBe("W");
    expect(getNextTimeframe("W")).toBe("M");
    expect(getNextTimeframe("M")).toBe("D");
    expect(getNextTimeframe("bad")).toBe("W");
  });

  it("falls back to PATCH notes when timeframe endpoint returns 404", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: false,
        status: 404,
        json: async () => ({ error: "Not found" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          chart: {
            ticker: "AAPL",
            date: "2026-02-12",
            filename: "chart.png",
            notes: "keep",
            timeframe: "W",
          },
        }),
      });

    vi.stubGlobal("fetch", fetchMock);

    const chart = await cycleChartTimeframe({
      ticker: "AAPL",
      date: "2026-02-12",
      filename: "chart.png",
      timeframe: "D",
      notes: "keep",
    });

    expect(chart.timeframe).toBe("W");
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0][0]).toContain("/timeframe");
    expect(fetchMock.mock.calls[1][0]).toContain("/notes");
    expect(fetchMock.mock.calls[1][1].method).toBe("PATCH");
    const fallbackBody = JSON.parse(fetchMock.mock.calls[1][1].body);
    expect(fallbackBody.timeframe).toBe("W");
    expect(fallbackBody.notes).toContain("[[TF:W]]");
  });
});
