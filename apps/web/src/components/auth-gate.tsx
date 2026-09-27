"use client";

import { createContext, FormEvent, ReactNode, useContext, useEffect, useState } from "react";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export type AuthUser = { id: number; email: string; role: "individual" | "employee" | "approver" | "admin"; org_id: number | null };
const AuthContext = createContext<AuthUser | null>(null);

export function useAuthenticatedUser() {
  const user = useContext(AuthContext);
  if (!user) throw new Error("Authenticated user context is unavailable");
  return user;
}

export function AuthGate({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = window.localStorage.getItem("reimburst.access_token");
    if (!token) { setLoading(false); return; }
    void fetch(`${apiBaseUrl}/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (response) => response.ok ? setUser(await response.json() as AuthUser) : window.localStorage.removeItem("reimburst.access_token"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <main className="grid min-h-screen place-items-center text-sm text-slate-500">Loading your workspace…</main>;
  if (!user) return <SignIn onAuthenticated={setUser} />;
  return <AuthContext.Provider value={user}>{children}</AuthContext.Provider>;
}

function SignIn({ onAuthenticated }: { onAuthenticated: (user: AuthUser) => void }) {
  const [register, setRegister] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/auth/${register ? "register" : "login"}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password }),
      });
      const data = await response.json() as AuthUser & { access_token?: string; detail?: string };
      if (!response.ok || !data.access_token) throw new Error(data.detail ?? "Could not authenticate");
      window.localStorage.setItem("reimburst.access_token", data.access_token); onAuthenticated(data);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not authenticate"); }
    finally { setBusy(false); }
  }
  return <main className="grid min-h-screen place-items-center bg-[#f8faff] p-5 text-[#14213d]"><form className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-7 shadow-sm" onSubmit={submit}><h1 className="text-2xl font-bold">{register ? "Create your account" : "Sign in to Reimburst"}</h1><p className="mt-2 text-sm text-slate-500">{register ? "New accounts start in individual mode." : "Use the account assigned to you."}</p>{error && <p className="mt-5 rounded bg-red-50 p-3 text-sm text-red-700" role="alert">{error}</p>}<label className="mt-6 block text-sm font-medium">Email<input autoComplete="email" className="mt-1 w-full rounded border border-slate-300 p-2" onChange={(event) => setEmail(event.target.value)} required type="email" value={email} /></label><label className="mt-4 block text-sm font-medium">Password<input autoComplete={register ? "new-password" : "current-password"} className="mt-1 w-full rounded border border-slate-300 p-2" minLength={12} onChange={(event) => setPassword(event.target.value)} required type="password" value={password} /></label><button className="mt-6 w-full rounded bg-blue-600 px-4 py-2.5 font-semibold text-white disabled:bg-slate-300" disabled={busy} type="submit">{busy ? "Please wait…" : register ? "Create account" : "Sign in"}</button><button className="mt-4 w-full text-sm font-medium text-blue-700" onClick={() => { setRegister(!register); setError(null); }} type="button">{register ? "Already have an account? Sign in" : "Need an account? Register"}</button></form></main>;
}
