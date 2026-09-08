/**
 * Frontend tests for the Analytics view (routes/analytics.tsx).
 *
 * Covers:
 * - AUC-ROC of 0.66 is displayed as the headline model quality metric
 * - PR-AUC of 0.98 is present but clearly labeled as misleading / majority-class artifact
 * - Band distribution chart renders
 * - Feature importance chart renders
 */

import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { AnalyticsResponse } from "@/lib/api";

// Mock router
vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (opts: { component: unknown }) => opts,
  useNavigate: () => vi.fn(),
  Link: ({ children, ...props }: React.HTMLAttributes<HTMLAnchorElement>) =>
    React.createElement("a", props, children),
}));

// Mock the generated API client
vi.mock("@/lib/api", () => ({
  useGetAnalyticsSuspense: vi.fn(),
}));

import { AnalyticsContent } from "@/routes/analytics";
import { useGetAnalyticsSuspense } from "@/lib/api";

// ─── Test data ──────────────────────────────────────────────────────────────

const MOCK_ANALYTICS: AnalyticsResponse = {
  total_census: 40,
  generated_at: "2026-09-08T10:00:00.000Z",
  band_distribution: [
    { band: "Ready", count: 15, pct: 37.5 },
    { band: "Borderline", count: 14, pct: 35.0 },
    { band: "Not ready", count: 11, pct: 27.5 },
  ],
  feature_importance: [
    { feature: "Lactate (last)", importance: 0.246 },
    { feature: "Age", importance: 0.046 },
    { feature: "Length of Stay", importance: 0.035 },
  ],
  avg_los_by_band: { Ready: 2.5, Borderline: 4.1, "Not ready": 8.3 },
  vent_rate: 0.12,
  vasopressor_rate: 0.08,
};

// ─── Helpers ────────────────────────────────────────────────────────────────

function renderAnalytics() {
  (useGetAnalyticsSuspense as ReturnType<typeof vi.fn>).mockReturnValue({
    data: MOCK_ANALYTICS,
  });
  return render(<AnalyticsContent />);
}

// ─── Tests ──────────────────────────────────────────────────────────────────

describe("AnalyticsContent — analytics view", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the page heading", () => {
    renderAnalytics();
    expect(
      screen.getByRole("heading", { name: /analytics.*model performance/i }),
    ).toBeInTheDocument();
  });

  it("renders AUC-ROC 0.66 as the primary model quality metric", () => {
    renderAnalytics();
    // The AUC-ROC value 0.66 must be visible
    expect(screen.getByText("0.66")).toBeInTheDocument();
    // "AUC-ROC" label appears at least once (label in card + footer)
    expect(screen.getAllByText(/auc-roc/i).length).toBeGreaterThan(0);
    // Annotated with its limitation (may appear in card + footer)
    expect(screen.getAllByText(/modest discrimination/i).length).toBeGreaterThan(0);
  });

  it("renders PR-AUC 0.98 labeled as misleading — not as headline quality", () => {
    renderAnalytics();
    // PR-AUC value present
    expect(screen.getByText("0.98")).toBeInTheDocument();
    // Explicitly labeled as misleading (not as headline metric)
    expect(screen.getAllByText(/misleading/i).length).toBeGreaterThan(0);
    // The explanation notes class imbalance (may appear multiple times)
    expect(screen.getAllByText(/class imbalance/i).length).toBeGreaterThan(0);
  });

  it("renders the Honest Assessment framing card", () => {
    renderAnalytics();
    expect(screen.getByText(/honest assessment/i)).toBeInTheDocument();
  });

  it("renders the band distribution chart with all three bands", () => {
    renderAnalytics();
    expect(
      screen.getByText(/current readiness band distribution/i),
    ).toBeInTheDocument();
    // All three band names appear in the distribution chart
    const readyEls = screen.getAllByText("Ready");
    expect(readyEls.length).toBeGreaterThan(0);
    expect(screen.getAllByText("Borderline").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Not ready").length).toBeGreaterThan(0);
  });

  it("renders the feature importance chart with feature names", () => {
    renderAnalytics();
    expect(screen.getByText(/global feature importance/i)).toBeInTheDocument();
    // Feature names from mock data should appear
    expect(screen.getByText("Lactate (last)")).toBeInTheDocument();
    expect(screen.getByText("Age")).toBeInTheDocument();
  });

  it("explains that the output is a relative index not a probability", () => {
    renderAnalytics();
    expect(screen.getByText(/relative/i)).toBeInTheDocument();
    expect(screen.getByText(/index, not probability/i)).toBeInTheDocument();
  });
});
