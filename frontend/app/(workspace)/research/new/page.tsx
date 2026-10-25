import { PageHeader, BackLink } from "@/components/ui";
import { ResearchForm } from "@/components/research-form";
export default function NewResearchPage() {
  return (
    <>
      <BackLink href="/research">All requests</BackLink>
      <PageHeader
        eyebrow="START WITH A QUESTION"
        title="New research"
        description="The right connections start with a clear brief."
      />
      <div className="form-layout">
        <ResearchForm />
        <aside className="context-note">
          <h3>Make your brief count</h3>
          <p>
            Be specific about the expertise, location, and experience you need.
          </p>
          <hr />
          <h3>You make the final call</h3>
          <p>
            Relevance scores help you prioritize. Source links help you verify.
            Your team decides who belongs on the shortlist.
          </p>
        </aside>
      </div>
    </>
  );
}
