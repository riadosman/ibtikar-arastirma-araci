"use client";
import Link from "next/link";
import { useState } from "react";
import { Plus, Search } from "lucide-react";
import { useData } from "@/lib/api";
import type { Page, Research } from "@/lib/types";
import { ErrorBox, Loading, PageHeader, Pagination } from "@/components/ui";
import { ResearchTable } from "@/components/research-table";
export default function ResearchPage() {
  const [q, setQ] = useState(""),
    [page, setPage] = useState(1);
  const { data, error, loading } = useData<Page<Research>>(
    `/research-requests?q=${encodeURIComponent(q)}&page=${page}`,
  );
  return (
    <>
      <PageHeader
        eyebrow="RESEARCH"
        title="All requests"
        description="A focused brief. A thoughtful shortlist."
      >
        <Link className="button primary" href="/research/new">
          <Plus size={17} />
          New research
        </Link>
      </PageHeader>
      <section className="panel">
        <div className="toolbar">
          <div className="search-input">
            <Search size={17} />
            <input
              aria-label="Search research"
              placeholder="Search requests…"
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setPage(1);
              }}
            />
          </div>
          <span className="muted">{data?.total || 0} requests</span>
        </div>
        <ErrorBox message={error} />
        {loading ? (
          <Loading />
        ) : (
          data && (
            <>
              <ResearchTable items={data.items} />
              <Pagination page={page} total={data.total} change={setPage} />
            </>
          )
        )}
      </section>
    </>
  );
}
