"use client";
import { useState } from "react";
import { Download } from "lucide-react";
import { downloadExport } from "@/lib/api";
import { ErrorBox } from "./ui";
export function ExportControls({
  researchId,
  onExport,
}: {
  researchId: string;
  onExport?: () => void;
}) {
  const [format, setFormat] = useState("csv"),
    [all, setAll] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [message, setMessage] = useState("");
  async function run() {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await downloadExport(researchId, format, all);
      setMessage(result.message);
      onExport?.();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="export-controls">
      <div className="actions">
        <select
          aria-label="Export format"
          value={format}
          onChange={(e) => setFormat(e.target.value)}
        >
          <option value="csv">CSV</option>
          <option value="xlsx">Excel (.xlsx)</option>
          <option value="json">JSON</option>
          <option value="sheets">Google Sheets preview</option>
        </select>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={all}
            onChange={(e) => setAll(e.target.checked)}
          />
          Export all statuses
        </label>
        <button className="button" disabled={busy} onClick={run}>
          <Download size={16} />
          {busy ? "Exporting…" : all ? "Export all" : "Export approved"}
        </button>
      </div>
      <ErrorBox message={error} />
      {message && (
        <p role="status" className="success-text">
          {message}
        </p>
      )}
    </div>
  );
}
