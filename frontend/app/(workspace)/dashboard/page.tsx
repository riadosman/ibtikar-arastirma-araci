"use client";
import Link from "next/link";
import {
  Plus,
  ArrowRight,
  ScanSearch,
  UsersRound,
  CircleCheck,
  Clock3,
  CircleX,
  ArrowUpRight,
} from "lucide-react";
import { useData } from "@/lib/api";
import type { Dashboard } from "@/lib/types";
import { ErrorBox, Loading, PageHeader } from "@/components/ui";
import { ResearchTable } from "@/components/research-table";
export default function DashboardPage() {
  const { data, error, loading } = useData<Dashboard>("/dashboard");
  if (error) return <ErrorBox message={error} />;
  if (loading || !data) return <Loading />;
  const metrics = [
    {
      name: "Active research",
      value: data.active_requests,
      icon: ScanSearch,
      note: "Requests in progress",
    },
    {
      name: "Candidates found",
      value: data.candidates_found,
      icon: UsersRound,
      note: "Across your workspace",
    },
    {
      name: "Awaiting review",
      value: data.awaiting_review,
      icon: Clock3,
      note: "Ready for your judgment",
    },
    {
      name: "Approved",
      value: data.approved,
      icon: CircleCheck,
      note: "Selected by your team",
    },
    {
      name: "Rejected",
      value: data.rejected,
      icon: CircleX,
      note: "Reviewed and set aside",
    },
  ];
  return (
    <>
      <PageHeader
        eyebrow="THE BIG PICTURE"
        title="Workspace overview"
        description="Your research, your people, and what comes next."
      >
        <Link className="button primary" href="/research/new">
          <Plus size={17} />
          New research
        </Link>
      </PageHeader>
      <div className="metrics">
        {metrics.map(({ name, value, icon: Icon, note }) => (
          <div className="metric" key={name}>
            <div className="metric-top">
              <span>{name}</span>
              <Icon size={17} />
            </div>
            <strong>{value}</strong>
            <small>{note}</small>
          </div>
        ))}
      </div>
      <div className="review-callout">
        <span className="review-callout-icon">
          <UsersRound size={25} />
        </span>
        <div>
          <p className="eyebrow">A LITTLE REVIEW GOES A LONG WAY</p>
          <h2>
            {data.awaiting_review
              ? `${data.awaiting_review} candidates are waiting for a closer look.`
              : "All caught up on candidate review."}
          </h2>
          <p>
            Check the evidence, consider the fit, and choose who moves forward.
          </p>
        </div>
        <Link className="button" href="/candidates?awaiting=true">
          Review candidates
          <ArrowRight size={16} />
        </Link>
      </div>
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Recent research</h2>
            <p className="muted">From a question to a considered shortlist.</p>
          </div>
          <Link className="text-link" href="/research">
            View all requests
            <ArrowUpRight size={16} />
          </Link>
        </div>
        <ResearchTable items={data.recent_requests} />
      </section>
      <div className="workflow-note">
        <span className="workflow-number">01</span>
        <div>
          <strong>Define your search</strong>
          <p>A clear brief makes better research.</p>
        </div>
        <ArrowRight size={16} />
        <span className="workflow-number">02</span>
        <div>
          <strong>Review the evidence</strong>
          <p>Every profile keeps its sources.</p>
        </div>
        <ArrowRight size={16} />
        <span className="workflow-number">03</span>
        <div>
          <strong>Build your shortlist</strong>
          <p>Export the people you approve.</p>
        </div>
      </div>
    </>
  );
}
