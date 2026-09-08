import { Suspense, useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { QueryErrorResetBoundary } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";
import { useGetCensusSuspense } from "@/lib/api";
import type { CensusPatient } from "@/lib/api";
import selector from "@/lib/selector";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { RefreshCw, ChevronRight, Loader2 } from "lucide-react";

// ─── Constants ─────────────────────────────────────────────────────────────
const ICU_BED_CAPACITY = 30;

// ─── Helpers ───────────────────────────────────────────────────────────────
type SortField = "readiness_index" | "los" | "age";

function bandEmoji(band: string): string {
  if (band === "Ready") return "🟢";
  if (band === "Borderline") return "🟡";
  return "🔴";
}

function sortPatients(
  patients: CensusPatient[],
  field: SortField,
): CensusPatient[] {
  return [...patients].sort((a, b) => {
    if (field === "readiness_index") return b.readiness_index - a.readiness_index;
    if (field === "los") return b.los - a.los;
    if (field === "age") return b.age - a.age;
    return 0;
  });
}

// ─── Census Content ────────────────────────────────────────────────────────
function CensusDashboard() {
  const { data } = useGetCensusSuspense(selector());
  const navigate = useNavigate();
  const [sortField, setSortField] = useState<SortField>("readiness_index");
  const [refreshing, setRefreshing] = useState(false);

  const ready = data.patients.filter((p) => p.band === "Ready").length;
  const borderline = data.patients.filter((p) => p.band === "Borderline").length;
  const notReady = data.patients.filter((p) => p.band === "Not ready").length;
  const utilization = Math.round((data.total / ICU_BED_CAPACITY) * 100);

  const sorted = sortPatients(data.patients, sortField);

  function handleRefresh() {
    setRefreshing(true);
    window.location.reload();
  }

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">ICU Census Dashboard</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            {data.total} patients &middot; updated{" "}
            {new Date(data.generated_at).toLocaleTimeString()}
          </p>
          <p className="text-xs text-muted-foreground mt-0.5 italic max-w-xl">
            Readiness index is a relative prioritization tool — decision
            support only. Not a discharge probability. Clinical judgment
            required.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={handleRefresh}
          disabled={refreshing}
        >
          {refreshing ? (
            <Loader2 className="h-4 w-4 animate-spin mr-1" />
          ) : (
            <RefreshCw className="h-4 w-4 mr-1" />
          )}
          Refresh
        </Button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-1 pt-4">
            <CardTitle className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Total ICU
            </CardTitle>
          </CardHeader>
          <CardContent className="pb-4">
            <div className="text-3xl font-bold">{data.total}</div>
          </CardContent>
        </Card>
        <Card className="border-green-500/30">
          <CardHeader className="pb-1 pt-4">
            <CardTitle className="text-xs font-medium text-green-600 dark:text-green-400 uppercase tracking-wide">
              🟢 Ready
            </CardTitle>
          </CardHeader>
          <CardContent className="pb-4">
            <div className="text-3xl font-bold text-green-600 dark:text-green-400">
              {ready}
            </div>
          </CardContent>
        </Card>
        <Card className="border-yellow-500/30">
          <CardHeader className="pb-1 pt-4">
            <CardTitle className="text-xs font-medium text-yellow-600 dark:text-yellow-400 uppercase tracking-wide">
              🟡 Borderline
            </CardTitle>
          </CardHeader>
          <CardContent className="pb-4">
            <div className="text-3xl font-bold text-yellow-600 dark:text-yellow-400">
              {borderline}
            </div>
          </CardContent>
        </Card>
        <Card className="border-red-500/30">
          <CardHeader className="pb-1 pt-4">
            <CardTitle className="text-xs font-medium text-red-600 dark:text-red-400 uppercase tracking-wide">
              🔴 Not Ready
            </CardTitle>
          </CardHeader>
          <CardContent className="pb-4">
            <div className="text-3xl font-bold text-red-600 dark:text-red-400">
              {notReady}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Bed utilization */}
      <Card>
        <CardHeader className="pb-2 pt-4">
          <CardTitle className="text-sm font-medium">
            ICU Bed Utilization
          </CardTitle>
        </CardHeader>
        <CardContent className="pb-4 space-y-1.5">
          <Progress value={utilization} className="h-3" />
          <p className="text-xs text-muted-foreground">
            {utilization}% — {data.total} / {ICU_BED_CAPACITY} beds occupied
          </p>
        </CardContent>
      </Card>

      {/* Patient table */}
      <Card>
        <CardHeader className="pb-2 pt-4">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <CardTitle className="text-base">Patient Ranking</CardTitle>
            <div className="flex items-center gap-1.5 text-xs">
              <span className="text-muted-foreground">Sort by:</span>
              {(
                [
                  ["readiness_index", "Readiness Index"],
                  ["los", "LOS"],
                  ["age", "Age"],
                ] as [SortField, string][]
              ).map(([field, label]) => (
                <Button
                  key={field}
                  variant={sortField === field ? "default" : "outline"}
                  size="sm"
                  className="h-7 text-xs"
                  onClick={() => setSortField(field)}
                >
                  {label}
                </Button>
              ))}
            </div>
          </div>
        </CardHeader>
        <CardContent className="pb-2 overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-12">Rank</TableHead>
                <TableHead>Patient</TableHead>
                <TableHead className="text-right">Age</TableHead>
                <TableHead className="text-right">LOS (d)</TableHead>
                <TableHead>
                  Readiness Index
                  <span className="text-muted-foreground text-xs font-normal ml-1">
                    (0–100, relative)
                  </span>
                </TableHead>
                <TableHead>Key Factors</TableHead>
                <TableHead className="w-8"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sorted.map((patient, idx) => (
                <TableRow
                  key={patient.icustay_id}
                  className="cursor-pointer hover:bg-muted/50 transition-colors"
                  onClick={() =>
                    navigate({
                      to: "/patients/$icustay_id",
                      params: { icustay_id: patient.icustay_id },
                    })
                  }
                >
                  <TableCell className="font-medium text-base">
                    {bandEmoji(patient.band)}{" "}
                    <span className="text-sm">{idx + 1}</span>
                  </TableCell>
                  <TableCell>
                    <div className="font-medium text-sm">#{patient.subject_id}</div>
                    <div className="text-xs text-muted-foreground">
                      ICU {patient.icustay_id}
                    </div>
                  </TableCell>
                  <TableCell className="text-right text-sm">
                    {Math.round(patient.age)}
                  </TableCell>
                  <TableCell className="text-right text-sm">
                    {patient.los.toFixed(1)}
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <span className="text-xl font-bold">
                        {patient.readiness_index}
                      </span>
                      <Badge
                        className={`text-xs ${
                          patient.band === "Ready"
                            ? "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300 border-green-300"
                            : patient.band === "Borderline"
                              ? "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300 border-yellow-300"
                              : "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300 border-red-300"
                        } border`}
                        variant="outline"
                      >
                        {patient.band}
                      </Badge>
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-col gap-0.5">
                      {patient.top_factors.slice(0, 2).map((f, i) => (
                        <span
                          key={i}
                          className={`text-xs ${
                            f.direction === "supports"
                              ? "text-green-600 dark:text-green-400"
                              : "text-red-600 dark:text-red-400"
                          }`}
                        >
                          {f.direction === "supports" ? "✓" : "✗"} {f.name}
                        </span>
                      ))}
                    </div>
                  </TableCell>
                  <TableCell>
                    <ChevronRight className="h-4 w-4 text-muted-foreground" />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Disclaimer */}
      <p className="text-xs text-muted-foreground text-center pb-4">
        MIMIC-III de-identified research data &middot; For decision support
        only &middot; Not for direct clinical use
      </p>
    </div>
  );
}

// ─── Skeleton ──────────────────────────────────────────────────────────────
function CensusSkeleton() {
  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">
      <div className="space-y-2">
        <Skeleton className="h-7 w-56" />
        <Skeleton className="h-4 w-96" />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <Skeleton key={i} className="h-24" />
        ))}
      </div>
      <Skeleton className="h-20 w-full" />
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Skeleton className="h-5 w-32" />
          <div className="flex gap-1">
            <Skeleton className="h-7 w-24" />
            <Skeleton className="h-7 w-16" />
            <Skeleton className="h-7 w-16" />
          </div>
        </div>
        {[1, 2, 3, 4, 5].map((i) => (
          <Skeleton key={i} className="h-14 w-full" />
        ))}
      </div>
      <div className="text-center text-sm text-muted-foreground animate-pulse">
        <Loader2 className="h-4 w-4 animate-spin inline mr-2" />
        Computing readiness scores for all ICU patients… (AI model may need
        ~30s to warm up)
      </div>
    </div>
  );
}

// ─── Exports for testing ───────────────────────────────────────────────────
export { CensusDashboard };

// ─── Route ─────────────────────────────────────────────────────────────────
export const Route = createFileRoute("/")({
  component: () => (
    <QueryErrorResetBoundary>
      {({ reset }) => (
        <ErrorBoundary
          onReset={reset}
          fallbackRender={({ error, resetErrorBoundary }) => (
            <div className="max-w-7xl mx-auto px-4 py-6">
              <Card className="border-destructive">
                <CardContent className="pt-6 space-y-3">
                  <p className="text-destructive font-medium">
                    Failed to load census data
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
          <Suspense fallback={<CensusSkeleton />}>
            <CensusDashboard />
          </Suspense>
        </ErrorBoundary>
      )}
    </QueryErrorResetBoundary>
  ),
});
