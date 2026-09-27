import { render, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { JobView } from "@/components/JobView";
import { PipelineTracker } from "@/components/progress/PipelineTracker";
import type { Stage } from "@/lib/api/types";

import { jobCompleted, jobFailed, jobRunning, rawFixtures } from "./fixtures";
import { API, server } from "./msw/server";
import { renderWithQuery } from "./test-utils";

function stageItems() {
  return within(screen.getByRole("list", { name: "Pipeline progress" })).getAllByRole("listitem");
}

describe("PipelineTracker", () => {
  it("shows each stage's status and marks the running step as current", () => {
    render(<PipelineTracker stages={jobRunning.stages} />);
    const items = stageItems();
    expect(items.map((li) => li.textContent)).toEqual([
      "Reading fileStatus: Done",
      "Profiling dataStatus: Done",
      "Finding patternsStatus: In progress · Testing patterns",
      "4Writing the storyStatus: Waiting",
      "5Building slide deckStatus: Waiting",
    ]);
    expect(items[2]).toHaveAttribute("aria-current", "step");
  });

  it("shows a failed stage", () => {
    render(<PipelineTracker stages={jobFailed.stages} />);
    expect(stageItems()[4]).toHaveTextContent("Failed");
  });

  it("shows all stages done", () => {
    render(<PipelineTracker stages={jobCompleted.stages} />);
    expect(stageItems().every((li) => li.textContent?.includes("Done"))).toBe(true);
  });

  it("shows pending stages as numbered steps", () => {
    const stages: Stage[] = jobRunning.stages.map((s) => ({ ...s, status: "pending" }));
    render(<PipelineTracker stages={stages} />);
    expect(stageItems()[0]).toHaveTextContent("1Reading file");
  });
});

describe("JobView polling", () => {
  it("polls until the job completes", async () => {
    const responses = [rawFixtures.running, rawFixtures.running, rawFixtures.completed];
    let calls = 0;
    server.use(
      http.get(`${API}/jobs/job123`, () => {
        const body = responses[Math.min(calls, responses.length - 1)];
        calls += 1;
        return HttpResponse.json(body);
      }),
    );

    renderWithQuery(<JobView jobId="job123" pollIntervalMs={20} />);
    expect(await screen.findByText("Running")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Completed")).toBeInTheDocument());
    const callsAtCompletion = calls;
    await new Promise((r) => setTimeout(r, 150));
    expect(calls).toBe(callsAtCompletion); // stopped polling
  });

  it("shows a not-found state for an unknown job", async () => {
    server.use(
      http.get(`${API}/jobs/gone`, () =>
        HttpResponse.json(
          { error: { code: "JOB_NOT_FOUND", message: "Job not found." } },
          { status: 404 },
        ),
      ),
    );
    renderWithQuery(<JobView jobId="gone" />);
    expect(await screen.findByText("Analysis not found")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Start a new analysis" })).toHaveAttribute("href", "/");
  });
});
