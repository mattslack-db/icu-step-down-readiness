import { Suspense } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { QueryErrorResetBoundary } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";
import { useGetPatientSuspense } from "@/lib/api";
import type { PatientDetail, VitalPoint } from "@/lib/api";
import selector from "@/lib/selector";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ArrowLeft, Loader2, AlertTriangle, CheckCircle2 } from "lucide-react";

// ─── Helpers ───────────────────────────────────────────────────────────────
function bandTextClass(band: string): string {
  if (band === "Ready") return "text-green-600 dark:text-green-400";
  if (band === "Borderline") return "text-yellow-600 dark:text-yellow-400";
  return "text-red-600 dark:text-red-400";
}

function bandEmoji(band: string): string {
  if (band === "Ready") return "🟢";
  if (band === "Borderline") return "🟡";
  return "🔴";
}

// ─── Readiness Gauge ───────────────────────────────────────────────────────
function ReadinessGauge({
  index,
  band,
}: {
  index: number;
  band: string;
}) {
  const W = 220, H = 130;
  const cx = W / 2, cy = 110;
  const r = 90;

  const bandStroke =
    band === "Ready"
      ? "#22c55e"
      : band === "Borderline"
        ? "#eab308"
        : "#ef4444";

  // Arc from 180° to 0° (left to right = 0 to 100)
  const startRad = Math.PI;
  const endRad = Math.PI - (index / 100) * Math.PI;

  const x1 = cx + r * Math.cos(startRad);
  const y1 = cy + r * Math.sin(startRad);
  const x2 = cx + r * Math.cos(endRad);
  const y2 = cy + r * Math.sin(endRad);
  const largeArc = index > 50 ? 1 : 0;
  const sweep = 0; // counter-clockwise

  return (
    <div className="flex flex-col items-center gap-2">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-52"
        aria-label={`Readiness index ${index} out of 100, band ${band}`}
      >
        {/* Track */}
        <path
          d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
          fill="none"
          stroke="currentColor"
          strokeOpacity={0.12}
          strokeWidth={14}
          strokeLinecap="round"
        />
        {/* Filled arc */}
        {index > 0 && (
          <path
            d={`M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} ${sweep} ${x2} ${y2}`}
            fill="none"
            stroke={bandStroke}
            strokeWidth={14}
            strokeLinecap="round"
          />
        )}
        {/* Index label */}
        <text
          x={cx}
          y={cy - 10}
          textAnchor="middle"
          fontSize={38}
          fontWeight={700}
          fill="currentColor"
        >
          {index}
        </text>
        <text
          x={cx}
          y={cy + 8}
          textAnchor="middle"
          fontSize={11}
          fill="currentColor"
          opacity={0.55}
        >
          / 100 index
        </text>
        {/* Min/Max labels */}
        <text x={8} y={cy + 4} fontSize={9} fill="currentColor" opacity={0.4}>
          0
        </text>
        <text
          x={W - 14}
          y={cy + 4}
          fontSize={9}
          fill="currentColor"
          opacity={0.4}
        >
          100
        </text>
      </svg>

      <div className="text-center space-y-0.5">
        <p className={`text-xl font-bold ${bandTextClass(band)}`}>
          {bandEmoji(band)} {band.toUpperCase()}
        </p>
        <p className="text-xs text-muted-foreground italic max-w-xs">
          Relative prioritization index — not a discharge probability.
          Clinical judgment required.
        </p>
      </div>
    </div>
  );
}

// ─── Vitals Chart ──────────────────────────────────────────────────────────
const VITAL_CONFIG: Record<
  string,
  { label: string; unit: string; color: string }
> = {
  hr: { label: "Heart Rate", unit: "bpm", color: "#f97316" },
  sbp: { label: "Systolic BP", unit: "mmHg", color: "#3b82f6" },
  dbp: { label: "Diastolic BP", unit: "mmHg", color: "#6366f1" },
  spo2: { label: "SpO₂", unit: "%", color: "#10b981" },
  temp: { label: "Temperature", unit: "°C", color: "#ec4899" },
  rr: { label: "Resp. Rate", unit: "/min", color: "#8b5cf6" },
  gcs: { label: "GCS", unit: "", color: "#14b8a6" },
};

function MiniVitalsChart({
  vitals,
  vitalName,
}: {
  vitals: VitalPoint[];
  vitalName: string;
}) {
  const cfg = VITAL_CONFIG[vitalName] ?? {
    label: vitalName,
    unit: "",
    color: "#6b7280",
  };
  const points = vitals
    .filter((v) => v.vital_name === vitalName)
    .sort(
      (a, b) => new Date(a.charttime).getTime() - new Date(b.charttime).getTime(),
    );

  if (points.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">No {cfg.label} data</p>
    );
  }

  const vals = points.map((p) => p.value);
  const minV = Math.min(...vals);
  const maxV = Math.max(...vals);
  const range = maxV - minV || 1;
  const W = 400,
    H = 70,
    PAD = 6;
  const xS = (i: number) =>
    PAD + (i / Math.max(points.length - 1, 1)) * (W - 2 * PAD);
  const yS = (v: number) =>
    H - PAD - ((v - minV) / range) * (H - 2 * PAD);
  const pathD = points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${xS(i).toFixed(1)} ${yS(p.value).toFixed(1)}`)
    .join(" ");

  const latest = vals[vals.length - 1];

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium">{cfg.label}</span>
        <span className="text-muted-foreground">
          Latest:{" "}
          <span className="font-semibold" style={{ color: cfg.color }}>
            {latest.toFixed(1)}
          </span>{" "}
          {cfg.unit}
        </span>
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        style={{ height: 60 }}
        role="img"
        aria-label={`${cfg.label} trend`}
      >
        <path
          d={pathD}
          fill="none"
          stroke={cfg.color}
          strokeWidth={2}
          strokeLinejoin="round"
        />
        {points.length <= 40 &&
          points.map((p, i) => (
            <circle
              key={i}
              cx={xS(i)}
              cy={yS(p.value)}
              r={2.5}
              fill={cfg.color}
            />
          ))}
        <text
          x={PAD}
          y={PAD + 4}
          fontSize={8}
          fill="currentColor"
          opacity={0.5}
        >
          {maxV.toFixed(0)}
        </text>
        <text
          x={PAD}
          y={H - 1}
          fontSize={8}
          fill="currentColor"
          opacity={0.5}
        >
          {minV.toFixed(0)}
        </text>
      </svg>
    </div>
  );
}

// ─── Recommended Actions ───────────────────────────────────────────────────
function RecommendedActions({ detail }: { detail: PatientDetail }) {
  const { band, features } = detail;

  const actions: string[] = [];

  if (band === "Ready") {
    actions.push("Consider step-down transfer within the next 4–8 hours");
    actions.push("Discuss transfer with clinical team and patient");
  } else if (band === "Borderline") {
    actions.push("Re-assess readiness in 4–6 hours");
    actions.push("Address modifiable risk factors before considering transfer");
  } else {
    actions.push("Continue current level of ICU care");
    actions.push("Address active physiological concerns before transfer");
  }

  if (features.on_vasopressors) {
    actions.push("Monitor vasopressor weaning progress");
  }
  if (features.on_ventilator) {
    actions.push("Ongoing ventilator management — not a step-down candidate while intubated");
  }
  if (features.gcs_last !== null && features.gcs_last < 14) {
    actions.push(`Neurological monitoring — GCS ${features.gcs_last.toFixed(0)}`);
  }
  if (detail.lactate_note) {
    actions.push(detail.lactate_note);
  }

  return (
    <div className="space-y-2">
      {actions.map((action, i) => (
        <div key={i} className="flex items-start gap-2 text-sm">
          <span className="mt-0.5 shrink-0">
            {i === 0 ? "📋" : i === 1 ? "🔔" : "💊"}
          </span>
          <span>{action}</span>
        </div>
      ))}
    </div>
  );
}

// ─── Main Detail View ──────────────────────────────────────────────────────
function PatientDetailContent({ icustay_id }: { icustay_id: string }) {
  const { data: detail } = useGetPatientSuspense({
    params: { icustay_id },
    ...selector(),
  });

  const supportingFactors = detail.factors.filter(
    (f) => f.direction === "supports",
  );
  const riskFactors = detail.factors.filter((f) => f.direction === "risk");

  const presentVitals = Object.keys(VITAL_CONFIG).filter((vn) =>
    detail.vitals.some((v) => v.vital_name === vn),
  );

  return (
    <div className="max-w-5xl mx-auto px-4 py-6 space-y-6">
      {/* Back link */}
      <Link
        to="/"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Census
      </Link>

      {/* Patient header */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold">
            Patient #{detail.features.subject_id}
          </h1>
          <p className="text-sm text-muted-foreground">
            ICU Stay {icustay_id} &middot; Age{" "}
            {Math.round(detail.features.age)} &middot; LOS{" "}
            {detail.features.los.toFixed(1)} days
          </p>
          {(detail.features.on_vasopressors ||
            detail.features.on_ventilator) && (
            <div className="flex gap-2 mt-1">
              {detail.features.on_vasopressors && (
                <Badge variant="destructive" className="text-xs">
                  On Vasopressors
                </Badge>
              )}
              {detail.features.on_ventilator && (
                <Badge variant="destructive" className="text-xs">
                  On Ventilator
                </Badge>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Top row: gauge + factors */}
      <div className="grid md:grid-cols-2 gap-6">
        {/* Readiness gauge */}
        <Card>
          <CardHeader className="pb-2 pt-4">
            <CardTitle className="text-sm font-medium">
              Step-Down Readiness Assessment
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col items-center pb-4">
            <ReadinessGauge
              index={detail.readiness_index}
              band={detail.band}
            />
          </CardContent>
        </Card>

        {/* Factors */}
        <div className="space-y-4">
          {supportingFactors.length > 0 && (
            <Card className="border-green-500/30">
              <CardHeader className="pb-2 pt-4">
                <CardTitle className="text-sm font-medium text-green-600 dark:text-green-400">
                  Supporting Factors
                </CardTitle>
              </CardHeader>
              <CardContent className="pb-4 space-y-2">
                {supportingFactors.map((f, i) => (
                  <div key={i} className="flex items-start gap-2 text-sm">
                    <CheckCircle2 className="h-4 w-4 text-green-600 dark:text-green-400 mt-0.5 shrink-0" />
                    <span>{f.name}</span>
                    <span className="text-xs text-muted-foreground ml-auto">
                      {(f.magnitude * 100).toFixed(0)}
                    </span>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {riskFactors.length > 0 && (
            <Card className="border-red-500/30">
              <CardHeader className="pb-2 pt-4">
                <CardTitle className="text-sm font-medium text-red-600 dark:text-red-400">
                  Risk Factors / Cautions
                </CardTitle>
              </CardHeader>
              <CardContent className="pb-4 space-y-2">
                {riskFactors.map((f, i) => (
                  <div key={i} className="flex items-start gap-2 text-sm">
                    <AlertTriangle className="h-4 w-4 text-red-600 dark:text-red-400 mt-0.5 shrink-0" />
                    <span>{f.name}</span>
                    <span className="text-xs text-muted-foreground ml-auto">
                      {(f.magnitude * 100).toFixed(0)}
                    </span>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </div>
      </div>

      {/* Tabs: Vitals | Gen AI Narrative | Features */}
      <Card>
        <Tabs defaultValue="vitals">
          <CardHeader className="pb-0 pt-4">
            <TabsList className="w-full justify-start h-auto p-0 bg-transparent gap-1 flex-wrap">
              <TabsTrigger value="vitals" className="text-xs">
                Vital Signs
              </TabsTrigger>
              <TabsTrigger value="narrative" className="text-xs">
                AI Narrative
              </TabsTrigger>
              <TabsTrigger value="features" className="text-xs">
                Clinical Data
              </TabsTrigger>
              <TabsTrigger value="actions" className="text-xs">
                Recommendations
              </TabsTrigger>
            </TabsList>
          </CardHeader>
          <CardContent className="pt-4 pb-4">
            {/* Vital Signs */}
            <TabsContent value="vitals" className="mt-0 space-y-4">
              {presentVitals.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No vital signs data recorded for this stay.
                </p>
              ) : (
                <div className="grid md:grid-cols-2 gap-4">
                  {presentVitals.map((vn) => (
                    <div key={vn} className="border rounded-lg p-3">
                      <MiniVitalsChart vitals={detail.vitals} vitalName={vn} />
                    </div>
                  ))}
                </div>
              )}
            </TabsContent>

            {/* AI Narrative */}
            <TabsContent value="narrative" className="mt-0">
              <div className="space-y-3">
                <div className="flex items-center gap-2 text-xs text-muted-foreground border-b pb-2">
                  <span className="font-medium text-foreground">
                    Generated by LLaMA-3.3-70B
                  </span>
                  &middot; Clinical decision support only &middot; Verify
                  with clinical data
                </div>
                <p className="text-sm leading-relaxed whitespace-pre-wrap">
                  {detail.narrative}
                </p>
                {detail.lactate_note && (
                  <p className="text-xs text-amber-600 dark:text-amber-400 border border-amber-300 dark:border-amber-700 rounded px-3 py-2 bg-amber-50 dark:bg-amber-950/30">
                    ⚠️ {detail.lactate_note}
                  </p>
                )}
              </div>
            </TabsContent>

            {/* Clinical Data */}
            <TabsContent value="features" className="mt-0">
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
                {[
                  ["Heart Rate (mean)", detail.features.hr_mean, "bpm"],
                  ["SBP (mean)", detail.features.sbp_mean, "mmHg"],
                  ["DBP (mean)", detail.features.dbp_mean, "mmHg"],
                  ["SpO₂ (mean)", detail.features.spo2_mean, "%"],
                  ["SpO₂ (min)", detail.features.spo2_min, "%"],
                  ["Temperature (mean)", detail.features.temp_c_mean, "°C"],
                  ["Resp. Rate (mean)", detail.features.rr_mean, "/min"],
                  ["GCS (last)", detail.features.gcs_last, ""],
                  ["Lactate (last)", detail.features.lactate_last, "mmol/L"],
                  ["Age", detail.features.age, "years"],
                  ["LOS", detail.features.los, "days"],
                ].map(([label, val, unit]) => (
                  <div key={label as string} className="border rounded-lg p-2.5">
                    <p className="text-xs text-muted-foreground">{label}</p>
                    <p className="font-medium">
                      {val !== null && val !== undefined
                        ? (val as number).toFixed(1)
                        : "—"}{" "}
                      <span className="text-xs text-muted-foreground font-normal">
                        {unit}
                      </span>
                    </p>
                  </div>
                ))}
              </div>
            </TabsContent>

            {/* Recommendations */}
            <TabsContent value="actions" className="mt-0">
              <RecommendedActions detail={detail} />
            </TabsContent>
          </CardContent>
        </Tabs>
      </Card>

      <p className="text-xs text-muted-foreground text-center pb-4">
        MIMIC-III de-identified research data &middot; For decision support
        only &middot; Raw score: {detail.readiness_score.toFixed(3)} (not a
        probability)
      </p>
    </div>
  );
}

// ─── Loading Skeleton ──────────────────────────────────────────────────────
function PatientDetailSkeleton() {
  return (
    <div className="max-w-5xl mx-auto px-4 py-6 space-y-6">
      <Skeleton className="h-4 w-28" />
      <div className="space-y-2">
        <Skeleton className="h-7 w-48" />
        <Skeleton className="h-4 w-72" />
      </div>
      <div className="grid md:grid-cols-2 gap-6">
        <Skeleton className="h-56" />
        <div className="space-y-4">
          <Skeleton className="h-28" />
          <Skeleton className="h-28" />
        </div>
      </div>
      <Skeleton className="h-64" />
      <div className="text-center text-sm text-muted-foreground animate-pulse flex items-center justify-center gap-2">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading patient data… AI model may need ~30s to warm up on first
        request
      </div>
    </div>
  );
}

// ─── Route ─────────────────────────────────────────────────────────────────
export const Route = createFileRoute("/patients/$icustay_id")({
  component: function PatientDetailPage() {
    const { icustay_id } = Route.useParams();
    return (
      <QueryErrorResetBoundary>
        {({ reset }) => (
          <ErrorBoundary
            onReset={reset}
            fallbackRender={({ error, resetErrorBoundary }) => (
              <div className="max-w-5xl mx-auto px-4 py-6 space-y-4">
                <Link
                  to="/"
                  className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
                >
                  <ArrowLeft className="h-4 w-4" />
                  Back to Census
                </Link>
                <Card className="border-destructive">
                  <CardContent className="pt-6 space-y-3">
                    <p className="text-destructive font-medium">
                      Failed to load patient data
                    </p>
                    <p className="text-sm text-muted-foreground">
                      {(error as Error)?.message ?? "Unknown error"}
                    </p>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={resetErrorBoundary}
                    >
                      Try again
                    </Button>
                  </CardContent>
                </Card>
              </div>
            )}
          >
            <Suspense fallback={<PatientDetailSkeleton />}>
              <PatientDetailContent icustay_id={icustay_id} />
            </Suspense>
          </ErrorBoundary>
        )}
      </QueryErrorResetBoundary>
    );
  },
});
