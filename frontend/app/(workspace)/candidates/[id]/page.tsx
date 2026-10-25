"use client";
import { useParams } from "next/navigation";
import { useState } from "react";
import {
  Check,
  X,
  PencilLine,
  MapPin,
  Building2,
  Sparkles,
} from "lucide-react";
import { api, useData } from "@/lib/api";
import type { Candidate } from "@/lib/types";
import {
  BackLink,
  Badge,
  ErrorBox,
  External,
  Loading,
  PageHeader,
  statuses,
  label,
} from "@/components/ui";

import { SourceEditor } from "@/components/source-editor";

const fields: { key: keyof Candidate; name: string; type?: string }[] = [
  { key: "full_name", name: "Full name" },
  { key: "headline", name: "Headline" },
  { key: "job_title", name: "Job title" },
  { key: "organization", name: "Organization" },
  { key: "organization_type", name: "Organization type" },
  { key: "field", name: "Field" },
  { key: "location", name: "Location" },
  { key: "city", name: "City" },
  { key: "country", name: "Country" },
  { key: "public_email", name: "Public email", type: "email" },
  { key: "public_phone", name: "Public phone" },
  { key: "website", name: "Website", type: "url" },
  { key: "linkedin_url", name: "LinkedIn URL", type: "url" },
  { key: "twitter_url", name: "X / Twitter URL", type: "url" },
  { key: "instagram_url", name: "Instagram URL", type: "url" },
];

export default function CandidateDetail() {
  const { id } = useParams<{ id: string }>();
  const { data, error, reload } = useData<Candidate>(`/candidates/${id}`);
  const [editing, setEditing] = useState(false),
    [busy, setBusy] = useState(false),
    [actionError, setActionError] = useState(""),
    [message, setMessage] = useState(""),
    [classification, setClassification] = useState<{
      classification: string;
      explanation: string;
      provider: string;
    }>();
  async function save(body: unknown) {
    setBusy(true);
    setActionError("");
    setMessage("");
    try {
      await api(`/candidates/${id}`, "PATCH", body);
      setEditing(false);
      setMessage("Candidate updated.");
      reload();
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function editSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const body: Record<string, unknown> = {};
    fields.forEach((f) => (body[f.key] = form.get(f.key) || null));
    body.bio = form.get("bio") || null;
    body.expertise = String(form.get("expertise"))
      .split(",")
      .map((x) => x.trim())
      .filter(Boolean);
    body.sources = form
      .getAll("source_url")
      .map((url, i) => ({
        url,
        name: form.getAll("source_name")[i],
        source_type: form.getAll("source_type")[i],
        source_date: form.getAll("source_date")[i] || null,
      }));
    await save(body);
  }
  async function classify() {
    setBusy(true);
    setActionError("");
    try {
      setClassification(await api(`/candidates/${id}/classify`, "POST"));
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (error) return <ErrorBox message={error} />;
  if (!data) return <Loading />;
  return (
    <>
      <BackLink href={`/research/${data.research_request_id}`}>
        Research request
      </BackLink>
      <PageHeader
        eyebrow="CANDIDATE PROFILE"
        title={data.full_name}
        description={data.headline || data.job_title || undefined}
      >
        <button className="button" onClick={() => setEditing(!editing)}>
          <PencilLine size={16} />
          {editing ? "Cancel editing" : "Edit profile"}
        </button>
      </PageHeader>
      <ErrorBox message={actionError} />
      {message && (
        <p role="status" className="success-text">
          {message}
        </p>
      )}
      {data.is_demo && (
        <div className="notice">
          Fictional demo profile. This person and these sources are examples,
          not verified research.
        </div>
      )}
      {editing ? (
        <form onSubmit={editSubmit} className="panel form-panel">
          <h2>Edit candidate information</h2>
          <div className="form-grid">
            {fields.map((f) => (
              <label key={f.key}>
                {f.name}
                <input
                  name={f.key}
                  type={f.type || "text"}
                  defaultValue={String(data[f.key] || "")}
                  required={f.key === "full_name"}
                />
              </label>
            ))}
          </div>
          <label>
            Biography
            <textarea name="bio" rows={4} defaultValue={data.bio || ""} />
          </label>
          <label>
            Expertise (comma separated)
            <input name="expertise" defaultValue={data.expertise.join(", ")} />
          </label>
          <SourceEditor initial={data.sources} />
          <button className="button primary" disabled={busy}>
            {busy ? "Saving…" : "Save profile"}
          </button>
        </form>
      ) : (
        <div className="detail-grid">
          <div className="detail-main">
            <section className="panel detail-section">
              <div className="profile-overview">
                <span className="avatar profile-avatar">
                  {data.full_name
                    .split(" ")
                    .slice(0, 2)
                    .map((n) => n[0])
                    .join("")}
                </span>
                <div>
                  <h2>{data.job_title || "Role not provided"}</h2>
                  <p>
                    <Building2 size={15} />
                    {data.organization || "Organization not provided"}
                  </p>
                  <p>
                    <MapPin size={15} />
                    {data.location || "Location not provided"}
                  </p>
                </div>
              </div>
              <h3>About</h3>
              <p className="body-copy">
                {data.bio || "No biography provided."}
              </p>
              <div className="detail-pairs">
                <div>
                  <small>FIELD</small>
                  <p>{data.field || "Not provided"}</p>
                </div>
                <div>
                  <small>ORGANIZATION TYPE</small>
                  <p>{data.organization_type || "Not provided"}</p>
                </div>
                <div>
                  <small>CITY / COUNTRY</small>
                  <p>
                    {[data.city, data.country].filter(Boolean).join(", ") ||
                      "Not provided"}
                  </p>
                </div>
              </div>
              <h3>Expertise</h3>
              <div className="tags">
                {data.expertise.length ? (
                  data.expertise.map((x) => <span key={x}>{x}</span>)
                ) : (
                  <p className="muted">Not provided</p>
                )}
              </div>
            </section>
            <section className="panel detail-section">
              <h2>Contact & profiles</h2>
              <div className="detail-pairs">
                <div>
                  <small>PUBLIC EMAIL</small>
                  <p>{data.public_email || "Not provided"}</p>
                </div>
                <div>
                  <small>PUBLIC PHONE</small>
                  <p>{data.public_phone || "Not provided"}</p>
                </div>
                {[
                  ["Website", data.website],
                  ["LinkedIn", data.linkedin_url],
                  ["X / Twitter", data.twitter_url],
                  ["Instagram", data.instagram_url],
                ].map(([name, url]) => (
                  <div key={name}>
                    <small>{name}</small>
                    <p>
                      <External url={url} />
                    </p>
                  </div>
                ))}
              </div>
            </section>
            <section className="panel detail-section">
              <h2>
                Sources{" "}
                <span className="count-pill">{data.sources.length}</span>
              </h2>
              <p className="muted">
                Open the original evidence before making a decision.
              </p>
              {data.sources.map((s) => (
                <div className="source-row" key={s.id || s.url}>
                  <div>
                    <strong>{s.name}</strong>
                    <span className="table-subtitle">
                      {label(s.source_type)}
                      {s.source_date
                        ? ` · ${new Date(s.source_date).toLocaleDateString()}`
                        : ""}
                    </span>
                    <External url={s.url} />
                  </div>
                </div>
              ))}
            </section>
          </div>
          <aside className="detail-aside">
            <section className="panel detail-section">
              <p className="eyebrow">FIT FOR THIS REQUEST</p>
              <div className="large-score">
                {data.relevance_score}
                <span>/ 100</span>
              </div>
              <p className="body-copy">{data.relevance_reason}</p>
              <div className="confidence-row">
                <span>Confidence</span>
                <strong>
                  {data.is_demo
                    ? "Unverified demo"
                    : `${data.confidence_score}%`}
                </strong>
              </div>
              <p className="fine-print">
                Confidence reflects source count and profile completeness, not
                independent verification.
              </p>
              <button
                className="button small"
                disabled={busy}
                onClick={classify}
              >
                <Sparkles size={15} />
                Explain classification
              </button>
              {classification && (
                <div className="notice">
                  <strong>{classification.classification}</strong>
                  <p>{classification.explanation}</p>
                  <small>Provider: {classification.provider}</small>
                </div>
              )}
            </section>
            <section className="panel detail-section review-panel">
              <h2>Your review</h2>
              <Badge value={data.status} />
              <div className="actions review-buttons">
                <button
                  className="button primary"
                  disabled={busy || data.status === "APPROVED"}
                  onClick={() => save({ status: "APPROVED" })}
                >
                  <Check size={16} />
                  Approve
                </button>
                <button
                  className="button"
                  disabled={busy || data.status === "REJECTED"}
                  onClick={() => save({ status: "REJECTED" })}
                >
                  <X size={16} />
                  Reject
                </button>
              </div>
              <form
                key={`${data.updated_at}-${data.status}`}
                onSubmit={(e) => {
                  e.preventDefault();
                  const f = new FormData(e.currentTarget);
                  void save({ status: f.get("status"), notes: f.get("notes") });
                }}
              >
                <label>
                  Status
                  <select name="status" defaultValue={data.status}>
                    {statuses.map((s) => (
                      <option key={s} value={s}>
                        {label(s)}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Review notes
                  <textarea
                    name="notes"
                    rows={5}
                    defaultValue={data.notes}
                    placeholder="Why is this person a good fit?"
                  />
                </label>
                <button className="button full-width" disabled={busy}>
                  Save review
                </button>
              </form>
            </section>
            <p className="fine-print">
              Added {new Date(data.created_at).toLocaleDateString()} · Updated{" "}
              {new Date(data.updated_at).toLocaleDateString()}
            </p>
          </aside>
        </div>
      )}
    </>
  );
}
