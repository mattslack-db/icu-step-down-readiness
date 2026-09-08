import { Suspense } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { QueryErrorResetBoundary } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";
import { useGetAnalyticsSuspense } from "@/lib/api";
import type { AnalyticsResponse } from "@/lib/api";
import selector from "@/lib/selector";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Progress } from "@/components/ui/progress";
import { Loader2, AlertTriangle } from "lucide-react";

// ─── Feature Importance Chart ─────────────────────────────────────────────
function FeatureImportanceChart({
  items,
}: {
  items: AnalyticsResponse["feature_importance"];
}) {
  const top10 = items.slice(0, 10);
  const maxVal = Math.max(...top10.map((i) => i.importance), 0.001);

  return (
    <div className="space-y-2.5">
      {top10.map((item) => (
        <div key={item.feature} className="space-y-1">
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground truncate max-w-xs">
              {item.feature}
            </span>
            <span className="font-medium ml-2 shrink-0">
              {(item.importance * 100).toFixed(1)}%
            </span>
          </div>
          <Progress
            value={(item.importance / maxVal) * 100}
            className="h-2"
          />
        </div>
      ))}
    </div>
  );
}

// ─── Band Distribution ────────────────────────────────────────────────────
function BandDistributionChart({
  bands,
}: {
  bands: AnalyticsResponse["band_distribution"];
  total?: number;
}) {
  const order = ["Ready", "Borderline", "Not ready"];
  const sorted = [...bands].sort(
    (a, b) => order.indexOf(a.band) - order.indexOf(b.band),
  );

  return (
    <div className="space-y-3">
      {sorted.map((b) => {
        const colorClass =
          b.band === "Ready"
            ? "bg-green-500"
            : b.band === "Borderline"
              ? "bg-yellow-500"
              : "bg-red-500";
        const textClass =
          b.band === "Ready"
            ? "text-green-600 dark:text-green-400"
            : b.band === "Borderline"
              ? "text-yellow-600 dark:text-yellow-400"
              : "text-red-600 dark:text-red-400";

        return (
          <div key={b.band} className="space-y-1">
            <div className="flex items-center justify-between text-sm">
              <span className={`font-medium ${textClass}`}>{b.band}</span>
              <span className="text-muted-foreground">
                {b.count} patients ({b.pct.toFixed(0)}%)
              </span>
            </div>
            <div className="h-4 bg-muted rounded-full overflow-hidden">
              <div
                className={`h-full ${colorClass} rounded-full transition-all`}
                style={{ width: `${b.pct}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── Analytics Content ────────────────────────────────────────────────────
function AnalyticsContent() {
  const { data } = useGetAnalyticsSuspense(selector());

  const losByBand = data.avg_los_by_band;

  return (
    <div className="max-w-5xl mx-auto px-4 py-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold">Analytics & Model Performance</h1>
        <p className="text-xs text-muted-foreground mt-0.5">
          Census snapshot at {new Date(data.generated_at).toLocaleTimeString()}
          &nbsp;&middot;&nbsp;{data.total_census} patients
        </p>
      </div>

      {/* Model performance — honest framing */}
      <Card className="border-amber-500/30">
        <CardHeader className="pb-2 pt-4">
          <div className="flex items-start gap-2">
            <AlertTriangle className="h-4 w-4 text-amber-500 mt-0.5 shrink-0" />
            <CardTitle className="text-sm font-medium">
              Model Performance — Honest Assessment
            </CardTitle>
          </div>
        </CardHeader>
        <CardContent className="pb-4 space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="border rounded-lg p-3 text-center">
              <p className="text-xs text-muted-foreground">AUC-ROC</p>
              <p className="text-2xl font-bold">0.66</p>
              <p className="text-xs text-muted-foreground">
                Modest discrimination
              </p>
            </div>
            <div className="border rounded-lg p-3 text-center">
              <p className="text-xs text-muted-foreground">
                Precision-Recall AUC
              </p>
              <p className="text-2xl font-bold text-amber-600">0.98</p>
              <p className="text-xs text-amber-600">
                Misleading: driven by class imbalance
              </p>
            </div>
            <div className="border rounded-lg p-3 text-center">
              <p className="text-xs text-muted-foreground">
                Bounce-back PR-AUC
              </p>
              <p className="text-2xl font-bold text-red-600">~0.06</p>
              <p className="text-xs text-red-600">
                Poor readmission prediction
              </p>
            </div>
            <div className="border rounded-lg p-3 text-center">
              <p className="text-xs text-muted-foreground">Output type</p>
              <p className="text-lg font-bold">Relative</p>
              <p className="text-xs text-muted-foreground">
                Index, not probability
              </p>
            </div>
          </div>

          <div className="text-xs text-muted-foreground space-y-1 border-t pt-3">
            <p>
              <strong>Important:</strong> The 0.98 PR-AUC is a statistical
              artifact of severe class imbalance (few positive outcomes in
              MIMIC-III) and does not indicate the model is highly accurate.
            </p>
            <p>
              The AUC of 0.66 provides modest discrimination — better than
              random (0.5) but well below high-confidence thresholds.
            </p>
            <p>
              The bounce-back PR-AUC of ~0.06 indicates the model has limited
              ability to predict which transferred patients will be
              re-admitted. Do not use for definitive transfer decisions.
            </p>
            <p className="font-medium text-foreground/70">
              This tool is decision support. All transfers must be clinically
              validated.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Band distribution + LOS */}
      <div className="grid md:grid-cols-2 gap-6">
        <Card>
          <CardHeader className="pb-2 pt-4">
            <CardTitle className="text-sm font-medium">
              Current Readiness Band Distribution
            </CardTitle>
          </CardHeader>
          <CardContent className="pb-4">
            <BandDistributionChart
              bands={data.band_distribution}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2 pt-4">
            <CardTitle className="text-sm font-medium">
              Average LOS by Band
            </CardTitle>
          </CardHeader>
          <CardContent className="pb-4 space-y-3">
            {Object.entries(losByBand)
              .sort(([, a], [, b]) => b - a)
              .map(([band, avgLos]) => (
                <div
                  key={band}
                  className="flex items-center justify-between text-sm border-b pb-2 last:border-0"
                >
                  <span className="text-muted-foreground">{band}</span>
                  <span className="font-bold">{avgLos.toFixed(2)} days</span>
                </div>
              ))}
            <p className="text-xs text-muted-foreground italic">
              Higher LOS in "Not ready" band may reflect severity, not model
              quality.
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Vent / Vasopressor rates */}
      <div className="grid grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-2 pt-4">
            <CardTitle className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Ventilated
            </CardTitle>
          </CardHeader>
          <CardContent className="pb-4">
            <div className="text-3xl font-bold">
              {(data.vent_rate * 100).toFixed(0)}%
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              {Math.round(data.vent_rate * data.total_census)} /{" "}
              {data.total_census} patients on ventilator
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2 pt-4">
            <CardTitle className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Vasopressors
            </CardTitle>
          </CardHeader>
          <CardContent className="pb-4">
            <div className="text-3xl font-bold">
              {(data.vasopressor_rate * 100).toFixed(0)}%
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              {Math.round(data.vasopressor_rate * data.total_census)} /{" "}
              {data.total_census} patients on vasopressors
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Feature Importance */}
      <Card>
        <CardHeader className="pb-2 pt-4">
          <CardTitle className="text-sm font-medium">
            Global Feature Importance
          </CardTitle>
          <p className="text-xs text-muted-foreground">
            Mean |SHAP| from v2 model evaluation — reflects model weights, not
            per-patient factors. Top 10 shown.
          </p>
        </CardHeader>
        <CardContent className="pb-4">
          <FeatureImportanceChart items={data.feature_importance} />
        </CardContent>
      </Card>

      <p className="text-xs text-muted-foreground text-center pb-4">
        MIMIC-III de-identified research data &middot; Model v2 &middot;
        AUC-ROC 0.66 &middot; For decision support only
      </p>
    </div>
  );
}

// ─── Skeleton ──────────────────────────────────────────────────────────────
function AnalyticsSkeleton() {
  return (
    <div className="max-w-5xl mx-auto px-4 py-6 space-y-6">
      <Skeleton className="h-7 w-64" />
      <Skeleton className="h-48 w-full" />
      <div className="grid md:grid-cols-2 gap-6">
        <Skeleton className="h-40" />
        <Skeleton className="h-40" />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
      </div>
      <Skeleton className="h-64" />
      <div className="text-center text-sm text-muted-foreground animate-pulse flex items-center justify-center gap-2">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading analytics data…
      </div>
    </div>
  );
}

// ─── Exports for testing ───────────────────────────────────────────────────
export { AnalyticsContent };

// ─── Route ─────────────────────────────────────────────────────────────────
export const Route = createFileRoute("/analytics")({
  component: () => (
    <QueryErrorResetBoundary>
      {({ reset }) => (
        <ErrorBoundary
          onReset={reset}
          fallbackRender={({ error, resetErrorBoundary }) => (
            <div className="max-w-5xl mx-auto px-4 py-6">
              <Card className="border-destructive">
                <CardContent className="pt-6 space-y-3">
                  <p className="text-destructive font-medium">
                    Failed to load analytics
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
          <Suspense fallback={<AnalyticsSkeleton />}>
            <AnalyticsContent />
          </Suspense>
        </ErrorBoundary>
      )}
    </QueryErrorResetBoundary>
  ),
});
