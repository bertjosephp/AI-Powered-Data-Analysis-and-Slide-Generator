import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { JobView } from "@/components/JobView";
import { ColumnTable, summarize } from "@/components/dataset/ColumnTable";
import { cellColor, CorrelationHeatmap } from "@/components/dataset/CorrelationHeatmap";
import { MissingValues } from "@/components/dataset/MissingValues";
import { SummaryCards } from "@/components/dataset/SummaryCards";
import { DeckCard } from "@/components/presentation/DeckCard";
import type { ColumnProfile, JobState } from "@/lib/api/types";

import { jobCompleted, jobRunning, rawFixtures } from "./fixtures";
import { API, server } from "./msw/server";
import { renderWithQuery } from "./test-utils";

const profile = jobCompleted.profile!;
const col = (name: string) => profile.columns.find((c) => c.name === name) as ColumnProfile;

describe("SummaryCards", () => {
  it("shows the headline dataset numbers", () => {
    render(<SummaryCards profile={profile} />);
    const tile = (label: string) => screen.getByText(label).parentElement!;
    expect(tile("Rows")).toHaveTextContent("40");
    expect(tile("Columns")).toHaveTextContent("9");
    expect(tile("Columns")).toHaveTextContent("4 numeric · 2 categorical · 1 datetime");
    expect(tile("Missing cells")).toHaveTextContent("1.39%");
    expect(tile("Duplicate rows")).toHaveTextContent("None found");
  });

  it("lists data quality warnings when present", () => {
    render(<SummaryCards profile={{ ...profile, warnings: ["'x' is 80.0% missing."] }} />);
    expect(screen.getByText("Data quality warnings")).toBeInTheDocument();
    expect(screen.getByText("'x' is 80.0% missing.")).toBeInTheDocument();
  });
});

describe("MissingValues", () => {
  it("shows only columns with gaps, largest first, with direct labels", () => {
    render(<MissingValues columns={profile.columns} />);
    const rows = within(screen.getByRole("list", { name: "Percent missing by column" })).getAllByRole(
      "listitem",
    );
    expect(rows.map((r) => r.textContent)).toEqual(["discount7.5% (3)", "region5% (2)"]);
  });

  it("says so when nothing is missing", () => {
    render(<MissingValues columns={[{ ...col("units") }]} />);
    expect(screen.getByText("No missing values in any column.")).toBeInTheDocument();
  });
});

describe("CorrelationHeatmap", () => {
  it("renders the lower triangle and labels only strong cells", () => {
    render(<CorrelationHeatmap correlation={profile.correlation} />);
    const n = profile.correlation!.columns.length;
    const cells = screen.getAllByRole("cell", { name: /r = / });
    expect(cells).toHaveLength((n * (n - 1)) / 2);
    const strong = screen.getByRole("cell", { name: "revenue and unit_price: r = 0.78" });
    expect(strong).toHaveTextContent("0.78");
    const weak = cells.find((c) => c.getAttribute("aria-label")?.startsWith("discount and units"));
    expect(weak).toHaveTextContent("");
  });

  it("shows the hovered pair's value and offers a table view", async () => {
    const user = userEvent.setup();
    render(<CorrelationHeatmap correlation={profile.correlation} />);
    await user.hover(screen.getByRole("cell", { name: /^revenue and units/ }));
    expect(screen.getByText(/r =/).parentElement).toHaveTextContent("revenue × units: r = 0.59");

    await user.click(screen.getByRole("button", { name: "Show as table" }));
    const firstRow = screen.getAllByRole("row")[1];
    expect(firstRow).toHaveTextContent("revenueunit_price0.78");
  });

  it("handles too few numeric columns", () => {
    render(<CorrelationHeatmap correlation={null} />);
    expect(screen.getByText(/at least two numeric columns/i)).toBeInTheDocument();
  });

  it("maps r onto the diverging scale", () => {
    expect(cellColor(null)).toBe("var(--surface-muted)");
    expect(cellColor(0.78)).toBe("color-mix(in oklab, var(--viz-mid), var(--viz-pos) 78%)");
    expect(cellColor(-0.5)).toBe("color-mix(in oklab, var(--viz-mid), var(--viz-neg) 50%)");
  });
});

describe("ColumnTable", () => {
  it("renders one row per column with a type-specific summary", () => {
    render(<ColumnTable columns={profile.columns} />);
    expect(screen.getAllByRole("row")).toHaveLength(profile.columns.length + 1);
    expect(summarize(col("order_date"))).toBe("2025-01-01 to 2025-10-01");
    expect(summarize(col("region"))).toBe("South (13), North (10), East (9)");
    expect(summarize(col("units"))).toMatch(/^mean 26\.63 · median 26\.5 · /);
    expect(summarize(col("order_id"))).toBe("Identifier, excluded from analysis");
  });
});

describe("DeckCard", () => {
  it("links to the .pptx download on the API", () => {
    render(<DeckCard job={jobCompleted} />);
    expect(screen.getByRole("link", { name: /download \.pptx/i })).toHaveAttribute(
      "href",
      "http://api.test/api/v1/jobs/job123/deck.pptx",
    );
    expect(screen.getByText(/8 slides · editable PowerPoint · 47 KB/)).toBeInTheDocument();
  });

  it("shows progress while the deck is building", () => {
    const job: JobState = {
      ...jobRunning,
      stages: jobRunning.stages
        .map((s) => ({ ...s, status: "done" as const }))
        .map((s) => (s.key === "generate_deck" ? { ...s, status: "running" as const } : s)),
    };
    render(<DeckCard job={job} />);
    expect(screen.getByText(/building your slide deck/i)).toBeInTheDocument();
  });

  it("renders nothing before the deck stage", () => {
    const { container } = render(<DeckCard job={jobRunning} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("JobView results", () => {
  it("shows the dataset and an insights placeholder while analyzing", async () => {
    server.use(http.get(`${API}/jobs/job123`, () => HttpResponse.json(rawFixtures.running)));
    renderWithQuery(<JobView jobId="job123" pollIntervalMs={60_000} />);
    expect(await screen.findByRole("heading", { name: "Dataset profile" })).toBeInTheDocument();
    expect(screen.getByLabelText("Generating insights")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Insights" })).not.toBeInTheDocument();
  });

  it("shows insights, hypotheses and the deck when completed", async () => {
    server.use(http.get(`${API}/jobs/job123`, () => HttpResponse.json(rawFixtures.completed)));
    renderWithQuery(<JobView jobId="job123" />);
    expect(await screen.findByRole("heading", { name: "Insights" })).toBeInTheDocument();
    expect(screen.getByText(/revenue is driven far more by which product/i)).toBeInTheDocument();
    expect(screen.getByText("Price mix drives revenue more than volume")).toBeInTheDocument();
    const insights = screen.getByRole("region", { name: "Insights" });
    expect(within(insights).getAllByText(/confidence$/)).toHaveLength(3);
    expect(screen.getByText("Your deck is ready")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Slides" })).toBeInTheDocument();
  });
});
