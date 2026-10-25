import { PageHeader } from "@/components/ui";
import { CandidateTable } from "@/components/candidate-table";
export default function CandidatesPage() {
  return (
    <>
      <PageHeader
        eyebrow="PEOPLE & EXPERTISE"
        title="Candidates"
        description="Explore the evidence. Find the fit. Build your shortlist."
      />
      <CandidateTable />
    </>
  );
}
