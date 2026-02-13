import { describe, expect, it } from "vitest";

import {
  buildChecklistFieldsForLabel,
  filterQueueByPolicy,
  policyToApiPayload,
  shouldUploadByPolicy,
} from "../src/lib/classifierHelpers.js";

describe("classifier policy helpers", () => {
  it("filters queue items by label policy", () => {
    const queue = [
      { filename: "a.png", label: "red" },
      { filename: "b.png", label: "yellow" },
      { filename: "c.png", label: "none" },
      { filename: "d.png", label: "yellow", error: "bad png" },
    ];

    const filtered = filterQueueByPolicy(queue, {
      uploadRed: true,
      uploadYellow: false,
      uploadNone: true,
    });

    expect(filtered.map((item) => item.filename)).toEqual(["a.png", "c.png"]);
  });

  it("gates upload behavior for each predicted label", () => {
    const policy = { uploadRed: false, uploadYellow: true, uploadNone: false };

    expect(shouldUploadByPolicy("red", policy)).toBe(false);
    expect(shouldUploadByPolicy("yellow", policy)).toBe(true);
    expect(shouldUploadByPolicy("none", policy)).toBe(false);
    expect(shouldUploadByPolicy("unknown", policy)).toBe(false);
  });

  it("builds API policy payload", () => {
    const payload = policyToApiPayload({ uploadRed: true, uploadYellow: false, uploadNone: true });
    expect(payload).toEqual({ policy_red: "upload", policy_yellow: "skip", policy_none: "upload" });
  });

  it("maps classifier result to checklist candle fields", () => {
    expect(buildChecklistFieldsForLabel("red")).toEqual({ red_candle: true, yellow_candle: false });
    expect(buildChecklistFieldsForLabel("yellow")).toEqual({ red_candle: false, yellow_candle: true });
    expect(buildChecklistFieldsForLabel("none")).toEqual({ red_candle: false, yellow_candle: false });
  });
});
