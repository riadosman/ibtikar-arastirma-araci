"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { Play, PencilLine, MapPin, Target, Tag } from "lucide-react";
import { api, useData } from "@/lib/api";
import type { Research, Settings } from "@/lib/types";
import {
  BackLink,
  Badge,
  ErrorBox,
  Loading,
  PageHeader,
} from "@/components/ui";
import { CandidateTable } from "@/components/candidate-table";
import { ExportControls } from "@/components/export-controls";
export default function ResearchDetail() {
  const { id } = useParams<{ id: string }>();
  const { data, error, loading, reload } = useData<Research>(
    `/research-requests/${id}`,
  );
  const config = useData<Settings>("/settings");
  const [busy, setBusy] = useState(false),
    [actionError, setActionError] = useState(""),
    [revision, setRevision] = useState(0),
    [message, setMessage] = useState("");
  async function run() {
    setBusy(true);
    setActionError("");
    try {
      const r = await api<{ created: number; merged: number }>(
        `/research-requests/${id}/run`,
        "POST",
      );
      setMessage(
        `${r.created} demo candidates added; ${r.merged} existing profiles merged.`,
      );
      setRevision((v) => v + 1);
      reload();
    } catch (e) {
      setActionError((e as Error).message);
      reload();
    } finally {
      setBusy(false);
    }
  }
  if (error) return <ErrorBox message={error} />;
  if (!data) return <Loading />;
  return (
    <>
      <BackLink href="/research">All requests</BackLink>
      <PageHeader
        eyebrow="RESEARCH BRIEF"
        title={data.title}
        description={data.description}
      >
        <Link className="button" href={`/research/${id}/edit`}>
          <PencilLine size={15} />
          Edit brief
        </Link>
        {config.data?.demo_mode && (
          <button className="button primary" disabled={busy} onClick={run}>
            <Play size={15} />
            {busy ? "Running demo…" : "Run demo search"}
          </button>
        )}
      </PageHeader>
      <ErrorBox message={actionError || data.error || undefined} />
      {message && (
        <p role="status" className="notice">
          {message} Demo identities and sources are fictional.
        </p>
      )}
      <div className="research-meta">
        <Badge value={data.status} />
        <span>
          <MapPin size={15} />
          {data.location}
        </span>
        <span>
          <Target size={15} />
          {data.requested_quantity} {data.target_type.toLowerCase()}s requested
        </span>
        <span>
          <Tag size={15} />
          {data.field}
        </span>
        <span>Created by {data.creator_name}</span>
      </div>
      {!!data.keywords.length && (
        <div className="tags">
          {data.keywords.map((k) => (
            <span key={k}>{k}</span>
          ))}
        </div>
      )}
      {data.notes && <p className="brief-notes">{data.notes}</p>}
      <div className="mini-metrics">
        {[
          ["Candidates found", data.stats.total],
          ["High relevance", data.stats.high],
          ["Medium relevance", data.stats.medium],
          ["Low relevance", data.stats.low],
          ["Approved", data.stats.approved],
          ["Rejected", data.stats.rejected],
        ].map(([name, value]) => (
          <div key={name}>
            <span>{name}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
      <div className="section-topline">
        <div>
          <h2>Candidate review</h2>
          <p className="muted">
            Scores guide your attention. You make the decision.
          </p>
        </div>
        <ExportControls researchId={id} />
      </div>
      <CandidateTable researchId={id} revision={revision} changed={reload} />
      {loading && <span className="sr-only">Refreshing statistics</span>}
    </>
  );
}
