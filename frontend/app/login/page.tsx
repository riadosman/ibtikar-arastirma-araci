"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Network, ArrowRight } from "lucide-react";
import { api } from "@/lib/api";
import { ErrorBox } from "@/components/ui";
export default function LoginPage() {
  const router = useRouter();
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    try {
      await api("/auth/login", "POST", {
        email: data.get("email"),
        password: data.get("password"),
      });
      router.replace("/dashboard");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="login-page">
      <div className="login-story">
        <div className="brand">
          <span className="brand-mark">
            <Network size={24} />
          </span>
          relations.
        </div>
        <div>
          <p className="eyebrow">RELATIONSHIP INTELLIGENCE</p>
          <h1>
            The right people.
            <br />A clearer picture.
          </h1>
          <p>
            Turn research into meaningful connections.
            <br />
            Discover, review, and organize expertise in one place.
          </p>
          <div className="login-flow">
            <span>Discover</span>
            <ArrowRight size={18} />
            <span>Review</span>
            <ArrowRight size={18} />
            <span>Connect</span>
          </div>
        </div>
        <small>Thoughtful research. Human decisions.</small>
      </div>
      <div className="login-form-area">
        <form onSubmit={submit} className="login-form">
          <p className="eyebrow">YOUR WORKSPACE AWAITS</p>
          <h1>Welcome back</h1>
          <p className="muted">Sign in to your relations workspace.</p>
          <ErrorBox message={error} />
          <label>
            Email address
            <input
              name="email"
              type="email"
              autoComplete="username"
              placeholder="you@organization.com"
              required
            />
          </label>
          <label>
            Password
            <input
              name="password"
              type="password"
              autoComplete="current-password"
              required
            />
          </label>
          <button className="button primary" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
            <ArrowRight size={17} />
          </button>
          <p className="login-help">
            Need access? Contact your workspace administrator.
          </p>
        </form>
      </div>
    </div>
  );
}
