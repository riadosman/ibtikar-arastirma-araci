"use client";
import { useData } from "@/lib/api";
import type { Settings } from "@/lib/types";
import { useUser } from "@/components/shell";
import { ErrorBox, Loading, PageHeader } from "@/components/ui";
export default function SettingsPage() {
  const { data, error } = useData<Settings>("/settings");
  const user = useUser();
  return (
    <>
      <PageHeader
        eyebrow="WORKSPACE"
        title="Settings"
        description="Your account and the services behind your research."
      />
      <ErrorBox message={error} />
      {!data ? (
        <Loading />
      ) : (
        <div className="settings-grid">
          <section className="panel detail-section">
            <h2>Your account</h2>
            <dl>
              <dt>Name</dt>
              <dd>{user?.name}</dd>
              <dt>Email</dt>
              <dd>{user?.email}</dd>
              <dt>Role</dt>
              <dd>{user?.role}</dd>
              <dt>Workspace access</dt>
              <dd>Shared internal workspace</dd>
            </dl>
          </section>
          <section className="panel detail-section">
            <h2>Connected capabilities</h2>
            <dl>
              <dt>Search</dt>
              <dd>Demo provider · fictional profiles</dd>
              <dt>AI assistance</dt>
              <dd>
                {data.ai_provider === "mock"
                  ? "Demo / deterministic assistance"
                  : "OpenAI"}
              </dd>
              <dt>Google Sheets</dt>
              <dd>Preview only · no external sheet created</dd>
              <dt>n8n API</dt>
              <dd>
                {data.api_key_configured
                  ? "API key configured"
                  : "API key not configured"}
              </dd>
              <dt>Demo search</dt>
              <dd>{data.demo_mode ? "Enabled" : "Disabled"}</dd>
            </dl>
          </section>
          <section className="panel detail-section">
            <h2>How your data is handled</h2>
            <p className="body-copy">
              All team members can view and review workspace research.
              Administrators manage access. Candidates must retain source links,
              and automation cannot approve or contact them.
            </p>
            <p className="body-copy">
              The Contacted status is a manual record. This application does not
              send outreach messages.
            </p>
          </section>
        </div>
      )}
    </>
  );
}
