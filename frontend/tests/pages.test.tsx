import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach } from "vitest";
import DashboardPage from "@/app/(workspace)/dashboard/page";
import NewResearchPage from "@/app/(workspace)/research/new/page";
import CandidatesPage from "@/app/(workspace)/candidates/page";
import ExportsPage from "@/app/(workspace)/exports/page";
import ResearchPage from "@/app/(workspace)/research/page";
import ResearchDetail from "@/app/(workspace)/research/[id]/page";
import CandidateDetail from "@/app/(workspace)/candidates/[id]/page";
import LoginPage from "@/app/login/page";
import { ExportControls } from "@/components/export-controls";
const mocks = vi.hoisted(() => ({
  api: vi.fn(),
  useData: vi.fn(),
  downloadExport: vi.fn(),
  push: vi.fn(),
  replace: vi.fn(),
  refresh: vi.fn(),
}));
vi.mock("@/lib/api", () => mocks);
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mocks.push,
    replace: mocks.replace,
    refresh: mocks.refresh,
  }),
  useParams: () => ({ id: "request-id" }),
}));
const request = {
  id: "request-id",
  title: "Vision experts",
  description: "Find speakers",
  field: "AI",
  location: "Istanbul",
  target_type: "Speaker",
  requested_quantity: 20,
  keywords: ["Vision"],
  notes: "",
  status: "READY_FOR_REVIEW",
  created_at: "2026-01-01",
  creator_name: "Admin",
  stats: {
    total: 2,
    approved: 1,
    rejected: 0,
    awaiting_review: 1,
    high: 1,
    medium: 1,
    low: 0,
  },
};
const candidate = {
  id: "candidate-id",
  research_request_id: "request-id",
  full_name: "Example Person",
  job_title: "Researcher",
  organization: "Example Lab",
  location: "Istanbul",
  relevance_score: 80,
  confidence_score: 50,
  relevance_reason: "Keyword match.",
  status: "NEW",
  notes: "",
  expertise: ["Vision"],
  sources: [
    {
      id: "source-id",
      url: "https://example.com/profile",
      name: "Example source",
      source_type: "website",
    },
  ],
  created_at: "2026-01-01",
  updated_at: "2026-01-01",
};
beforeEach(() => {
  vi.clearAllMocks();
  mocks.useData.mockImplementation((path: string) => ({
    data:
      path === "/dashboard"
        ? {
            active_requests: 1,
            candidates_found: 2,
            awaiting_review: 1,
            approved: 1,
            rejected: 0,
            recent_requests: [request],
          }
        : path === "/settings"
          ? { demo_mode: true }
          : path === "/research-requests/request-id"
            ? request
            : path === "/candidates/request-id"
              ? candidate
              : path.startsWith("/research-requests") &&
                  !path.includes("/candidates")
                ? { items: [request], total: 1 }
                : path.startsWith("/exports")
                  ? { items: [], total: 0 }
                  : { items: [candidate], total: 1 },
    loading: false,
    error: "",
    reload: vi.fn(),
  }));
  mocks.api.mockResolvedValue({ id: "request-id" });
  mocks.downloadExport.mockResolvedValue({ message: "Export downloaded." });
});
describe("main screens", () => {
  it("renders dashboard counts and real request links", () => {
    render(<DashboardPage />);
    expect(
      screen.getByRole("heading", { name: "Workspace overview" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Vision experts" }),
    ).toHaveAttribute("href", "/research/request-id");
  });
  it("renders research list", () => {
    render(<ResearchPage />);
    expect(
      screen.getByRole("heading", { name: "All requests" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("textbox", { name: "Search research" }),
    ).toBeInTheDocument();
  });
  it("submits a validated research brief", async () => {
    render(<NewResearchPage />);
    fireEvent.change(screen.getByLabelText("Request title"), {
      target: { value: "New brief" },
    });
    fireEvent.change(screen.getByLabelText("Field"), {
      target: { value: "AI" },
    });
    fireEvent.change(screen.getByLabelText("Location"), {
      target: { value: "Istanbul" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create research" }));
    await waitFor(() =>
      expect(mocks.api).toHaveBeenCalledWith(
        "/research-requests",
        "POST",
        expect.objectContaining({ title: "New brief", requested_quantity: 20 }),
      ),
    );
  });
  it("renders details with sources and a human review action", async () => {
    render(<CandidateDetail />);
    expect(
      screen.getByRole("heading", { name: "Example Person" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /example.com/ })).toHaveAttribute(
      "href",
      "https://example.com/profile",
    );
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() =>
      expect(mocks.api).toHaveBeenCalledWith(
        "/candidates/request-id",
        "PATCH",
        { status: "APPROVED" },
      ),
    );
  });
  it("renders candidates with search and filtering", () => {
    render(<CandidatesPage />);
    expect(
      screen.getByRole("combobox", { name: "Filter status" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "View Example Person" }),
    ).toBeInTheDocument();
  });
  it("renders research details and demo search", () => {
    render(<ResearchDetail />);
    expect(
      screen.getByRole("heading", { name: "Vision experts" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Run demo search" }),
    ).toBeInTheDocument();
  });
  it("renders export history empty state", () => {
    render(<ExportsPage />);
    expect(screen.getByText("No exports yet")).toBeInTheDocument();
  });
  it("exports approved candidates by default", async () => {
    render(<ExportControls researchId="request-id" />);
    fireEvent.click(screen.getByRole("button", { name: "Export approved" }));
    await waitFor(() =>
      expect(mocks.downloadExport).toHaveBeenCalledWith(
        "request-id",
        "csv",
        false,
      ),
    );
  });
  it("shows login errors without losing form", async () => {
    mocks.api.mockRejectedValue(new Error("Incorrect email or password."));
    render(<LoginPage />);
    fireEvent.change(screen.getByLabelText("Email address"), {
      target: { value: "admin@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "wrong" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Incorrect email or password.",
    );
  });
});
