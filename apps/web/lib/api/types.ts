// Runtime schemas for the FastAPI contract (apps/api/app/schemas). Responses are
// parsed with these, so a backend change that breaks the contract fails loudly.
import { z } from "zod";

export const TopValueSchema = z.object({ value: z.string(), count: z.number() });

const num = z.number().nullish();

export const ColumnProfileSchema = z.object({
  name: z.string(),
  inferred_type: z.enum(["numeric", "categorical", "datetime", "boolean", "text", "id"]),
  dtype: z.string(),
  missing_count: z.number(),
  missing_pct: z.number(),
  unique_count: z.number(),
  mean: num,
  std: num,
  min: num,
  p25: num,
  median: num,
  p75: num,
  max: num,
  skew: num,
  outlier_count: num,
  infinite_count: num,
  top_values: z.array(TopValueSchema).nullish(),
  min_date: z.string().nullish(),
  max_date: z.string().nullish(),
});

export const DatasetProfileSchema = z.object({
  n_rows: z.number(),
  n_cols: z.number(),
  memory_bytes: z.number(),
  duplicate_rows: z.number(),
  missing_cells_total: z.number(),
  missing_pct_total: z.number(),
  sampled: z.boolean(),
  sample_rows: z.number().nullish(),
  columns: z.array(ColumnProfileSchema),
  correlation: z
    .object({
      method: z.literal("pearson"),
      columns: z.array(z.string()),
      matrix: z.array(z.array(z.number().nullable())),
    })
    .nullish(),
  top_correlations: z.array(z.object({ a: z.string(), b: z.string(), r: z.number() })),
  warnings: z.array(z.string()),
});

export const InsightsSchema = z.object({
  executive_summary: z.string(),
  key_findings: z.array(
    z.object({ title: z.string(), detail: z.string(), supporting_stats: z.array(z.string()) }),
  ),
  hypotheses: z.array(
    z.object({
      statement: z.string(),
      rationale: z.string(),
      suggested_test: z.string(),
      confidence: z.enum(["low", "medium", "high"]),
    }),
  ),
  analytical_questions: z.array(z.object({ question: z.string(), why_it_matters: z.string() })),
  data_quality_notes: z.array(z.string()),
  recommended_next_steps: z.array(z.string()),
  slide_outline: z.array(z.object({ title: z.string(), bullets: z.array(z.string()) })),
});

export const PresentationSchema = z.object({
  gamma_generation_id: z.string(),
  status: z.enum(["pending", "completed", "failed"]),
  gamma_url: z.string().nullish(),
  export_url: z.string().nullish(),
  credits_deducted: z.number().nullish(),
  error: z.string().nullish(),
  mock: z.boolean().default(false),
});

export const StageKeySchema = z.enum(["ingest", "profile", "analyze", "generate_deck"]);

export const StageSchema = z.object({
  key: StageKeySchema,
  label: z.string(),
  status: z.enum(["pending", "running", "done", "failed"]),
  started_at: z.string().nullish(),
  finished_at: z.string().nullish(),
  message: z.string().nullish(),
});

export const AnalysisOptionsSchema = z.object({
  num_slides: z.number().int().min(4).max(25),
  tone: z.enum(["executive", "technical", "casual"]),
  audience: z.string().max(200),
  theme_id: z.string().max(100).nullish(),
  export_as: z.enum(["pdf", "pptx"]).nullish(),
});

export const JobStateSchema = z.object({
  job_id: z.string(),
  filename: z.string(),
  options: AnalysisOptionsSchema,
  status: z.enum(["queued", "running", "completed", "failed"]),
  created_at: z.string(),
  updated_at: z.string(),
  stages: z.array(StageSchema),
  profile: DatasetProfileSchema.nullish(),
  insights: InsightsSchema.nullish(),
  presentation: PresentationSchema.nullish(),
  error: z.object({ stage: StageKeySchema.nullable(), code: z.string(), message: z.string() }).nullish(),
});

export const JobCreatedSchema = z.object({
  job_id: z.string(),
  status: JobStateSchema.shape.status,
});

export const ErrorEnvelopeSchema = z.object({
  error: z.object({ code: z.string(), message: z.string(), details: z.unknown().optional() }),
});

export type ColumnProfile = z.infer<typeof ColumnProfileSchema>;
export type DatasetProfile = z.infer<typeof DatasetProfileSchema>;
export type Insights = z.infer<typeof InsightsSchema>;
export type Presentation = z.infer<typeof PresentationSchema>;
export type Stage = z.infer<typeof StageSchema>;
export type StageKey = z.infer<typeof StageKeySchema>;
export type AnalysisOptions = z.infer<typeof AnalysisOptionsSchema>;
export type JobState = z.infer<typeof JobStateSchema>;
export type JobCreated = z.infer<typeof JobCreatedSchema>;

export const DEFAULT_OPTIONS: AnalysisOptions = {
  num_slides: 10,
  tone: "executive",
  audience: "business stakeholders",
  export_as: "pdf",
};
