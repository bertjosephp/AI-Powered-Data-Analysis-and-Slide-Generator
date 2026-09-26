import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { UploadForm } from "@/components/upload/UploadForm";

import { API, server } from "./msw/server";
import { renderWithQuery } from "./test-utils";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const csv = () => new File(["a,b\n1,2\n"], "sales.csv", { type: "text/csv" });

describe("UploadForm", () => {
  beforeEach(() => push.mockReset());

  it("keeps submit disabled until a file is chosen", () => {
    renderWithQuery(<UploadForm />);
    expect(screen.getByRole("button", { name: /analyze and build deck/i })).toBeDisabled();
  });

  it("uploads the file with options and navigates to the job page", async () => {
    const user = userEvent.setup();
    let options: unknown;
    server.use(
      http.post(`${API}/jobs`, async ({ request }) => {
        options = JSON.parse((await request.formData()).get("options") as string);
        return HttpResponse.json({ job_id: "abc123", status: "queued" }, { status: 202 });
      }),
    );
    renderWithQuery(<UploadForm />);

    await user.upload(screen.getByLabelText("Upload dataset"), csv());
    expect(await screen.findByText("sales.csv")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Tone"), "technical");
    await user.click(screen.getByRole("button", { name: /analyze and build deck/i }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/jobs/abc123"));
    expect(options).toMatchObject({ tone: "technical", num_slides: 10 });
  });

  it("rejects unsupported file types on the client", async () => {
    const user = userEvent.setup({ applyAccept: false });
    renderWithQuery(<UploadForm />);

    await user.upload(
      screen.getByLabelText("Upload dataset"),
      new File(["{}"], "data.json", { type: "application/json" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(/only csv and excel/i);
    expect(screen.getByRole("button", { name: /analyze and build deck/i })).toBeDisabled();
  });

  it("shows the server's error message when the upload is rejected", async () => {
    const user = userEvent.setup();
    server.use(
      http.post(`${API}/jobs`, () =>
        HttpResponse.json(
          { error: { code: "INVALID_FILE", message: "Could not parse the CSV." } },
          { status: 400 },
        ),
      ),
    );
    renderWithQuery(<UploadForm />);

    await user.upload(screen.getByLabelText("Upload dataset"), csv());
    await user.click(screen.getByRole("button", { name: /analyze and build deck/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not parse the CSV.");
    expect(push).not.toHaveBeenCalled();
  });

  it("lets the user remove the chosen file", async () => {
    const user = userEvent.setup();
    renderWithQuery(<UploadForm />);
    await user.upload(screen.getByLabelText("Upload dataset"), csv());
    await user.click(await screen.findByRole("button", { name: "Remove file" }));
    expect(screen.getByLabelText("Upload dataset")).toBeInTheDocument();
  });
});
