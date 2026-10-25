"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Search, Check, X, ArrowUpRight } from "lucide-react";
import { api, useData } from "@/lib/api";
import type { Page, Candidate } from "@/lib/types";
import {
  Badge,
  Empty,
  ErrorBox,
  External,
  Loading,
  Pagination,
  statuses,
  label,
} from "./ui";
export function CandidateTable({
  researchId,
  revision = 0,
  changed,
}: {
  researchId?: string;
  revision?: number;
  changed?: () => void;
}) {
  const [q, setQ] = useState(""),
    [status, setStatus] = useState(""),
    [minimum, setMinimum] = useState("0"),
    [sort, setSort] = useState("relevance_score"),
    [direction, setDirection] = useState("desc"),
    [page, setPage] = useState(1),
    [busy, setBusy] = useState(""),
    [error, setError] = useState("");
  useEffect(() => {
    if (
      !researchId &&
      new URLSearchParams(window.location.search).get("awaiting") === "true"
    )
      setStatus("AWAITING");
  }, [researchId]);
  const endpoint = researchId
    ? `/research-requests/${researchId}/candidates`
    : "/candidates";
  const {
    data,
    loading,
    error: loadError,
    reload,
  } = useData<Page<Candidate>>(
    `${endpoint}?q=${encodeURIComponent(q)}&${status === "AWAITING" ? "awaiting_review=true&" : status ? `status=${status}&` : ""}min_score=${minimum}&sort=${sort}&direction=${direction}&page=${page}&revision=${revision}`,
  );
  async function review(id: string, value: string) {
    setBusy(id);
    setError("");
    try {
      await api(`/candidates/${id}`, "PATCH", { status: value });
      reload();
      changed?.();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  return (
    <section className="panel">
      <div className="toolbar candidate-toolbar">
        <div className="search-input">
          <Search size={17} />
          <input
            aria-label="Search candidates"
            placeholder="Search people, organizations, locations…"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setPage(1);
            }}
          />
        </div>
        <select
          aria-label="Filter status"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setPage(1);
          }}
        >
          <option value="">All statuses</option>
          <option value="AWAITING">Awaiting review</option>
          {statuses.map((s) => (
            <option key={s} value={s}>
              {label(s)}
            </option>
          ))}
        </select>
        <select
          aria-label="Minimum relevance"
          value={minimum}
          onChange={(e) => {
            setMinimum(e.target.value);
            setPage(1);
          }}
        >
          <option value="0">Any relevance</option>
          <option value="40">40+ relevance</option>
          <option value="75">75+ relevance</option>
        </select>
        <select
          aria-label="Sort candidates"
          value={sort}
          onChange={(e) => {
            setSort(e.target.value);
            setPage(1);
          }}
        >
          <option value="relevance_score">Relevance</option>
          <option value="full_name">Name</option>
          <option value="organization">Organization</option>
          <option value="confidence_score">Confidence</option>
          <option value="created_at">Date added</option>
        </select>
        <button
          className="button small"
          onClick={() => setDirection((d) => (d === "asc" ? "desc" : "asc"))}
          aria-label="Toggle sort direction"
        >
          {direction === "asc" ? "↑ Asc" : "↓ Desc"}
        </button>
      </div>
      <ErrorBox message={error || loadError} />
      {loading ? (
        <Loading />
      ) : !data?.items.length ? (
        <Empty
          title="No candidates to show"
          detail="Try a different filter, run demo research, or import candidates through the API."
        />
      ) : (
        <div className="table-scroll">
          <table className="candidate-table">
            <thead>
              <tr>
                <th>Candidate</th>
                <th>Organization / role</th>
                <th>Location</th>
                <th>Relevance</th>
                <th>Confidence</th>
                <th>Source</th>
                <th>Status</th>
                <th>Review</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((c) => (
                <tr key={c.id}>
                  <td>
                    <Link
                      className="table-title candidate-name"
                      href={`/candidates/${c.id}`}
                    >
                      <span className="avatar small-avatar">
                        {c.full_name
                          .split(" ")
                          .slice(0, 2)
                          .map((n) => n[0])
                          .join("")}
                      </span>
                      <span>{c.full_name}</span>
                    </Link>
                    {c.is_demo && (
                      <span className="demo-label">FICTIONAL DEMO</span>
                    )}
                  </td>
                  <td>
                    <span>{c.organization || "Not provided"}</span>
                    <span className="table-subtitle">
                      {c.job_title || "Role not provided"}
                    </span>
                  </td>
                  <td>{c.location || "—"}</td>
                  <td>
                    <div className="score">
                      <strong
                        className={c.relevance_score >= 75 ? "score-high" : ""}
                      >
                        {c.relevance_score}
                      </strong>
                      <span className="score-track">
                        <span style={{ width: `${c.relevance_score}%` }} />
                      </span>
                    </div>
                  </td>
                  <td>
                    {c.is_demo ? (
                      <span className="muted">Unverified</span>
                    ) : (
                      `${c.confidence_score}%`
                    )}
                  </td>
                  <td>
                    <External url={c.sources[0]?.url}>
                      {c.sources[0]?.name || "No source"}
                    </External>
                  </td>
                  <td>
                    <Badge value={c.status} />
                  </td>
                  <td>
                    <div className="row-actions">
                      <button
                        disabled={busy === c.id || c.status === "APPROVED"}
                        className="approve"
                        aria-label={`Approve ${c.full_name}`}
                        title="Approve"
                        onClick={() => review(c.id, "APPROVED")}
                      >
                        <Check size={17} />
                      </button>
                      <button
                        disabled={busy === c.id || c.status === "REJECTED"}
                        aria-label={`Reject ${c.full_name}`}
                        title="Reject"
                        onClick={() => review(c.id, "REJECTED")}
                      >
                        <X size={17} />
                      </button>
                      <Link
                        href={`/candidates/${c.id}`}
                        aria-label={`View ${c.full_name}`}
                      >
                        <ArrowUpRight size={17} />
                      </Link>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data && <Pagination page={page} total={data.total} change={setPage} />}
    </section>
  );
}
