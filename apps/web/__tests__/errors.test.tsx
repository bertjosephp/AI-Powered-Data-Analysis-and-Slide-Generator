import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { JobView } from "@/components/JobView";
import { ErrorPanel } from "@/components/progress/ErrorPanel";
import type { JobState } from "@/lib/api/types";

import { jobFailed, rawFixtures } from "./fixtures";
import { API, server } from "./msw/server";
import { renderWithQuery } from "./test-utils";

describe("ErrorPanel", () => {
  it("names the failed stage, shows the message and a hint", () => {
    renderWithQuery(<ErrorPanel job={jobFailed} />);
    expect(screen.getByRole("heading", { name: "Building slide deck failed" })).toBeInTheDocument();
    expect(screen.getByText("The slide deck could not be rendered.")).toBeInTheDocument();
    expect(screen.getByText(/renders the deck again without re-running/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry from building slide deck/i })).toBeEnabled();
  });

  it("offers only a re-upload when the dataset is gone", () => {
    const job: JobState = {
      ...jobFailed,
      profile: null,
      insights: null,
      error: { stage: "profile", code: "INTERNAL_ERROR", message: "Boom." },
    };
    renderWithQuery(<ErrorPanel job={job} />);
    expect(screen.queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Upload again" })).toHaveAttribute("href", "/");
  });

  it("renders nothing for a healthy job", () => {
    const { container } = renderWithQuery(<ErrorPanel job={{ ...jobFailed, error: null }} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("retry flow", () => {
  it("retries a failed job and polls it to completion", async () => {
    const user = userEvent.setup();
    let retried = false;
    server.use(
      http.get(`${API}/jobs/job123`, () =>
        HttpResponse.json(retried ? rawFixtures.completed : rawFixtures.failed),
      ),
      http.post(`${API}/jobs/job123/retry`, () => {
        retried = true;
        return HttpResponse.json({ job_id: "job123", status: "queued" }, { status: 202 });
      }),
    );

    renderWithQuery(<JobView jobId="job123" pollIntervalMs={20} />);
    await user.click(await screen.findByRole("button", { name: /retry from building slide deck/i }));

    await waitFor(() => expect(screen.getByText("Your deck is ready")).toBeInTheDocument());
    expect(screen.queryByRole("heading", { name: /failed/ })).not.toBeInTheDocument();
  });

  it("shows why a retry was refused", async () => {
    const user = userEvent.setup();
    server.use(
      http.post(`${API}/jobs/job123/retry`, () =>
        HttpResponse.json(
          { error: { code: "JOB_NOT_RETRYABLE", message: "Only failed jobs can be retried." } },
          { status: 409 },
        ),
      ),
    );
    renderWithQuery(<ErrorPanel job={jobFailed} />);
    await user.click(screen.getByRole("button", { name: /retry/i }));
    expect(await screen.findByText("Only failed jobs can be retried.")).toBeInTheDocument();
  });
});

describe("connection loss", () => {
  it("keeps showing the last known progress with a warning", async () => {
    let calls = 0;
    server.use(
      http.get(`${API}/jobs/job123`, () => {
        calls += 1;
        return calls === 1 ? HttpResponse.json(rawFixtures.running) : HttpResponse.error();
      }),
    );
    renderWithQuery(<JobView jobId="job123" pollIntervalMs={20} />);
    expect(await screen.findByText(/lost contact with the server/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Dataset profile" })).toBeInTheDocument();
  });
});
