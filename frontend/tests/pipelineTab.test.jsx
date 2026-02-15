/** @vitest-environment jsdom */
import React from "react";
import { act } from "react-dom/test-utils";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PipelineTab from "../src/components/PipelineTab";

let container;
let root;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.restoreAllMocks();
});

describe("PipelineTab", () => {
  it("shows parsed preview counts after create job", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ id: "1", state: "draft", tickers: ["AAPL"], invalid_rows: [{ line: 2 }], progress: {}, items: [] }), { status: 200 })
    );

    await act(async () => {
      root.render(<PipelineTab />);
    });

    const textarea = container.querySelector("textarea");
    textarea.value = "AAPL\nBAD$";
    textarea.dispatchEvent(new Event("input", { bubbles: true }));

    await act(async () => {
      container.querySelector("button").click();
    });

    expect(container.textContent).toContain("Valid tickers: 1");
    expect(container.textContent).toContain("Invalid rows: 1");
  });

  it("supports awaiting_login resume flow", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: "1", state: "draft", tickers: ["AAPL"], invalid_rows: [], progress: {}, items: [] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: "1", state: "awaiting_login", launch_url: "/login", tickers: ["AAPL"], invalid_rows: [], progress: {}, items: [] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: "1", state: "running_capture", tickers: ["AAPL"], invalid_rows: [], progress: { captured: 0, total: 1, classified: 0, uploaded: 0 }, items: [] }), { status: 200 }));

    await act(async () => {
      root.render(<PipelineTab />);
    });
    const textarea = container.querySelector("textarea");
    textarea.value = "AAPL";
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
    await act(async () => container.querySelector("button").click());
    await act(async () => Array.from(container.querySelectorAll("button")).find((b) => b.textContent.includes("Start Pipeline")).click());
    await act(async () => Array.from(container.querySelectorAll("button")).find((b) => b.textContent.includes("Resume")).click());

    expect(container.textContent).toContain("State: running_capture");
  });

  it("builds upload decision payload with overrides", async () => {
    const fetchMock = vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: "1", state: "awaiting_upload_decision", tickers: ["AAPL"], invalid_rows: [], progress: {}, items: [{ ticker: "AAPL", label: "red" }] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: "1", state: "running_upload", tickers: ["AAPL"], invalid_rows: [], progress: {}, items: [{ ticker: "AAPL", label: "red" }] }), { status: 200 }));

    await act(async () => root.render(<PipelineTab />));
    const textarea = container.querySelector("textarea");
    textarea.value = "AAPL";
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
    await act(async () => container.querySelector("button").click());

    const select = container.querySelector("select");
    select.value = "skip";
    select.dispatchEvent(new Event("change", { bubbles: true }));
    await act(async () => Array.from(container.querySelectorAll("button")).find((b) => b.textContent.includes("Upload approved charts")).click());

    const lastCall = fetchMock.mock.calls.at(-1);
    expect(lastCall[0]).toContain("upload-decision");
    expect(JSON.parse(lastCall[1].body)).toEqual({
      policy: { upload_red: true, upload_yellow: true, skip_none: true },
      overrides: { AAPL: "skip" },
    });
  });
});
