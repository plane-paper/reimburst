"use client";

import { createApiClient, type components } from "@reimburse/contract";
import { createContext, FormEvent, ReactNode, useContext, useEffect, useState } from "react";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const api = createApiClient(apiBaseUrl);
export type AuthUser = { id: number; email: string; role: "individual" | "employee" | "approver" | "admin"; org_id: number | null };
type Notification = components["schemas"]["NotificationDetail"];
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
    if (!token) { void Promise.resolve().then(() => setLoading(false)); return; }
    void fetch(`${apiBaseUrl}/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (response) => response.ok ? setUser(await response.json() as AuthUser) : window.localStorage.removeItem("reimburst.access_token"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <main className="grid min-h-screen place-items-center text-sm text-slate-500">Loading your workspace…</main>;
  if (!user) return <SignIn onAuthenticated={setUser} />;
  const signOut = () => { window.localStorage.removeItem("reimburst.access_token"); setUser(null); };
  return <AuthContext.Provider value={user}><AuthenticatedTools onSignOut={signOut} />{children}</AuthContext.Provider>;
}

function AuthenticatedTools({ onSignOut }: { onSignOut: () => void }) {
  const user = useAuthenticatedUser();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [error, setError] = useState<string | null>(null);
  const unread = notifications.filter((notification) => notification.read_at === null).length;

  const load = async () => {
    const result = await api.GET("/notifications");
    if (!result.data) { setError("Notifications are temporarily unavailable."); return; }
    setNotifications(result.data); setError(null);
  };
  useEffect(() => {
    const initial = window.setTimeout(() => void load(), 0);
    const timer = window.setInterval(() => void load(), 30_000);
    return () => { window.clearTimeout(initial); window.clearInterval(timer); };
  }, []);
  const read = async (notification: Notification) => {
    if (notification.read_at) return;
    const result = await api.POST("/notifications/{notification_id}/read", { params: { path: { notification_id: notification.id } } });
    if (result.data) setNotifications((current) => current.map((item) => item.id === result.data?.id ? result.data : item));
  };

  return <div className="fixed right-3 top-3 z-[60] flex items-center gap-2 sm:right-5 sm:top-5"><details className="relative"><summary aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`} className="cursor-pointer list-none rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 shadow-sm hover:bg-slate-50">Notifications{unread ? <span className="ml-2 rounded-full bg-blue-600 px-1.5 py-0.5 text-xs text-white">{unread}</span> : null}</summary><section aria-label="Notifications" className="absolute right-0 mt-2 max-h-[70vh] w-80 overflow-y-auto rounded-xl border border-slate-200 bg-white p-2 shadow-xl"><h2 className="px-2 py-2 text-sm font-bold text-slate-800">Notifications</h2>{error ? <p className="px-2 pb-2 text-sm text-red-700" role="alert">{error}</p> : null}{notifications.length ? <ul className="divide-y divide-slate-100">{notifications.map((notification) => <li key={notification.id}><a className={`block rounded-lg px-2 py-3 text-sm hover:bg-slate-50 ${notification.read_at ? "text-slate-500" : "bg-blue-50/60 text-slate-800"}`} href={notification.request_id ? "/organization" : "#"} onClick={() => void read(notification)}><span className="block font-semibold">{notification.title}</span><span className="mt-1 block leading-5">{notification.body}</span><time className="mt-1 block text-xs text-slate-400">{new Date(notification.created_at).toLocaleString()}</time></a></li>)}</ul> : <p className="px-2 pb-2 text-sm text-slate-500">You’re all caught up.</p>}</section></details><details className="relative"><summary aria-label="Account menu" className="cursor-pointer list-none rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 shadow-sm hover:bg-slate-50">Account</summary><div className="absolute right-0 mt-2 w-56 rounded-xl border border-slate-200 bg-white p-3 text-sm shadow-xl"><p className="truncate font-medium text-slate-800">{user.email}</p><p className="mt-1 capitalize text-slate-500">{user.role}</p><button className="mt-3 w-full rounded-md border border-slate-300 px-3 py-2 text-left font-medium text-slate-700 hover:bg-slate-50" onClick={onSignOut} type="button">Sign out</button></div></details></div>;
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
