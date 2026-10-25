"use client";
import { useUser } from "@/components/shell";
import { PageHeader } from "@/components/ui";
export default function ApiPage() {
  const user = useUser();
  if (user?.role !== "ADMIN") return <p>Administrator access is required.</p>;
  return (
    <>
      <PageHeader
        eyebrow="ADMINISTRATION"
        title="API & integrations"
        description="Bring external research into a reviewable workspace."
      />
      <section className="panel detail-section">
        <h2>Connect n8n</h2>
        <p className="body-copy">
          Use the backend URL accessible from your n8n instance. Local default:
          http://localhost:8100. Authenticate using your N8N_API_KEY from the
          server environment.
        </p>
        <pre>
          {[
            "Authorization: Bearer <N8N_API_KEY>",
            "Content-Type: application/json",
            "",
            "POST /api/v1/research-requests",
            "POST /api/v1/research-requests/{id}/candidates",
            "POST /api/v1/research-requests/{id}/candidates/bulk",
            "POST /api/v1/research-requests/{id}/complete",
            "GET  /api/v1/research-requests/{id}/candidates",
            "PATCH /api/v1/candidates/{id}",
          ].join("\n")}
        </pre>
        <p className="body-copy">
          Importing candidates always starts with NEW status. Completing
          collection marks the request ready for review. Only a signed-in person
          can change candidate status.
        </p>
        <h3>Candidate payload</h3>
        <pre>
          {JSON.stringify(
            {
              full_name: "Example Person",
              job_title: "Researcher",
              organization: "Example University",
              field: "Computer Vision",
              location: "Istanbul",
              expertise: ["Computer Vision", "Machine Learning"],
              source_url: "https://example.com/profile",
              source_name: "Example University",
              source_type: "university",
            },
            null,
            2,
          )}
        </pre>
        <p className="muted">
          Bulk endpoint: wrap profiles in {`{"candidates": [...]}`}. See backend
          /docs for the complete interactive OpenAPI reference. Credentials are
          never displayed here.
        </p>
      </section>
    </>
  );
}
