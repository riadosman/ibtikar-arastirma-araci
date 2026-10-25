"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import type { Research } from "@/lib/types";
import { ErrorBox, label } from "./ui";
export function ResearchForm({ initial }: { initial?: Research }) {
  const router = useRouter();
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [suggesting, setSuggesting] = useState(false);
  const [keywords, setKeywords] = useState(initial?.keywords.join(", ") || "");
  function values(form: HTMLFormElement) {
    const d = new FormData(form);
    return {
      title: d.get("title"),
      description: d.get("description"),
      field: d.get("field"),
      location: d.get("location"),
      target_type: d.get("target_type"),
      requested_quantity: Number(d.get("requested_quantity")),
      keywords: keywords
        .split(",")
        .map((k) => k.trim())
        .filter(Boolean),
      notes: d.get("notes"),
    };
  }
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const body = values(e.currentTarget);
    try {
      const result = await api<Research>(
        initial ? `/research-requests/${initial.id}` : "/research-requests",
        initial ? "PATCH" : "POST",
        {
          ...body,
          ...(initial
            ? { status: new FormData(e.currentTarget).get("status") }
            : {}),
        },
      );
      router.push(`/research/${result.id}`);
      router.refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function suggest(form: HTMLFormElement | null) {
    if (!form || !form.reportValidity()) return;
    setSuggesting(true);
    setError("");
    try {
      const result = await api<{ keywords: string[] }>(
        "/ai/interpret",
        "POST",
        values(form),
      );
      setKeywords(result.keywords.join(", "));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSuggesting(false);
    }
  }
  return (
    <form className="panel form-panel" onSubmit={submit}>
      <div className="section-heading">
        <span className="step-marker">1</span>
        <div>
          <h2>Define the brief</h2>
          <p className="muted">Tell us who you want to find and why.</p>
        </div>
      </div>
      <ErrorBox message={error} />
      <label>
        Request title
        <input
          name="title"
          defaultValue={initial?.title}
          placeholder="e.g. Computer Vision Experts"
          maxLength={200}
          required
        />
      </label>
      <label>
        Description
        <textarea
          name="description"
          defaultValue={initial?.description}
          placeholder="What are you hoping to achieve with this research?"
          rows={3}
        />
      </label>
      <div className="form-grid">
        <label>
          Field
          <input
            name="field"
            defaultValue={initial?.field}
            placeholder="e.g. Artificial Intelligence"
            maxLength={200}
            required
          />
        </label>
        <label>
          Location
          <input
            name="location"
            defaultValue={initial?.location}
            placeholder="e.g. Istanbul"
            maxLength={200}
            required
          />
        </label>
        <label>
          Target type
          <input
            name="target_type"
            list="targets"
            defaultValue={initial?.target_type || "Speaker"}
            maxLength={100}
            required
          />
          <datalist id="targets">
            <option>Speaker</option>
            <option>Expert</option>
            <option>Partner</option>
            <option>Organization</option>
          </datalist>
        </label>
        <label>
          Number of people
          <input
            name="requested_quantity"
            type="number"
            min={1}
            max={1000}
            defaultValue={initial?.requested_quantity || 20}
            required
          />
        </label>
      </div>
      <div className="section-heading section-divider">
        <span className="step-marker">2</span>
        <div>
          <h2>Add a little context</h2>
          <p className="muted">
            Help narrow the search to the people who matter.
          </p>
        </div>
      </div>
      <label>
        Keywords
        <input
          name="keywords"
          value={keywords}
          onChange={(e) => setKeywords(e.target.value)}
          placeholder="Computer Vision, Machine Learning"
        />
        <small>Separate keywords with commas.</small>
      </label>
      <button
        className="button small"
        type="button"
        disabled={suggesting}
        onClick={(e) => suggest(e.currentTarget.form)}
      >
        <Sparkles size={15} />
        {suggesting ? "Suggesting…" : "Suggest keywords"}
      </button>
      <label>
        Optional notes
        <textarea
          name="notes"
          defaultValue={initial?.notes}
          rows={3}
          placeholder="Experience, organizations, or other useful details…"
        />
      </label>
      {initial && (
        <label>
          Request status
          <select name="status" defaultValue={initial.status}>
            {["CREATED", "READY_FOR_REVIEW", "COMPLETED", "FAILED"].map((s) => (
              <option key={s} value={s}>
                {label(s)}
              </option>
            ))}
          </select>
        </label>
      )}
      <div className="form-footer">
        <span className="muted">Candidates always require human review.</span>
        <button className="button primary" disabled={busy}>
          {busy ? "Saving…" : initial ? "Save changes" : "Create research"}
          <ArrowRight size={16} />
        </button>
      </div>
    </form>
  );
}
