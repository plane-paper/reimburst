"use client";

import { type ReactNode } from "react";

/** The standalone demo has no identity-provider or API dependency. */
export function AuthGate({ children }: { children: ReactNode }) {
  return <>{children}</>;
}

/** Compatibility helper for the API-backed screens kept in the repository. */
export function useAuthenticatedUser() {
  return { id: 1, email: "richard@demo.local", role: "admin" as "individual" | "employee" | "approver" | "admin", org_id: 1 };
}
