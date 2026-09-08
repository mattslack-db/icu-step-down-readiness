import { ThemeProvider } from "@/components/apx/theme-provider";
import { ModeToggle } from "@/components/apx/mode-toggle";
import { QueryClient } from "@tanstack/react-query";
import {
  createRootRouteWithContext,
  Link,
  Outlet,
} from "@tanstack/react-router";
import { Toaster } from "sonner";
import { Activity } from "lucide-react";

export const Route = createRootRouteWithContext<{
  queryClient: QueryClient;
}>()({
  component: () => (
    <ThemeProvider defaultTheme="dark" storageKey="apx-ui-theme">
      <div className="min-h-screen bg-background flex flex-col">
        <header className="z-50 bg-background/80 backdrop-blur-sm border-b sticky top-0">
          <div className="h-16 flex items-center justify-between px-4 max-w-7xl mx-auto w-full">
            {/* Brand */}
            <div className="flex items-center gap-2">
              <Activity className="h-5 w-5 text-primary" />
              <span className="font-semibold text-sm">ICU Step-Down Readiness</span>
            </div>

            {/* Navigation */}
            <nav className="flex items-center gap-1">
              <Link
                to="/"
                className="px-3 py-1.5 rounded-md text-sm font-medium transition-colors [&.active]:bg-accent [&.active]:text-accent-foreground hover:bg-accent/50"
              >
                Census
              </Link>
              <Link
                to="/analytics"
                className="px-3 py-1.5 rounded-md text-sm font-medium transition-colors [&.active]:bg-accent [&.active]:text-accent-foreground hover:bg-accent/50"
              >
                Analytics
              </Link>
            </nav>

            <ModeToggle />
          </div>
        </header>

        <main className="flex-1">
          <Outlet />
        </main>
      </div>
      <Toaster richColors />
    </ThemeProvider>
  ),
});
