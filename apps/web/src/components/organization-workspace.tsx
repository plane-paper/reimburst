"use client";
/* eslint-disable @next/next/no-img-element -- Receipt host is configured at runtime; do not proxy sensitive image bytes through Next.js. */

import { authenticatedFetch, createApiClient, type components } from "@reimburse/contract";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { ReceiptCapture } from "@/components/receipt-capture";
import { useAuthenticatedUser } from "@/components/auth-gate";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const api = createApiClient(apiBaseUrl);
type Receipt = components["schemas"]["ReceiptDetail"];
type OrganizationRequest = components["schemas"]["OrganizationRequestDetail"];

function money(cents: number | null, currency: string | null | undefined) {
  if (cents === null) return "—";
  const sign = cents < 0 ? "-" : "";
  return `${sign}${currency ?? "USD"} ${Math.floor(Math.abs(cents) / 100).toLocaleString()}.${String(Math.abs(cents) % 100).padStart(2, "0")}`;
}

function statusClass(status: string) {
  return { draft: "bg-slate-100 text-slate-700", submitted: "bg-blue-50 text-blue-700", approved: "bg-emerald-50 text-emerald-700", rejected: "bg-red-50 text-red-700", paid: "bg-violet-50 text-violet-700" }[status] ?? "bg-slate-100 text-slate-700";
}

export function OrganizationWorkspace() {
  const user = useAuthenticatedUser();
  const isApprover = user.role === "approver" || user.role === "admin";
  const isEmployee = user.role === "employee";
  const view: "employee" | "approver" = isApprover ? "approver" : "employee";
  const [available, setAvailable] = useState<Receipt[]>([]);
  const [mine, setMine] = useState<OrganizationRequest[]>([]);
  const [pending, setPending] = useState<OrganizationRequest[]>([]);
  const [selectedReceiptIds, setSelectedReceiptIds] = useState<number[]>([]);
  const [selectedRequest, setSelectedRequest] = useState<OrganizationRequest | null>(null);
  const [note, setNote] = useState("");
  const [captureOpen, setCaptureOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [receipts, employeeRequests, approverRequests] = await Promise.all([
      isEmployee ? api.GET("/organization/receipts/available") : Promise.resolve({ data: [] as Receipt[] }),
      isEmployee ? api.GET("/organization/requests/mine") : Promise.resolve({ data: [] as OrganizationRequest[] }),
      isApprover ? api.GET("/organization/requests/pending") : Promise.resolve({ data: [] as OrganizationRequest[] }),
    ]);
    if (!receipts.data || !employeeRequests.data || !approverRequests.data) {
      setError("Could not load the organization workspace. Please refresh and try again.");
      return;
    }
    setAvailable(receipts.data);
    setMine(employeeRequests.data);
    setPending(approverRequests.data);
    setError(null);
    setSelectedRequest((current) => {
      if (!current) return null;
      return [...employeeRequests.data, ...approverRequests.data].find((request) => request.id === current.id) ?? null;
    });
  }, [isApprover, isEmployee]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);
  useEffect(() => {
    if (selectedRequest && ["pending", "processing"].includes(selectedRequest.synopsis_status)) {
      const timer = window.setInterval(() => void load(), 2000);
      return () => window.clearInterval(timer);
    }
  }, [load, selectedRequest]);

  const selectedReceipts = available.filter((receipt) => selectedReceiptIds.includes(receipt.id));
  const currencies = new Set(selectedReceipts.map((receipt) => receipt.currency));
  const selectionValid = selectedReceiptIds.length > 0 && currencies.size === 1 && !currencies.has(null);

  const toggleReceipt = (id: number) => setSelectedReceiptIds((ids) => ids.includes(id) ? ids.filter((value) => value !== id) : [...ids, id]);
  const createDraft = async () => {
    if (!selectionValid) return;
    setBusy(true); setError(null);
    const result = await api.POST("/organization/requests", { body: { receipt_ids: selectedReceiptIds } });
    setBusy(false);
    if (!result.data) { setError("Could not create the draft. Confirm eligible receipts and try again."); return; }
    setSelectedReceiptIds([]); setSelectedRequest(result.data); await load();
  };
  const submit = async (request: OrganizationRequest) => {
    setBusy(true); setError(null);
    const result = await api.POST("/organization/requests/{request_id}/submit", { params: { path: { request_id: request.id } } });
    setBusy(false);
    if (!result.data) { setError("Could not submit this request. Please try again."); return; }
    setSelectedRequest(result.data); await load();
  };
  const retrySynopsis = async (request: OrganizationRequest) => {
    setBusy(true); setError(null);
    const result = await api.POST("/organization/requests/{request_id}/retry-synopsis", { params: { path: { request_id: request.id } } });
    setBusy(false);
    if (!result.data) { setError("Could not retry synopsis generation. Please try again."); return; }
    setSelectedRequest(result.data); await load();
  };
  const review = async (action: "approve" | "reject") => {
    if (!selectedRequest) return;
    setBusy(true); setError(null);
    const result = action === "approve"
      ? await api.POST("/organization/requests/{request_id}/approve", { params: { path: { request_id: selectedRequest.id } }, body: { note: note.trim() || null } })
      : await api.POST("/organization/requests/{request_id}/reject", { params: { path: { request_id: selectedRequest.id } }, body: { note: note.trim() || null } });
    setBusy(false);
    if (!result.data) { setError(`Could not ${action} this request. Please try again.`); return; }
    setSelectedRequest(result.data); setNote(""); await load();
  };

  if (!isEmployee && !isApprover) return <main className="grid min-h-screen place-items-center p-5 text-slate-600">Your individual account cannot access organization reimbursements.</main>;
  const requests = view === "employee" ? mine : pending;
  return <main className="min-h-screen bg-[#f8faff] px-5 py-8 text-[#14213d] sm:px-10"><div className="mx-auto max-w-7xl">
    <div className="flex flex-wrap items-center justify-between gap-4"><div><Link className="text-sm font-semibold text-blue-600" href="/">← Home</Link><h1 className="mt-4 text-3xl font-bold">Organization reimbursements</h1><p className="mt-2 text-slate-500">Capture confirmed receipts, submit a request, or review the approval queue.</p></div><button className="rounded-lg bg-[#2563eb] px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-700" onClick={() => setCaptureOpen(true)} type="button">Scan organization receipt</button></div>
    <p className="mt-3 text-sm text-slate-500">Signed in as {user.email} · <span className="capitalize">{user.role}</span></p>
    {error && <p className="mt-5 rounded-lg border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700" role="alert">{error}</p>}
    {view === "employee" && <section className="mt-7 rounded-xl border border-slate-200 bg-white"><div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 p-5"><div><h2 className="font-bold">Available confirmed receipts</h2><p className="mt-1 text-sm text-slate-500">Choose receipts in one currency to create a draft.</p></div><button className="rounded-lg bg-[#2563eb] px-4 py-2 text-sm font-semibold text-white disabled:bg-slate-300" disabled={!selectionValid || busy} onClick={createDraft} type="button">{busy ? "Creating…" : `Create draft${selectedReceiptIds.length ? ` (${selectedReceiptIds.length})` : ""}`}</button></div>{selectedReceiptIds.length > 1 && currencies.size > 1 && <p className="mx-5 mt-4 rounded bg-amber-50 p-3 text-sm text-amber-800">A request can contain receipts in one currency only.</p>}<div className="overflow-x-auto"><table className="w-full min-w-[640px] text-left text-sm"><thead className="bg-slate-50 text-slate-500"><tr><th className="p-4">Select</th><th>Merchant</th><th>Date</th><th>Items</th><th className="pr-4 text-right">Total</th></tr></thead><tbody>{available.map((receipt) => <tr className="border-t border-slate-100" key={receipt.id}><td className="p-4"><input aria-label={`Select ${receipt.merchant ?? "receipt"}`} checked={selectedReceiptIds.includes(receipt.id)} onChange={() => toggleReceipt(receipt.id)} type="checkbox" /></td><td className="font-medium">{receipt.merchant ?? "Unknown merchant"}</td><td>{receipt.confirmed_at ? new Date(receipt.confirmed_at).toLocaleDateString() : "—"}</td><td>{receipt.line_items.length}</td><td className="pr-4 text-right font-semibold">{money(receipt.total_cents, receipt.currency)}</td></tr>)}{!available.length && <tr><td className="p-6 text-center text-slate-500" colSpan={5}>No confirmed receipts are ready for a new request.</td></tr>}</tbody></table></div></section>}
    <div className="mt-7 grid gap-6 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]"><section className="overflow-hidden rounded-xl border border-slate-200 bg-white"><div className="border-b border-slate-100 p-5"><h2 className="font-bold">{view === "employee" ? "My reimbursement requests" : "Pending approval"}</h2><p className="mt-1 text-sm text-slate-500">{view === "employee" ? "Draft, submitted, and completed requests." : "Submitted requests awaiting your decision."}</p></div><div className="divide-y divide-slate-100">{requests.map((request) => <button className={`w-full p-4 text-left hover:bg-slate-50 ${selectedRequest?.id === request.id ? "bg-blue-50/60" : ""}`} key={request.id} onClick={() => setSelectedRequest(request)} type="button"><div className="flex items-center justify-between gap-3"><span className="font-semibold">Request #{request.id}</span><span className={`rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${statusClass(request.status)}`}>{request.status}</span></div><p className="mt-2 text-sm text-slate-500">{request.receipts.length} receipt{request.receipts.length === 1 ? "" : "s"} · {request.currency}</p></button>)}{!requests.length && <p className="p-6 text-sm text-slate-500">{view === "employee" ? "Create a draft from confirmed receipts to get started." : "There are no requests waiting for approval."}</p>}</div></section><RequestDetail request={selectedRequest} approver={view === "approver"} busy={busy} note={note} onNoteChange={setNote} onRetry={retrySynopsis} onSubmit={submit} onReview={review} /></div>
  </div>{captureOpen && <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-950/35 p-4 backdrop-blur-sm sm:p-8"><div aria-modal="true" className="mx-auto mt-4 max-w-2xl" role="dialog"><div className="mb-3 flex justify-end"><button aria-label="Close receipt capture" className="rounded-full bg-white p-2 text-slate-500 shadow-sm hover:text-slate-900" onClick={() => setCaptureOpen(false)} type="button">✕</button></div><ReceiptCapture organization onConfirmed={() => void load()} /></div></div>}</main>;
}

function AuthenticatedReceiptImage({ receipt }: { receipt: OrganizationRequest["receipts"][number] }) {
  const [source, setSource] = useState<string | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    let objectUrl: string | null = null;
    const timer = window.setTimeout(() => void (async () => {
      const response = await authenticatedFetch(`${apiBaseUrl}/organization/receipts/${receipt.id}/image`);
      if (!response.ok) { setError(true); return; }
      objectUrl = URL.createObjectURL(await response.blob());
      setSource(objectUrl);
    })(), 0);
    return () => { window.clearTimeout(timer); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [receipt.id]);
  if (error) return <p className="grid h-32 place-items-center bg-red-50 px-4 text-center text-sm text-red-700" role="alert">Receipt preview is unavailable. Please try again later.</p>;
  if (!source) return <div aria-label="Loading receipt preview" className="h-32 animate-pulse bg-slate-100" />;
  return <img alt={`Receipt from ${receipt.merchant ?? "unknown merchant"}`} className="max-h-64 w-full object-contain bg-slate-50" src={source} />;
}

function RequestDetail({ request, approver, busy, note, onNoteChange, onRetry, onSubmit, onReview }: { request: OrganizationRequest | null; approver: boolean; busy: boolean; note: string; onNoteChange: (value: string) => void; onRetry: (request: OrganizationRequest) => void; onSubmit: (request: OrganizationRequest) => void; onReview: (action: "approve" | "reject") => void }) {
  if (!request) return <section className="rounded-xl border border-dashed border-slate-300 bg-white p-8 text-sm text-slate-500">Select a request to inspect its receipts, synopsis, and audit trail.</section>;
  const synopsisPending = ["pending", "processing"].includes(request.synopsis_status);
  return <section className="rounded-xl border border-slate-200 bg-white p-5"><div className="flex items-start justify-between gap-3"><div><h2 className="text-lg font-bold">Request #{request.id}</h2><p className="mt-1 text-sm text-slate-500">Employee #{request.employee_id} · {request.currency}</p></div><span className={`rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${statusClass(request.status)}`}>{request.status}</span></div><div className="mt-5 rounded-lg bg-slate-50 p-4"><p className="text-xs font-bold uppercase tracking-wide text-slate-500">Approver synopsis</p>{synopsisPending && <p className="mt-2 text-sm text-blue-700"><span className="mr-2 inline-block size-2 animate-pulse rounded-full bg-blue-600" />Generating synopsis…</p>}{request.synopsis_status === "failed" && <div className="mt-2 text-sm text-red-700"><p>Synopsis generation failed: {request.synopsis_error ?? "Please retry."}</p>{!approver && request.status === "submitted" && <button className="mt-2 font-semibold text-blue-700" disabled={busy} onClick={() => onRetry(request)} type="button">Retry generation</button>}</div>}{request.synopsis && <p className="mt-2 text-sm leading-6 text-slate-700">{request.synopsis}</p>}</div><div className="mt-5"><h3 className="font-semibold">Receipts</h3><div className="mt-3 space-y-4">{request.receipts.map((receipt) => <article className="overflow-hidden rounded-lg border border-slate-200" key={receipt.id}><AuthenticatedReceiptImage receipt={receipt} /><div className="p-3"><div className="flex justify-between gap-3"><p className="font-semibold">{receipt.merchant ?? "Unknown merchant"}</p><p className="font-semibold">{money(receipt.total_cents, receipt.currency)}</p></div><p className="mt-1 text-xs text-slate-500">{receipt.date ?? "Date unavailable"}</p><ul className="mt-3 divide-y divide-slate-100 text-sm">{receipt.line_items.map((item) => <li className="flex justify-between gap-3 py-2" key={item.id}><span>{item.description}<span className="ml-2 text-xs capitalize text-slate-400">{item.category?.replaceAll("_", " ") ?? "uncategorized"}</span></span><span className="font-medium">{money(item.amount_cents, receipt.currency)}</span></li>)}</ul></div></article>)}</div></div><div className="mt-5"><h3 className="font-semibold">Audit trail</h3><ol className="mt-2 space-y-2 border-l border-slate-200 pl-4 text-sm">{request.audit_events.map((event) => <li key={event.id}><span className="font-medium capitalize">{event.action.replaceAll("_", " ")}</span><span className="ml-2 text-slate-500">{new Date(event.created_at).toLocaleString()}</span>{event.payload?.note && <p className="mt-1 text-slate-600">{event.payload.note}</p>}</li>)}{!request.audit_events.length && <li className="text-slate-500">No transitions recorded yet.</li>}</ol></div>{!approver && request.status === "draft" && <button className="mt-6 w-full rounded-lg bg-[#2563eb] px-4 py-3 text-sm font-semibold text-white disabled:bg-slate-300" disabled={busy} onClick={() => onSubmit(request)} type="button">{busy ? "Submitting…" : "Submit for approval"}</button>}{approver && request.status === "submitted" && <div className="mt-6 space-y-3 border-t border-slate-100 pt-5"><label className="block text-sm font-semibold" htmlFor="review-note">Decision note <span className="font-normal text-slate-400">(optional)</span></label><textarea className="w-full rounded-lg border border-slate-300 p-3 text-sm" id="review-note" maxLength={1000} onChange={(event) => onNoteChange(event.target.value)} placeholder="Add context for the employee" value={note} /><div className="grid grid-cols-2 gap-3"><button className="rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm font-semibold text-red-700 disabled:opacity-50" disabled={busy} onClick={() => onReview("reject")} type="button">Reject</button><button className="rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50" disabled={busy} onClick={() => onReview("approve")} type="button">Approve</button></div></div>}</section>;
}
