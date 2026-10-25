"use client";
import { useCallback, useEffect, useState } from "react";

async function errorMessage(response: Response) {
  const data = await response.json().catch(() => null);
  if (Array.isArray(data?.detail))
    return data.detail
      .map(
        (e: { loc: string[]; msg: string }) =>
          `${e.loc.slice(1).join(".")}: ${e.msg}`,
      )
      .join("; ");
  return typeof data?.detail === "string"
    ? data.detail
    : "Something went wrong. Please try again.";
}

export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    method,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "RelationshipPlatform",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    if (
      response.status === 401 &&
      !path.startsWith("/auth/") &&
      typeof window !== "undefined"
    )
      window.location.assign("/login");
    throw new Error(await errorMessage(response));
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export function useData<T>(path: string) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState(0);
  const reload = useCallback(() => setVersion((v) => v + 1), []);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    api<T>(path)
      .then((value) => {
        if (active) setData(value);
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [path, version]);
  return { data, error, loading, reload };
}

export async function downloadExport(
  id: string,
  format: string,
  includeAll: boolean,
) {
  const response = await fetch(`/api/v1/research-requests/${id}/exports`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "RelationshipPlatform",
    },
    body: JSON.stringify({ format, include_all: includeAll }),
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  if (format === "sheets") return response.json();
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = `candidates-${id.slice(0, 8)}.${format}`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  return { message: "Export downloaded." };
}
