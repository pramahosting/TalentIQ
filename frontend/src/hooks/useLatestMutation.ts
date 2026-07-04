import { useMutationState } from "@tanstack/react-query";

/**
 * Reads the latest status/data/error of a mutation by its mutationKey,
 * sourced from TanStack Query's shared MutationCache (which lives on the
 * QueryClient at the app root and never unmounts).
 *
 * Why this exists: a mutation started with `useMutation()` normally reports
 * its result via local hook state (`isPending`, `data`, ...). That local
 * state disappears the moment the component that started it unmounts —
 * e.g. when the user navigates to a different page while a long-running
 * "Run Analysis" / "Generate JD" / "Search" request is still in flight.
 * The underlying network request itself is NOT cancelled by navigation
 * (it's a plain promise, not tied to the component), so it keeps running
 * and completes on the server regardless. This hook lets ANY mount of the
 * page (including a fresh one after navigating back) ask "what's the
 * latest state of the mutation with this key?" and pick up right where
 * the in-flight or completed request left off.
 *
 * Scope/limits: this survives in-app navigation (SPA route changes) for
 * as long as the browser tab stays open. It does NOT survive a full page
 * reload/refresh — the mutation cache is in-memory only. For results that
 * must survive a hard refresh too, they need to be persisted server-side
 * and re-fetched (which JD Creator, CandidateLens, JobHunter, MarketIntel,
 * and LinkExplore already do via their History/session lists).
 */
export function useLatestMutation<TData = unknown, TError = unknown>(
  mutationKey: unknown[]
): {
  status: "idle" | "pending" | "success" | "error";
  data: TData | undefined;
  error: TError | undefined;
  submittedAt: number | undefined;
} {
  const matches = useMutationState({
    filters: { mutationKey },
    select: (mutation) => ({
      status: mutation.state.status as "idle" | "pending" | "success" | "error",
      data: mutation.state.data as TData | undefined,
      error: mutation.state.error as TError | undefined,
      submittedAt: mutation.state.submittedAt,
    }),
  });

  if (matches.length === 0) {
    return { status: "idle", data: undefined, error: undefined, submittedAt: undefined };
  }
  return matches[matches.length - 1];
}
