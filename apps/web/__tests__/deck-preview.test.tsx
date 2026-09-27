import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { DeckPreview } from "@/components/presentation/DeckPreview";
import { formatChartValue, SlideView } from "@/components/presentation/SlideView";
import type { Slide } from "@/lib/api/types";

import { jobCompleted } from "./fixtures";

const deck = jobCompleted.deck as Slide[];

function slideOf<L extends Slide["layout"]>(layout: L) {
  return deck.find((s) => s.layout === layout) as Extract<Slide, { layout: L }>;
}

describe("SlideView", () => {
  it("renders the title slide with resolved meta and no footer", () => {
    render(<SlideView slide={slideOf("title")} index={1} total={8} datasetName="sample.csv" />);
    expect(screen.getByText("What drives returned")).toBeInTheDocument();
    expect(screen.getByText(/5,000 rows × 22 columns/)).toBeInTheDocument();
    expect(screen.queryByText("1 / 8")).not.toBeInTheDocument();
  });

  it("renders KPI values exactly as resolved by the backend", () => {
    render(<SlideView slide={slideOf("kpi_cards")} index={3} total={8} datasetName="sample.csv" />);
    for (const text of ["17.6% vs 6.3%", "16.5×", "+646%", "channel: Social vs Paid Search", "3 / 8"]) {
      expect(screen.getByText(text)).toBeInTheDocument();
    }
  });

  it("draws chart bars with value labels", () => {
    const chartSlide = deck.find(
      (s) => s.layout === "chart_insight" && s.chart?.style === "bars",
    ) as Extract<Slide, { layout: "chart_insight" }>;
    render(<SlideView slide={chartSlide} index={4} total={8} datasetName="sample.csv" />);
    expect(screen.getByText("Social")).toBeInTheDocument();
    expect(screen.getByText("17.6%")).toBeInTheDocument();
    expect(screen.getByText("Overall: 9.4%")).toBeInTheDocument();
    expect(screen.getByText(chartSlide.bullets[0])).toBeInTheDocument();
  });

  it("draws ordered bands as columns", () => {
    const chartSlide = deck.find(
      (s) => s.layout === "chart_insight" && s.chart?.style === "columns",
    ) as Extract<Slide, { layout: "chart_insight" }>;
    render(<SlideView slide={chartSlide} index={5} total={8} datasetName="sample.csv" />);
    for (const c of chartSlide.chart!.categories) expect(screen.getAllByText(c).length).toBeGreaterThan(0);
    expect(screen.getByText("WHAT IT MEANS")).toBeInTheDocument();
  });

  it("renders a chart slide without a chart as text cards", () => {
    const slide: Slide = {
      layout: "chart_insight",
      title: "Text only",
      bullets: ["First point", "Second point"],
      chart: null,
    };
    render(<SlideView slide={slide} index={2} total={2} datasetName="x.csv" />);
    expect(screen.getByText("First point")).toBeInTheDocument();
  });

  it("formats chart values like the pptx renderer", () => {
    expect(formatChartValue(0.7825, "correlation")).toBe("0.78");
    expect(formatChartValue(7.5, "percent")).toBe("7.5%");
    expect(formatChartValue(5, "percent")).toBe("5%");
    expect(formatChartValue(685.06275, "number")).toBe("685");
    expect(formatChartValue(26.625, "number")).toBe("26.63");
    expect(formatChartValue(12500, "number")).toBe("12.5K");
  });
});

describe("DeckPreview", () => {
  it("shows a thumbnail per slide", () => {
    render(<DeckPreview slides={deck} datasetName="sample.csv" />);
    const buttons = screen.getAllByRole("button", { name: /^Open slide/ });
    expect(buttons).toHaveLength(8);
    expect(buttons[0]).toHaveAccessibleName(
      "Open slide 1 of 8: What drives returned",
    );
  });

  it("opens presenter mode, navigates with the keyboard, and closes with Escape", async () => {
    const user = userEvent.setup();
    render(<DeckPreview slides={deck} datasetName="sample.csv" />);

    const thumb = screen.getByRole("button", { name: /^Open slide 3 of 8/ });
    await user.click(thumb);
    const dialog = screen.getByRole("dialog", { name: "Slide 3 of 8" });
    expect(dialog).toHaveFocus();
    expect(within(dialog).getByText("The numbers that matter")).toBeInTheDocument();

    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("dialog", { name: "Slide 4 of 8" })).toBeInTheDocument();
    await user.keyboard("{ArrowLeft}{ArrowLeft}");
    expect(screen.getByRole("dialog", { name: "Slide 2 of 8" })).toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(thumb).toHaveFocus();
  });

  it("stops at the ends of the deck", async () => {
    const user = userEvent.setup();
    render(<DeckPreview slides={deck} datasetName="sample.csv" />);
    await user.click(screen.getByRole("button", { name: "Present" }));
    expect(screen.getByRole("button", { name: "Previous slide" })).toBeDisabled();
    await user.keyboard("{ArrowLeft}");
    expect(screen.getByRole("dialog", { name: "Slide 1 of 8" })).toBeInTheDocument();
  });
});
