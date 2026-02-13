import { describe, expect, it } from "vitest";

import { filterQueueByPolicy, shouldUploadByPolicy } from "../src/lib/classifierHelpers.js";

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
      skipNone: false,
    });

    expect(filtered.map((item) => item.filename)).toEqual(["a.png", "c.png"]);
  });

  it("gates upload behavior for each predicted label", () => {
    const policy = { uploadRed: false, uploadYellow: true, skipNone: true };

    expect(shouldUploadByPolicy("red", policy)).toBe(false);
    expect(shouldUploadByPolicy("yellow", policy)).toBe(true);
    expect(shouldUploadByPolicy("none", policy)).toBe(false);
    expect(shouldUploadByPolicy("unknown", policy)).toBe(false);
  });
});
