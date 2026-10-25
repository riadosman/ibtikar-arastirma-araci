import Link from "next/link";
export default function NotFound() {
  return (
    <div className="empty">
      <h1>Page not found</h1>
      <p>This page may have moved.</p>
      <Link className="button primary" href="/dashboard">
        Return to overview
      </Link>
    </div>
  );
}
