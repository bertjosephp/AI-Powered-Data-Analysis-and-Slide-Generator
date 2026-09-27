import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { UploadForm } from "@/components/upload/UploadForm";
import { readCsvHeader } from "@/lib/csvHeader";

import { API, server } from "./msw/server";
import { renderWithQuery } from "./test-utils";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const SAMPLE = {
  name: "saas_churn",
  title: "SaaS subscriptions",
  description: "B2B SaaS accounts.",
  rows: 3000,
  columns: 20,
  suggested_question: "Which customers churn?",
  suggested_target: "churned",
  filename: "saas_churn.csv",
};

describe("readCsvHeader", () => {
  it("reads quoted, semicolon-delimited headers and skips a BOM", async () => {
    const file = new File(['﻿"order id";region;"say ""hi"""\n1;N;x\n'], "d.csv");
    expect(await readCsvHeader(file)).toEqual(["order id", "region", 'say "hi"']);
  });

  it("returns null for Excel files", async () => {
    expect(await readCsvHeader(new File(["PK"], "d.xlsx"))).toBeNull();
  });
});

describe("UploadForm steering", () => {
  beforeEach(() => {
    push.mockReset();
    server.use(http.get(`${API}/samples`, () => HttpResponse.json([SAMPLE])));
  });

  it("offers the file's columns as the outcome and sends question and target", async () => {
    const user = userEvent.setup();
    let options: Record<string, unknown> = {};
    server.use(
      http.post(`${API}/jobs`, async ({ request }) => {
        options = JSON.parse((await request.formData()).get("options") as string);
        return HttpResponse.json({ job_id: "j1", status: "queued" }, { status: 202 });
      }),
    );
    renderWithQuery(<UploadForm />);

    await user.upload(
      screen.getByLabelText("Upload dataset"),
      new File(["plan,churned,seats\nBasic,true,3\n"], "accounts.csv", { type: "text/csv" }),
    );
    const outcome = await screen.findByRole("combobox", { name: /outcome to explain/i });
    expect(Array.from((outcome as HTMLSelectElement).options).map((o) => o.value)).toEqual([
      "",
      "plan",
      "churned",
      "seats",
    ]);
    await user.selectOptions(outcome, "churned");
    await user.type(screen.getByLabelText(/what do you want to learn/i), "Who churns?");
    await user.click(screen.getByRole("button", { name: /analyze and build deck/i }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/jobs/j1"));
    expect(options).toMatchObject({ target_column: "churned", question: "Who churns?" });
  });

  it("loads an example dataset with its suggested question and outcome", async () => {
    const user = userEvent.setup();
    server.use(
      http.get(`${API}/samples/saas_churn.csv`, () =>
        new HttpResponse("customer_id,plan,churned\nA1,Basic,true\n", {
          headers: { "Content-Type": "text/csv" },
        }),
      ),
    );
    renderWithQuery(<UploadForm />);

    await user.click(await screen.findByRole("button", { name: /saas subscriptions/i }));
    expect(await screen.findByText("saas_churn.csv")).toBeInTheDocument();
    expect(screen.getByLabelText(/what do you want to learn/i)).toHaveValue("Which customers churn?");
    expect(screen.getByRole("combobox", { name: /outcome to explain/i })).toHaveValue("churned");
    expect(screen.getByRole("button", { name: /saas subscriptions/i })).toHaveAttribute("aria-pressed", "true");
  });
});
