"use client";
import { useState } from "react";
import type { Source } from "@/lib/types";
export function SourceEditor({ initial }: { initial: Source[] }) {
  const [sources, setSources] = useState(initial);
  return (
    <div className="source-editor">
      <h3>Sources</h3>
      <p className="muted">
        Keep at least one link to the evidence behind this profile.
      </p>
      {sources.map((source, index) => (
        <div className="source-row" key={index}>
          <div className="form-grid">
            <label>
              Source name
              <input
                name="source_name"
                value={source.name}
                required
                onChange={(e) =>
                  setSources((values) =>
                    values.map((s, i) =>
                      i === index ? { ...s, name: e.target.value } : s,
                    ),
                  )
                }
              />
            </label>
            <label>
              Source type
              <input
                name="source_type"
                value={source.source_type}
                required
                onChange={(e) =>
                  setSources((values) =>
                    values.map((s, i) =>
                      i === index ? { ...s, source_type: e.target.value } : s,
                    ),
                  )
                }
              />
            </label>
          </div>
          <label>
            Source URL
            <input
              name="source_url"
              type="url"
              value={source.url}
              required
              onChange={(e) =>
                setSources((values) =>
                  values.map((s, i) =>
                    i === index ? { ...s, url: e.target.value } : s,
                  ),
                )
              }
            />
          </label>
          <input
            type="hidden"
            name="source_date"
            value={source.source_date || ""}
          />
          <button
            className="button small"
            type="button"
            disabled={sources.length === 1}
            onClick={() =>
              setSources((values) => values.filter((_, i) => i !== index))
            }
          >
            Remove source
          </button>
        </div>
      ))}
      <button
        className="button small"
        type="button"
        disabled={sources.length >= 30}
        onClick={() =>
          setSources((values) => [
            ...values,
            { name: "", url: "", source_type: "website" },
          ])
        }
      >
        Add source
      </button>
    </div>
  );
}
