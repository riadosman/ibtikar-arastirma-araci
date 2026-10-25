"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";
import {
  Network,
  LayoutDashboard,
  ScanSearch,
  UsersRound,
  Download,
  Settings2,
  Plus,
  LogOut,
  Users,
  Code2,
  Activity,
  Menu,
  X,
  ChevronDown,
} from "lucide-react";
import { api } from "@/lib/api";
import type { User } from "@/lib/types";
import { ErrorBox, Loading } from "./ui";
const UserContext = createContext<User | null>(null);
export const useUser = () => useContext(UserContext);
const navigation = [
  { href: "/dashboard", text: "Overview", icon: LayoutDashboard },
  { href: "/research", text: "All requests", icon: ScanSearch },
  { href: "/candidates", text: "Candidates", icon: UsersRound },
  { href: "/exports", text: "Exports", icon: Download },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname(),
    router = useRouter();
  const [user, setUser] = useState<User | null>(null),
    [error, setError] = useState(""),
    [open, setOpen] = useState(false);
  useEffect(() => {
    api<User>("/auth/me")
      .then(setUser)
      .catch(() => router.replace("/login"));
  }, [router]);
  useEffect(() => setOpen(false), [pathname]);
  if (!user) return <Loading />;
  async function logout() {
    try {
      await api("/auth/logout", "POST");
      router.replace("/login");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <UserContext.Provider value={user}>
      <div className="app-shell">
        {open && (
          <button
            className="sidebar-scrim"
            aria-label="Close navigation"
            onClick={() => setOpen(false)}
          />
        )}
        <aside className={`sidebar ${open ? "open" : ""}`}>
          <Link href="/dashboard" className="brand">
            <span className="brand-mark">
              <Network size={22} />
            </span>
            relations<span className="brand-period">.</span>
          </Link>
          <div className="workspace-picker">
            <span className="workspace-icon">IR</span>
            <div>
              <strong>Relations workspace</strong>
              <small>Internal intelligence</small>
            </div>
            <ChevronDown size={14} />
          </div>
          <Link className="button primary new-research" href="/research/new">
            <Plus size={16} />
            New research
          </Link>
          <p className="nav-label">WORKSPACE</p>
          <nav aria-label="Main navigation">
            {navigation.map(({ href, text, icon: Icon }) => (
              <Link
                key={href}
                href={href}
                className={
                  pathname === href ||
                  (href === "/research" && pathname.startsWith("/research/"))
                    ? "active"
                    : ""
                }
              >
                <Icon size={18} />
                {text}
              </Link>
            ))}
            <Link
              href="/settings"
              className={pathname === "/settings" ? "active" : ""}
            >
              <Settings2 size={18} />
              Settings
            </Link>
          </nav>
          {user.role === "ADMIN" && (
            <>
              <p className="nav-label admin-label">ADMINISTRATION</p>
              <nav aria-label="Administration">
                {[
                  { href: "/admin/users", text: "Users", icon: Users },
                  {
                    href: "/admin/api",
                    text: "API & integrations",
                    icon: Code2,
                  },
                  {
                    href: "/admin/system",
                    text: "System activity",
                    icon: Activity,
                  },
                ].map(({ href, text, icon: Icon }) => (
                  <Link
                    key={href}
                    href={href}
                    className={pathname === href ? "active" : ""}
                  >
                    <Icon size={18} />
                    {text}
                  </Link>
                ))}
              </nav>
            </>
          )}
          <div className="sidebar-footer">
            <div className="human-note">
              <span className="live-dot" />
              Human decisions, better informed.
            </div>
            <div className="profile">
              <span className="avatar">
                {user.name.slice(0, 2).toUpperCase()}
              </span>
              <div>
                <strong>{user.name}</strong>
                <small>
                  {user.role === "ADMIN" ? "Administrator" : "Team member"}
                </small>
              </div>
              <button title="Sign out" aria-label="Sign out" onClick={logout}>
                <LogOut size={17} />
              </button>
            </div>
          </div>
        </aside>
        <div className="main-column">
          <div className="topbar">
            <div className="actions">
              <button
                className="mobile-menu"
                aria-label="Toggle navigation"
                onClick={() => setOpen(!open)}
              >
                {open ? <X size={20} /> : <Menu size={20} />}
              </button>
              <span>Workspace</span>
              <span className="breadcrumb-slash">/</span>
              <strong>
                {pathname.startsWith("/admin")
                  ? "Administration"
                  : pathname
                      .split("/")[1]
                      ?.replace(/^./, (c) => c.toUpperCase())}
              </strong>
            </div>
            <span className="workspace-tag">
              <span className="live-dot" />
              Private workspace
            </span>
          </div>
          <main>
            <ErrorBox message={error} />
            {children}
          </main>
          <footer className="page-footer">
            Relationship Intelligence Platform{" "}
            <span>Built around human judgment</span>
          </footer>
        </div>
      </div>
    </UserContext.Provider>
  );
}
