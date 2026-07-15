"use client";

import { useEffect, useState } from "react";
import { createApiClient } from "@reimburse/contract";

const apiClient = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

type State =
  | { status: "pending" }
  | { status: "success"; value: string }
  | { status: "error"; message: string };

export function HealthCheck() {
  const [state, setState] = useState<State>({ status: "pending" });

  useEffect(() => {
    let cancelled = false;

    apiClient
      .GET("/health")
      .then(({ data, error }) => {
        if (cancelled) return;
        if (error) {
          setState({ status: "error", message: "API returned an error" });
          return;
        }
        setState({ status: "success", value: data.status });
      })
      .catch(() => {
        if (!cancelled) {
          setState({ status: "error", message: "Could not reach the API" });
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  if (state.status === "pending") {
    return <p className="text-zinc-500">Checking API…</p>;
  }

  if (state.status === "error") {
    return <p className="text-red-600">API health check failed: {state.message}</p>;
  }

  return (
    <p className="text-green-600">
      API health: <code>{state.value}</code>
    </p>
  );
}
