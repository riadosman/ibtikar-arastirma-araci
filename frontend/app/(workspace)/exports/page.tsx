"use client";
import Link from "next/link";
import { useState } from "react";
import { useData } from "@/lib/api";
import type { ExportJob, Page, Research } from "@/lib/types";
import {
  Badge,
  Empty,
  ErrorBox,
  Loading,
  PageHeader,
  Pagination,
} from "@/components/ui";
import { ExportControls } from "@/components/export-controls";
export default function ExportsPage() {
  const [page, setPage] = useState(1),
    [id, setId] = useState("");
  const jobs = useData<Page<ExportJob>>(`/exports?page=${page}`);
  const requests = useData<Page<Research>>("/research-requests?page_size=100");
  return (
    <>
      <PageHeader
        eyebrow="TAKE YOUR RESEARCH FURTHER"
        title="Exports"
        description="A useful shortlist, ready for the next conversation."
      />
      <section className="panel detail-section">
        <h2>Create an export</h2>
        <p className="muted">
          Only approved candidates are included by default. Source links travel
          with every profile.
        </p>
        <label className="export-request">
          Research request
          <select value={id} onChange={(e) => setId(e.target.value)}>
            <option value="">Choose a request…</option>
            {requests.data?.items.map((r) => (
              <option key={r.id} value={r.id}>
                {r.title}
              </option>
            ))}
          </select>
        </label>
        <ErrorBox message={requests.error} />
        {id && <ExportControls researchId={id} onExport={jobs.reload} />}
      </section>
      <section className="panel">
        <div className="panel-heading">
          <h2>Export history</h2>
          <span className="muted">Files are generated on demand</span>
        </div>
        <ErrorBox message={jobs.error} />
        {jobs.loading ? (
          <Loading />
        ) : !jobs.data?.items.length ? (
          <Empty
            title="No exports yet"
            detail="Choose a request above to download your first shortlist."
          />
        ) : (
          <>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Research</th>
                    <th>Format</th>
                    <th>Candidates</th>
                    <th>Selection</th>
                    <th>Status</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.data.items.map((j) => (
                    <tr key={j.id}>
                      <td>
                        <Link
                          className="text-link"
                          href={`/research/${j.research_request_id}`}
                        >
                          {requests.data?.items.find(
                            (r) => r.id === j.research_request_id,
                          )?.title || j.research_request_id.slice(0, 8)}
                        </Link>
                      </td>
                      <td>{j.format.toUpperCase()}</td>
                      <td>{j.candidate_count}</td>
                      <td>
                        {j.include_all ? "All statuses" : "Approved only"}
                      </td>
                      <td>
                        <Badge value={j.status} />
                      </td>
                      <td>{new Date(j.created_at).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination page={page} total={jobs.data.total} change={setPage} />
          </>
        )}
      </section>
    </>
  );
}
