import Link from "next/link";
import { ArrowUpRight, SearchX } from "lucide-react";
export const statuses = [
  "NEW",
  "REVIEW",
  "APPROVED",
  "REJECTED",
  "CONTACTED",
  "ARCHIVED",
];
export const label = (text: string) =>
  text
    .toLowerCase()
    .replaceAll("_", " ")
    .replace(/^./, (c) => c.toUpperCase());
export function Badge({ value }: { value: string }) {
  return (
    <span className={`badge badge-${value.toLowerCase()}`}>
      <span className="status-dot" />
      {label(value)}
    </span>
  );
}
export function ErrorBox({ message }: { message?: string }) {
  return message ? (
    <div role="alert" className="notice error">
      {message}
    </div>
  ) : null;
}
export function Loading() {
  return (
    <div role="status" className="loading">
      <span className="spinner" />
      Loading workspace…
    </div>
  );
}
export function Empty({
  title = "Nothing here yet",
  detail,
}: {
  title?: string;
  detail: string;
}) {
  return (
    <div className="empty">
      <SearchX size={30} />
      <h3>{title}</h3>
      <p>{detail}</p>
    </div>
  );
}
export function PageHeader({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  children?: React.ReactNode;
}) {
  return (
    <header className="page-header">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {description && <p className="muted">{description}</p>}
      </div>
      <div className="actions">{children}</div>
    </header>
  );
}
export function External({
  url,
  children,
}: {
  url?: string | null;
  children?: React.ReactNode;
}) {
  return url ? (
    <a
      className="external"
      href={url}
      target="_blank"
      rel="noopener noreferrer"
    >
      {children || url}
      <ArrowUpRight size={14} />
    </a>
  ) : (
    <span className="muted">Not provided</span>
  );
}
export function Pagination({
  page,
  total,
  size = 20,
  change,
}: {
  page: number;
  total: number;
  size?: number;
  change: (n: number) => void;
}) {
  return (
    <div className="pagination">
      <span>
        {total
          ? `${(page - 1) * size + 1}–${Math.min(page * size, total)} of ${total}`
          : "0 results"}
      </span>
      <div className="actions">
        <button
          className="button small"
          disabled={page <= 1}
          onClick={() => change(page - 1)}
        >
          Previous
        </button>
        <span>Page {page}</span>
        <button
          className="button small"
          disabled={page * size >= total}
          onClick={() => change(page + 1)}
        >
          Next
        </button>
      </div>
    </div>
  );
}
export function BackLink({
  href,
  children,
}: {
  href: string;
  children: React.ReactNode;
}) {
  return (
    <Link className="back-link" href={href}>
      ← {children}
    </Link>
  );
}
