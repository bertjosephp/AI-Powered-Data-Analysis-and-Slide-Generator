// @vitest-environment node
// The client needs no DOM; Node's native File/FormData/fetch match browser behavior.
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { ApiError, createJob, getJob, retryJob } from "@/lib/api/client";
import { DEFAULT_OPTIONS, JobStateSchema } from "@/lib/api/types";

import { rawFixtures } from "./fixtures";
import { API, server } from "./msw/server";

describe("contract", () => {
  it.each(Object.entries(rawFixtures))("backend %s job fixture matches JobStateSchema", (_, raw) => {
    expect(JobStateSchema.safeParse(raw).success).toBe(true);
  });
});

describe("api client", () => {
  it("getJob parses a job", async () => {
    server.use(http.get(`${API}/jobs/job123`, () => HttpResponse.json(rawFixtures.completed)));
    const job = await getJob("job123");
    expect(job.status).toBe("completed");
    expect(job.presentation?.slide_count).toBe(8);
    expect(job.deck?.[2].layout).toBe("kpi_cards");
  });

  it("createJob posts the file and options as multipart form data", async () => {
    let received: FormData | undefined;
    server.use(
      http.post(`${API}/jobs`, async ({ request }) => {
        received = await request.formData();
        return HttpResponse.json({ job_id: "j1", status: "queued" }, { status: 202 });
      }),
    );
    const file = new File(["a,b\n1,2\n"], "data.csv", { type: "text/csv" });
    const created = await createJob(file, { ...DEFAULT_OPTIONS, num_slides: 8 });

    expect(created).toEqual({ job_id: "j1", status: "queued" });
    expect((received?.get("file") as File).name).toBe("data.csv");
    expect(JSON.parse(received?.get("options") as string)).toMatchObject({ num_slides: 8 });
  });

  it("surfaces the backend error envelope as ApiError", async () => {
    server.use(
      http.post(`${API}/jobs/j1/retry`, () =>
        HttpResponse.json(
          { error: { code: "JOB_NOT_RETRYABLE", message: "Only failed jobs can be retried." } },
          { status: 409 },
        ),
      ),
    );
    await expect(retryJob("j1")).rejects.toMatchObject({
      status: 409,
      code: "JOB_NOT_RETRYABLE",
      message: "Only failed jobs can be retried.",
    });
  });

  it("maps a non-envelope error to a generic ApiError", async () => {
    server.use(http.get(`${API}/jobs/x`, () => new HttpResponse("boom", { status: 502 })));
    await expect(getJob("x")).rejects.toMatchObject({ status: 502, code: "HTTP_502" });
  });

  it("maps a network failure to NETWORK_ERROR", async () => {
    server.use(http.get(`${API}/jobs/x`, () => HttpResponse.error()));
    const err = await getJob("x").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe("NETWORK_ERROR");
  });

  it("rejects a response that breaks the contract", async () => {
    server.use(http.get(`${API}/jobs/x`, () => HttpResponse.json({ job_id: "x" })));
    await expect(getJob("x")).rejects.toMatchObject({ code: "BAD_RESPONSE" });
  });
});
