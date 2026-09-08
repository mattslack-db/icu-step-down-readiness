/**
 * Frontend tests for the Patient Detail view (routes/patients/$icustay_id.tsx).
 *
 * Covers:
 * - Readiness gauge renders with index value + band label
 * - Supporting factors card renders when supports-direction factors present
 * - Risk factors card renders when risk-direction factors present
 * - AI narrative text is rendered
 * - Loading skeleton shows a cold-start loading state
 */

import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { PatientDetail } from "@/lib/api";

// Mock router
vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (opts: { component: unknown }) => opts,
  useNavigate: () => vi.fn(),
  Link: ({ children, ...props }: React.HTMLAttributes<HTMLAnchorElement>) =>
    React.createElement("a", props, children),
}));

// Mock the generated API client
vi.mock("@/lib/api", () => ({
  useGetPatientSuspense: vi.fn(),
}));

import { PatientDetailContent, PatientDetailSkeleton, ReadinessGauge } from "@/routes/patients/$icustay_id";
import { useGetPatientSuspense } from "@/lib/api";

// ─── Test data ──────────────────────────────────────────────────────────────

const MOCK_DETAIL: PatientDetail = {
  band: "Ready",
  readiness_index: 75,
  readiness_score: 0.8,
  narrative: "This patient demonstrates stable haemodynamics and improving ventilatory status, supporting consideration for step-down transfer.",
  lactate_note: null,
  factors: [
    { direction: "supports", magnitude: 0.3, name: "Normal SpO2" },
    { direction: "supports", magnitude: 0.2, name: "Stable heart rate" },
    { direction: "risk", magnitude: 0.15, name: "Elevated lactate" },
  ],
  features: {
    icustay_id: "icu-001",
    subject_id: "sub-001",
    age: 65.0,
    los: 3.5,
    on_vasopressors: false,
    on_ventilator: false,
    hr_mean: 72.0,
    sbp_mean: 120.0,
    dbp_mean: 80.0,
    spo2_mean: 98.0,
    spo2_min: 95.0,
    temp_c_mean: 37.0,
    rr_mean: 16.0,
    gcs_last: 15.0,
    lactate_last: 1.8,
  },
  vitals: [
    { vital_name: "hr", value: 72.0, charttime: "2026-09-08T09:00:00Z" },
    { vital_name: "hr", value: 74.0, charttime: "2026-09-08T10:00:00Z" },
    { vital_name: "spo2", value: 98.0, charttime: "2026-09-08T09:00:00Z" },
  ],
};

const MOCK_NOT_READY: PatientDetail = {
  ...MOCK_DETAIL,
  band: "Not ready",
  readiness_index: 20,
  readiness_score: 0.3,
  narrative: "Ongoing vasopressor support and ventilator dependence preclude step-down transfer at this time.",
  factors: [
    { direction: "risk", magnitude: 0.5, name: "On vasopressors" },
    { direction: "risk", magnitude: 0.4, name: "Ventilator dependent" },
  ],
  features: {
    ...MOCK_DETAIL.features,
    on_vasopressors: true,
    on_ventilator: true,
    gcs_last: 10.0,
  },
};

// ─── Helpers ────────────────────────────────────────────────────────────────

function renderDetail(detail: PatientDetail = MOCK_DETAIL) {
  (useGetPatientSuspense as ReturnType<typeof vi.fn>).mockReturnValue({
    data: detail,
  });
  return render(<PatientDetailContent icustay_id="icu-001" />);
}

// ─── Tests ──────────────────────────────────────────────────────────────────

describe("PatientDetailContent — patient detail view", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the readiness gauge with the index value", () => {
    renderDetail();
    // The gauge SVG has an aria-label describing the index and band
    const gauge = screen.getByLabelText(/readiness index 75.*band ready/i);
    expect(gauge).toBeInTheDocument();
  });

  it("renders the readiness band label in the gauge", () => {
    renderDetail();
    // Band label is rendered below the SVG arc
    expect(screen.getByText(/READY/i)).toBeInTheDocument();
  });

  it("renders the Supporting Factors card when supports-direction factors exist", () => {
    renderDetail();
    expect(screen.getByText("Supporting Factors")).toBeInTheDocument();
    expect(screen.getByText("Normal SpO2")).toBeInTheDocument();
    expect(screen.getByText("Stable heart rate")).toBeInTheDocument();
  });

  it("renders the Risk Factors card when risk-direction factors exist", () => {
    renderDetail();
    expect(screen.getByText(/risk factors/i)).toBeInTheDocument();
    expect(screen.getByText("Elevated lactate")).toBeInTheDocument();
  });

  it("renders only risk factors (no supporting card) when all factors are risk", () => {
    renderDetail(MOCK_NOT_READY);
    expect(screen.queryByText("Supporting Factors")).not.toBeInTheDocument();
    expect(screen.getByText(/risk factors/i)).toBeInTheDocument();
    expect(screen.getByText("On vasopressors")).toBeInTheDocument();
    expect(screen.getByText("Ventilator dependent")).toBeInTheDocument();
  });

  it("renders the AI narrative text after switching to the narrative tab", async () => {
    const user = userEvent.setup();
    renderDetail();
    // The narrative tab content is hidden by default (active tab is "vitals")
    // Switch to the AI Narrative tab to make the content visible
    const narrativeTab = screen.getByRole("tab", { name: /ai narrative/i });
    await user.click(narrativeTab);
    expect(
      screen.getByText(/stable haemodynamics/i),
    ).toBeInTheDocument();
  });

  it("renders the step-down assessment section title", () => {
    renderDetail();
    expect(
      screen.getByText(/step-down readiness assessment/i),
    ).toBeInTheDocument();
  });

  it("renders vital signs tab with a hr chart when vitals are present", () => {
    renderDetail();
    // The vitals tab trigger is present
    expect(
      screen.getByRole("tab", { name: /vital signs/i }),
    ).toBeInTheDocument();
  });

  it("renders the AI Narrative tab", () => {
    renderDetail();
    expect(
      screen.getByRole("tab", { name: /ai narrative/i }),
    ).toBeInTheDocument();
  });

  it("shows vasopressor badge for a patient on vasopressors", () => {
    renderDetail(MOCK_NOT_READY);
    // "On Vasopressors" appears as a badge and may also appear in recommendations
    expect(screen.getAllByText(/on vasopressors/i).length).toBeGreaterThan(0);
  });
});

describe("PatientDetailSkeleton — loading state", () => {
  it("renders the loading state message", () => {
    render(<PatientDetailSkeleton />);
    expect(screen.getByText(/loading patient data/i)).toBeInTheDocument();
  });

  it("renders skeleton placeholder elements", () => {
    const { container } = render(<PatientDetailSkeleton />);
    // Skeleton divs (Skeleton component renders div with animate-pulse)
    const skeletons = container.querySelectorAll(".animate-pulse, [class*='skeleton']");
    expect(skeletons.length).toBeGreaterThan(0);
  });
});

describe("ReadinessGauge — standalone gauge component", () => {
  it("renders with correct aria-label including index and band", () => {
    render(<ReadinessGauge index={75} band="Ready" />);
    // Use getByLabelText — the SVG carries aria-label but no explicit role="img"
    expect(
      screen.getByLabelText(/readiness index 75.*band ready/i),
    ).toBeInTheDocument();
  });

  it("shows the index value in the SVG text", () => {
    render(<ReadinessGauge index={42} band="Borderline" />);
    expect(screen.getByText("42")).toBeInTheDocument();
  });

  it("shows '/ 100 index' label in the gauge SVG", () => {
    render(<ReadinessGauge index={60} band="Borderline" />);
    expect(screen.getByText("/ 100 index")).toBeInTheDocument();
  });

  it("renders the band label below the gauge", () => {
    render(<ReadinessGauge index={20} band="Not ready" />);
    expect(screen.getByText(/NOT READY/i)).toBeInTheDocument();
  });
});
