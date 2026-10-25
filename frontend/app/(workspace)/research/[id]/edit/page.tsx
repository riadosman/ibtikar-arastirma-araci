"use client";
import { useParams } from "next/navigation";
import { useData } from "@/lib/api";
import type { Research } from "@/lib/types";
import { ResearchForm } from "@/components/research-form";
import { BackLink, PageHeader, ErrorBox, Loading } from "@/components/ui";
export default function EditResearchPage() {
  const { id } = useParams<{ id: string }>();
  const { data, error, loading } = useData<Research>(
    `/research-requests/${id}`,
  );
  return (
    <>
      <BackLink href={`/research/${id}`}>Research details</BackLink>
      <PageHeader title="Edit research" />
      <ErrorBox message={error} />
      {loading ? <Loading /> : data && <ResearchForm initial={data} />}
    </>
  );
}
