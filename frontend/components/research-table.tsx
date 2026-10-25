import Link from "next/link";
import { ArrowUpRight, MapPin } from "lucide-react";
import type { Research } from "@/lib/types";
import { Badge, Empty } from "./ui";
export function ResearchTable({ items }: { items: Research[] }) {
  if (!items.length)
    return (
      <Empty
        title="Your next connection starts here"
        detail="Create a research request to start discovering relevant people."
      />
    );
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Research request</th>
            <th>Status</th>
            <th>Candidates</th>
            <th>Approved</th>
            <th>Created</th>
            <th>
              <span className="sr-only">Open</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((r) => (
            <tr key={r.id}>
              <td>
                <Link className="table-title" href={`/research/${r.id}`}>
                  {r.title}
                </Link>
                <span className="table-subtitle">
                  <MapPin size={12} />
                  {r.location}
                  <span>·</span>
                  {r.requested_quantity} requested
                </span>
              </td>
              <td>
                <Badge value={r.status} />
              </td>
              <td className="number">{r.stats.total}</td>
              <td>
                <span className="approved-count">{r.stats.approved}</span>
                <span className="muted"> / {r.requested_quantity}</span>
              </td>
              <td className="muted">
                {new Date(r.created_at).toLocaleDateString("en-GB", {
                  day: "numeric",
                  month: "short",
                  year: "numeric",
                })}
              </td>
              <td>
                <Link
                  aria-label={`Open ${r.title}`}
                  className="icon-link"
                  href={`/research/${r.id}`}
                >
                  <ArrowUpRight size={18} />
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
