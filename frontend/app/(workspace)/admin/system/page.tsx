"use client";
import { useData } from "@/lib/api";
import { Empty, ErrorBox, Loading, PageHeader } from "@/components/ui";
type Audit = {
  id: string;
  created_at: string;
  user_id: string | null;
  action: string;
  entity_id: string;
  detail: Record<string, unknown>;
};
export default function SystemPage() {
  const { data, error } = useData<Audit[]>("/admin/audit");
  return (
    <>
      <PageHeader
        eyebrow="ADMINISTRATION"
        title="System activity"
        description="A record of the decisions and changes in your workspace."
      />
      <section className="panel">
        <div className="panel-heading">
          <h2>Recent audit events</h2>
          <span className="muted">Latest 100 events</span>
        </div>
        <ErrorBox message={error} />
        {!data && !error ? (
          <Loading />
        ) : data?.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Action</th>
                  <th>Actor</th>
                  <th>Record</th>
                  <th>Details</th>
                </tr>
              </thead>
              <tbody>
                {data.map((a) => (
                  <tr key={a.id}>
                    <td>{new Date(a.created_at).toLocaleString()}</td>
                    <td>{a.action}</td>
                    <td>{a.user_id?.slice(0, 8) || "n8n / system"}</td>
                    <td>
                      <code>{a.entity_id.slice(0, 8)}</code>
                    </td>
                    <td>
                      <code>{JSON.stringify(a.detail)}</code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          !error && (
            <Empty detail="Activity will appear as your team uses the workspace." />
          )
        )}
      </section>
    </>
  );
}
