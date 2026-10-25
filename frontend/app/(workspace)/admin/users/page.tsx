"use client";
import { useState } from "react";
import { api, useData } from "@/lib/api";
import type { User } from "@/lib/types";
import { useUser } from "@/components/shell";
import { ErrorBox, Loading, PageHeader } from "@/components/ui";
export default function UsersPage() {
  const { data, error, reload } = useData<User[]>("/admin/users");
  const me = useUser();
  const [busy, setBusy] = useState(false),
    [actionError, setActionError] = useState("");
  async function create(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget,
      d = new FormData(form);
    setBusy(true);
    setActionError("");
    try {
      await api("/admin/users", "POST", Object.fromEntries(d));
      form.reset();
      reload();
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function toggle(id: string) {
    setBusy(true);
    try {
      await api(`/admin/users/${id}/toggle`, "POST");
      reload();
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeader
        eyebrow="ADMINISTRATION"
        title="Workspace users"
        description="Give your team access to a shared research workspace."
      />
      <ErrorBox message={error || actionError} />
      {!data && !error ? (
        <Loading />
      ) : (
        data && (
          <>
            <section className="panel">
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Email</th>
                      <th>Role</th>
                      <th>Access</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.map((u) => (
                      <tr key={u.id}>
                        <td>{u.name}</td>
                        <td>{u.email}</td>
                        <td>{u.role}</td>
                        <td>{u.active ? "Active" : "Inactive"}</td>
                        <td>
                          <button
                            className="button small"
                            disabled={busy || u.id === me?.id}
                            onClick={() => toggle(u.id)}
                          >
                            {u.active ? "Deactivate" : "Activate"}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
            <form className="panel form-panel" onSubmit={create}>
              <h2>Add a team member</h2>
              <div className="form-grid">
                <label>
                  Name
                  <input name="name" required maxLength={200} />
                </label>
                <label>
                  Email
                  <input name="email" type="email" required />
                </label>
                <label>
                  Initial password
                  <input
                    name="password"
                    type="password"
                    autoComplete="new-password"
                    minLength={12}
                    maxLength={256}
                    required
                  />
                  <small>At least 12 characters.</small>
                </label>
                <label>
                  Role
                  <select name="role">
                    <option value="USER">Team member</option>
                    <option value="ADMIN">Administrator</option>
                  </select>
                </label>
              </div>
              <button className="button primary" disabled={busy}>
                Create user
              </button>
            </form>
          </>
        )
      )}
    </>
  );
}
