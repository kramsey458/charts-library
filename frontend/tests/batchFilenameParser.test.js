import { describe, expect, it } from "vitest";

import { parseBatchFilename } from "../src/lib/batchFilenameParser.js";

describe("batch filename parser", () => {
  it("parses TICKER_YYYY-MM-DD format with trailing time", () => {
    const parsed = parseBatchFilename("VG_2026-02-12_22-19-22.png");
    expect(parsed.ticker).toBe("VG");
    expect(parsed.date).toBe("2026-02-12");
    expect(parsed.confidence).toBe("high");
    expect(parsed.requiresConfirmation).toBe(false);
  });

  it("parses YYYY-MM-DD_TICKER format", () => {
    const parsed = parseBatchFilename("2026-02-12_AAPL_signal.png");
    expect(parsed.ticker).toBe("AAPL");
    expect(parsed.date).toBe("2026-02-12");
    expect(parsed.confidence).toBe("high");
  });

  it("handles compact date token", () => {
    const parsed = parseBatchFilename("MSFT_20260212_setup.png");
    expect(parsed.date).toBe("2026-02-12");
    expect(parsed.ticker).toBe("MSFT");
  });

  it("returns confirmation-needed for ambiguous filename", () => {
    const parsed = parseBatchFilename("signal_VG_entry_2026-02-12.png");
    expect(parsed.ticker).toBe("VG");
    expect(parsed.date).toBe("2026-02-12");
    expect(parsed.confidence).toBe("medium");
    expect(parsed.requiresConfirmation).toBe(true);
  });

  it("fails when ticker/date are missing", () => {
    const parsed = parseBatchFilename("chart_snapshot.png");
    expect(parsed.confidence).toBe("none");
    expect(parsed.requiresConfirmation).toBe(true);
  });
});
