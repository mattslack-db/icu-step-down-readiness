/**
 * Frontend tests for the Analytics view (routes/analytics.tsx).
 *
 * Covers:
 * - AUC-ROC of 0.74 (v7) is the headline metric, shown next to the 0.64
 *   readmission-only AUC and explained by the left-the-ICU-alive cohort
 * - Not-safe PR-AUC of 0.23 (vs 4.7% base rate) is the precision metric
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

const MOCK_DRIFT: AnalyticsResponse["drift_status"] = {
  psi: 0.07,
  ks: 0.12,
  verdict: "stable",
  n_live: 150,
  model_version: "2",
  computed_at: "2026-09-26T06:00:00.000Z",
};

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
  drift_status: MOCK_DRIFT,
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

  it("renders AUC-ROC 0.74 as the primary model quality metric", () => {
    renderAnalytics();
    expect(screen.getByText("0.74")).toBeInTheDocument();
    // "AUC-ROC" label appears at least once (label in card + footer)
    expect(screen.getAllByText(/auc-roc/i).length).toBeGreaterThan(0);
  });

  it("shows readmission-only AUC 0.64 alongside the headline — gain is not overstated", () => {
    renderAnalytics();
    expect(screen.getByText("0.64")).toBeInTheDocument();
    expect(screen.getAllByText(/readmission-only/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/death/i).length).toBeGreaterThan(0);
  });

  it("renders the not-safe PR-AUC 0.23 as the precision metric", () => {
    renderAnalytics();
    expect(screen.getByText("0.23")).toBeInTheDocument();
    expect(screen.getAllByText(/not-safe pr-auc/i).length).toBeGreaterThan(0);
  });

  it("explains that the model is evaluated only on patients who left the ICU alive", () => {
    renderAnalytics();
    expect(screen.getByText(/left the ICU alive/i)).toBeInTheDocument();
    expect(screen.queryByText("0.89")).not.toBeInTheDocument();
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

  it("renders the drift monitor tile with PSI value when drift data is present", () => {
    renderAnalytics();
    // The tile heading must appear
    expect(screen.getByText(/model drift monitor/i)).toBeInTheDocument();
    // PSI value rendered (0.07 → "0.070")
    expect(screen.getByText("0.070")).toBeInTheDocument();
    // Verdict "Stable" is shown
    expect(screen.getByText("Stable")).toBeInTheDocument();
  });

  it("renders the drift monitor tile in no-data state when drift_status is null", () => {
    (useGetAnalyticsSuspense as ReturnType<typeof vi.fn>).mockReturnValue({
      data: { ...MOCK_ANALYTICS, drift_status: null },
    });
    render(<AnalyticsContent />);
    expect(screen.getByText(/model drift monitor/i)).toBeInTheDocument();
    expect(screen.getByText(/daily drift-check job has not run/i)).toBeInTheDocument();
  });
});
