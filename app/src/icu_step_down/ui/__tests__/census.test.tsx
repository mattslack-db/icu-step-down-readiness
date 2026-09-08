/**
 * Frontend tests for the Census dashboard view (routes/index.tsx).
 *
 * Covers:
 * - Summary cards rendered for all three readiness bands
 * - Patient ranking table with sorting controls
 * - Band assignment: ≥66 → Ready/🟢, 33-65 → Borderline/🟡, <33 → Not ready/🔴
 * - Readiness displayed as an index (0–100), NOT as a discharge probability "%"
 */

import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { CensusResponse } from "@/lib/api";

// Mock router — createFileRoute is called at module load time
vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (opts: { component: unknown }) => opts,
  useNavigate: () => vi.fn(),
  Link: ({ children, ...props }: React.HTMLAttributes<HTMLAnchorElement>) =>
    React.createElement("a", props, children),
}));

// Mock the generated API client — no network calls
vi.mock("@/lib/api", () => ({
  useGetCensusSuspense: vi.fn(),
}));

// Import the component after mocks are registered
import { CensusDashboard } from "@/routes/index";
import { useGetCensusSuspense } from "@/lib/api";

// ─── Test data ──────────────────────────────────────────────────────────────

const MOCK_CENSUS: CensusResponse = {
  total: 3,
  generated_at: "2026-09-08T10:00:00.000Z",
  patients: [
    {
      icustay_id: "icu-001",
      subject_id: "sub-001",
      readiness_index: 75,   // ≥66 → Ready
      readiness_score: 0.8,
      band: "Ready",
      age: 65,
      los: 3.5,
      on_vasopressors: false,
      on_ventilator: false,
      top_factors: [
        { direction: "supports", magnitude: 0.3, name: "Good SpO2" },
      ],
    },
    {
      icustay_id: "icu-002",
      subject_id: "sub-002",
      readiness_index: 50,   // 33-65 → Borderline
      readiness_score: 0.55,
      band: "Borderline",
      age: 55,
      los: 2.0,
      on_vasopressors: false,
      on_ventilator: false,
      top_factors: [],
    },
    {
      icustay_id: "icu-003",
      subject_id: "sub-003",
      readiness_index: 20,   // <33 → Not ready
      readiness_score: 0.3,
      band: "Not ready",
      age: 72,
      los: 7.0,
      on_vasopressors: true,
      on_ventilator: false,
      top_factors: [
        { direction: "risk", magnitude: 0.5, name: "Elevated lactate" },
      ],
    },
  ],
};

// ─── Helpers ────────────────────────────────────────────────────────────────

function renderCensus() {
  (useGetCensusSuspense as ReturnType<typeof vi.fn>).mockReturnValue({
    data: MOCK_CENSUS,
  });
  return render(<CensusDashboard />);
}

// ─── Tests ──────────────────────────────────────────────────────────────────

describe("CensusDashboard — census view", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the ICU Census Dashboard heading", () => {
    renderCensus();
    expect(
      screen.getByRole("heading", { name: /icu census dashboard/i }),
    ).toBeInTheDocument();
  });

  it("renders summary cards for total patients and all three bands", () => {
    renderCensus();
    // Total ICU count appears at least once (may also appear elsewhere in the page)
    expect(screen.getAllByText("3").length).toBeGreaterThan(0);
    // Summary card titles (upper-case via CSS — test text content)
    expect(screen.getByText(/🟢 Ready/i)).toBeInTheDocument();
    expect(screen.getByText(/🟡 Borderline/i)).toBeInTheDocument();
    expect(screen.getByText(/🔴 Not Ready/i)).toBeInTheDocument();
  });

  it("renders sorting controls for Readiness Index, LOS, and Age", () => {
    renderCensus();
    expect(
      screen.getByRole("button", { name: /readiness index/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /los/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /age/i }),
    ).toBeInTheDocument();
  });

  it("shows the Patient Ranking table header", () => {
    renderCensus();
    expect(screen.getByText(/patient ranking/i)).toBeInTheDocument();
  });

  it("shows Ready band for patient with readiness_index >= 66", () => {
    renderCensus();
    // Patient icu-001 has index=75, band='Ready'
    const readyBadges = screen.getAllByText("Ready");
    expect(readyBadges.length).toBeGreaterThan(0);
  });

  it("shows Borderline band for patient with 33 <= readiness_index < 66", () => {
    renderCensus();
    // Patient icu-002 has index=50, band='Borderline'
    const borderlineBadges = screen.getAllByText("Borderline");
    expect(borderlineBadges.length).toBeGreaterThan(0);
  });

  it("shows Not ready band for patient with readiness_index < 33", () => {
    renderCensus();
    // Patient icu-003 has index=20, band='Not ready'
    const notReadyBadges = screen.getAllByText("Not ready");
    expect(notReadyBadges.length).toBeGreaterThan(0);
  });

  it("renders readiness as an index (0–100, relative) — not as a discharge probability", () => {
    renderCensus();
    // The column header must say "(0–100, relative)", not "probability" or "%"
    expect(screen.getByText(/0–100, relative/i)).toBeInTheDocument();
    // The disclaimer must distinguish from probability
    expect(
      screen.getByText(/not a discharge probability/i),
    ).toBeInTheDocument();
    // The index values (75, 50, 20) are displayed as bare numbers in the table
    expect(screen.getAllByText("75").length).toBeGreaterThan(0);
    expect(screen.getAllByText("50").length).toBeGreaterThan(0);
    expect(screen.getAllByText("20").length).toBeGreaterThan(0);
  });

  it("renders supporting factor direction for the Ready patient", () => {
    renderCensus();
    // The top_factors for icu-001 include a 'supports' factor
    expect(screen.getByText(/good spo2/i)).toBeInTheDocument();
  });
});
