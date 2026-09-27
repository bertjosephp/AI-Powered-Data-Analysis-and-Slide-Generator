import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { delay, http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { JobView } from "@/components/JobView";
import { ServerWakeBanner } from "@/components/ServerWakeBanner";
import { UploadForm } from "@/components/upload/UploadForm";
import { ServerStatusProvider } from "@/lib/hooks/useServerStatus";

import completed from "./fixtures/job-completed.json";
import { API, server } from "./msw/server";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

const healthy = (demo: unknown = null) =>
  http.get(`${API}/health`, () => HttpResponse.json({ status: "ok", mock_external: false, demo }));

function renderApp(ui: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ServerStatusProvider wakeThresholdMs={30} retryIntervalMs={30}>
        <ServerWakeBanner />
        {ui}
      </ServerStatusProvider>
    </QueryClientProvider>,
  );
}

describe("server wake-up", () => {
  it("shows no banner when the server answers quickly", async () => {
    server.use(
      healthy(),
      http.get(`${API}/samples`, () => HttpResponse.json([])),
    );
    renderApp(<UploadForm />);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /analyze and build deck/i })).toBeInTheDocument(),
    );
    expect(screen.queryByText(/waking up the analysis server/i)).not.toBeInTheDocument();
  });

  it("explains the cold start, locks submit, then clears once the server is up", async () => {
    let attempts = 0;
    server.use(
      http.get(`${API}/health`, async () => {
        attempts += 1;
        if (attempts < 3) return HttpResponse.error(); // still asleep
        return HttpResponse.json({
          status: "ok",
          mock_external: false,
          demo: null,
        });
      }),
      http.get(`${API}/samples`, () => HttpResponse.json([])),
    );
    renderApp(<UploadForm />);

    expect(await screen.findByText(/waking up the analysis server/i)).toBeInTheDocument();
    expect(screen.getByText(/can take up to a minute/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /waiting for server/i })).toBeDisabled();
    expect(screen.getByTestId("sample-skeletons")).toBeInTheDocument();

    await waitFor(() =>
      expect(screen.queryByText(/waking up the analysis server/i)).not.toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: /analyze and build deck/i })).toBeInTheDocument();
    expect(attempts).toBe(3);
  });

  it("treats a slow first answer as waking", async () => {
    server.use(
      http.get(`${API}/health`, async () => {
        await delay(150);
        return HttpResponse.json({
          status: "ok",
          mock_external: false,
          demo: null,
        });
      }),
      http.get(`${API}/samples`, () => HttpResponse.json([])),
    );
    renderApp(<UploadForm />);

    expect(await screen.findByText(/waking up the analysis server/i)).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.queryByText(/waking up the analysis server/i)).not.toBeInTheDocument(),
    );
  });

  it("shows how many Claude analyses the visitor has left", async () => {
    server.use(
      healthy({
        runs_per_hour: 3,
        runs_left_this_hour: 2,
        budget_remaining_usd: 2.5,
        claude_available: true,
      }),
      http.get(`${API}/samples`, () => HttpResponse.json([])),
    );
    renderApp(<UploadForm />);

    expect(await screen.findByTestId("demo-hint")).toHaveTextContent(
      "Live demo · 2 Claude analyses left this hour",
    );
  });

  it("says when the demo limit means the offline analyst will be used", async () => {
    server.use(
      healthy({
        runs_per_hour: 3,
        runs_left_this_hour: 0,
        budget_remaining_usd: 2.5,
        claude_available: false,
      }),
      http.get(`${API}/samples`, () => HttpResponse.json([])),
    );
    renderApp(<UploadForm />);

    expect(await screen.findByTestId("demo-hint")).toHaveTextContent(/offline analyst/i);
  });

  it("shows the note when a run fell back to the offline analyst", async () => {
    const note = "You've reached the demo limit of 3 Claude analyses per hour.";
    server.use(
      healthy(),
      http.get(`${API}/jobs/j1`, () =>
        HttpResponse.json({
          ...completed,
          analyst: "mock",
          analyst_note: note,
        }),
      ),
    );
    renderApp(<JobView jobId="j1" pollIntervalMs={10_000} />);

    expect(await screen.findByTestId("analyst-note")).toHaveTextContent(note);
    expect(screen.getByText("Offline (rule-based)")).toBeInTheDocument();
  });
});
