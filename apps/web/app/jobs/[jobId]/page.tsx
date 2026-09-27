import type { Metadata } from "next";

import { JobView } from "@/components/JobView";

export const metadata: Metadata = { title: "Analysis · Data to Deck" };

export default async function JobPage({ params }: PageProps<"/jobs/[jobId]">) {
  const { jobId } = await params;
  return <JobView jobId={jobId} />;
}
