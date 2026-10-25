"use client";
export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <div className="empty">
      <h1>Unable to load this page</h1>
      <p>Please try again.</p>
      <button className="button" onClick={reset}>
        Retry
      </button>
    </div>
  );
}
