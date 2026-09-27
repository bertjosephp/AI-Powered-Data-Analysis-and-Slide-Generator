"use client";

import { ChevronLeft, ChevronRight, Maximize2, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { SectionHeader } from "@/components/ui/SectionHeader";
import type { Slide } from "@/lib/api/types";

import { SlideView } from "./SlideView";

type Props = { slides: Slide[]; datasetName: string };

export function DeckPreview({ slides, datasetName }: Props) {
  const [current, setCurrent] = useState<number | null>(null);
  const total = slides.length;

  return (
    <section aria-labelledby="slides-heading">
      <SectionHeader
        id="slides-heading"
        eyebrow="Deck"
        title="Slides"
        description="A preview of the downloadable deck. Click any slide to present."
        action={
          <button
            type="button"
            onClick={() => setCurrent(0)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface px-3 py-1.5 text-sm font-medium shadow-card transition hover:bg-surface-muted"
          >
            <Maximize2 className="size-4" aria-hidden /> Present
          </button>
        }
      />
      <ol className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {slides.map((slide, i) => (
          <li key={i}>
            <button
              type="button"
              onClick={() => setCurrent(i)}
              aria-label={`Open slide ${i + 1} of ${total}: ${slideTitle(slide)}`}
              className="block w-full overflow-hidden rounded-xl border border-border shadow-card transition hover:-translate-y-0.5 hover:shadow-lg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent motion-reduce:transition-none motion-reduce:hover:translate-y-0"
            >
              <div aria-hidden className="pointer-events-none">
                <SlideView slide={slide} index={i + 1} total={total} datasetName={datasetName} />
              </div>
            </button>
          </li>
        ))}
      </ol>
      {current !== null && (
        <Presenter
          slides={slides}
          datasetName={datasetName}
          index={current}
          onChange={setCurrent}
          onClose={() => setCurrent(null)}
        />
      )}
    </section>
  );
}

function Presenter({
  slides,
  datasetName,
  index,
  onChange,
  onClose,
}: {
  slides: Slide[];
  datasetName: string;
  index: number;
  onChange: (i: number) => void;
  onClose: () => void;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const total = slides.length;
  const go = useCallback(
    (delta: number) => onChange(Math.min(total - 1, Math.max(0, index + delta))),
    [index, onChange, total],
  );

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    dialogRef.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
      opener?.focus();
    };
  }, []);

  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-label={`Slide ${index + 1} of ${total}`}
      tabIndex={-1}
      onKeyDown={(e) => {
        if (e.key === "Escape") onClose();
        else if (e.key === "ArrowRight" || e.key === "PageDown" || e.key === " ") {
          e.preventDefault();
          go(1);
        } else if (e.key === "ArrowLeft" || e.key === "PageUp") {
          e.preventDefault();
          go(-1);
        }
      }}
      className="fixed inset-0 z-50 flex flex-col bg-[#0b0b0f] outline-none"
    >
      <div className="flex items-center justify-between px-4 py-3 text-sm text-white/80">
        <span aria-live="polite">
          {index + 1} / {total}
        </span>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close presentation"
          className="rounded-md p-1.5 hover:bg-white/10 hover:text-white"
        >
          <X className="size-5" />
        </button>
      </div>
      <div className="flex min-h-0 flex-1 items-center justify-center px-4 pb-4 sm:px-16">
        <div className="w-full max-w-[min(100%,calc((100dvh-8rem)*16/9))] shadow-2xl">
          <SlideView slide={slides[index]} index={index + 1} total={total} datasetName={datasetName} />
        </div>
      </div>
      <button
        type="button"
        onClick={() => go(-1)}
        disabled={index === 0}
        aria-label="Previous slide"
        className="absolute top-1/2 left-2 -translate-y-1/2 rounded-full p-2 text-white/70 hover:bg-white/10 hover:text-white disabled:opacity-20 sm:left-4"
      >
        <ChevronLeft className="size-7" />
      </button>
      <button
        type="button"
        onClick={() => go(1)}
        disabled={index === total - 1}
        aria-label="Next slide"
        className="absolute top-1/2 right-2 -translate-y-1/2 rounded-full p-2 text-white/70 hover:bg-white/10 hover:text-white disabled:opacity-20 sm:right-4"
      >
        <ChevronRight className="size-7" />
      </button>
    </div>
  );
}

function slideTitle(slide: Slide): string {
  return slide.layout === "executive_summary" ? "Executive summary" : slide.title;
}
