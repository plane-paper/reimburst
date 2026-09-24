"use client";

import { createApiClient, type components } from "@reimburse/contract";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

const api = createApiClient(process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000");
type History = components["schemas"]["SpendingHistory"];
type OutboundRequest = components["schemas"]["OutboundRequestDetail"];

function money(cents: number, currency: string | null) {
  return `${currency ?? "USD"} ${(cents / 100).toFixed(2)}`;
}

function timestamp(value: string | null) {
  return value ? new Date(value).toLocaleString() : "—";
}

export default function RequestsPage() {
  const [history, setHistory] = useState<History | null>(null);
  const [requests, setRequests] = useState<OutboundRequest[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [payer, setPayer] = useState("");
  const [active, setActive] = useState<OutboundRequest | null>(null);
  const activeId = useRef<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [items, outbound] = await Promise.all([api.GET("/spending/history"), api.GET("/outbound-requests")]);
    if (!items.data || !outbound.data) { setError("Could not load your request workspace. Please try again."); return; }
    setHistory(items.data); setRequests(outbound.data);
    if (activeId.current !== null) setActive(outbound.data.find((request) => request.id === activeId.current) ?? null);
  }, []);
  useEffect(() => { activeId.current = active?.id ?? null; }, [active]);
  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);
  useEffect(() => {
    if (active && ["pending", "processing"].includes(active.generation_status)) {
      const timer = window.setInterval(() => void load(), 2000);
      return () => window.clearInterval(timer);
    }
  }, [active, load]);

  const chosen = history?.items.filter((item) => selected.includes(item.line_item_id)) ?? [];
  const total = chosen.reduce((sum, item) => sum + item.amount_cents, 0);
  const currencies = [...new Set(chosen.map((item) => item.currency ?? "USD"))];
  const toggle = (id: number) => setSelected((current) => current.includes(id) ? current.filter((value) => value !== id) : [...current, id]);
  const generate = async () => {
    if (!payer.trim() || !selected.length) return;
    setBusy(true); setError(null);
    const result = await api.POST("/outbound-requests", { body: { external_payer: payer.trim(), line_item_ids: selected } });
    setBusy(false);
    if (!result.data) { setError("Could not start the reimbursement request. Please try again."); return; }
    activeId.current = result.data.id; setActive(result.data); setSelected([]); await load();
  };
  const save = async () => {
    if (!active) return;
    setBusy(true); setError(null);
    const result = await api.PUT("/outbound-requests/{request_id}", { params: { path: { request_id: active.id } }, body: { external_payer: active.external_payer ?? undefined, synopsis: active.synopsis ?? undefined, subject: active.subject ?? undefined, body: active.body ?? undefined } });
    setBusy(false);
    if (!result.data) { setError("Could not save the draft. Please try again."); return; }
    setActive(result.data); await load();
  };
  const markSent = async () => {
    if (!active) return;
    const result = await api.POST("/outbound-requests/{request_id}/mark-sent", { params: { path: { request_id: active.id } } });
    if (!result.data) { setError("Could not mark this request as sent. Please try again."); return; }
    setActive(result.data); await load();
  };
  const copy = async () => {
    if (!active?.subject || !active.body) return;
    await navigator.clipboard.writeText(`Subject: ${active.subject}\n\n${active.body}`);
  };
  const download = () => {
    if (!active?.subject || !active.body) return;
    const blob = new Blob([`To: ${active.external_payer ?? ""}\nSubject: ${active.subject}\n\n${active.body}`], { type: "message/rfc822" });
    const anchor = document.createElement("a"); anchor.href = URL.createObjectURL(blob); anchor.download = "reimbursement-request.eml"; anchor.click(); URL.revokeObjectURL(anchor.href);
  };

  return <main className="min-h-screen bg-[#f8faff] px-5 py-10 text-[#14213d] sm:px-10"><div className="mx-auto max-w-6xl">
    <Link className="text-sm font-semibold text-blue-600" href="/">← Home</Link>
    <div className="mt-5"><h1 className="text-3xl font-bold">Reimbursement requests</h1><p className="mt-2 text-slate-500">Select confirmed items, then create a draft to send through your own email client.</p></div>
    {error && <p className="mt-5 rounded bg-red-50 p-3 text-red-700">{error}</p>}
    <div className="mt-7 grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]"><section className="overflow-hidden rounded-xl border border-slate-200 bg-white"><div className="border-b border-slate-100 p-5"><h2 className="font-bold">Select confirmed items</h2><p className="mt-1 text-sm text-slate-500">Items already in a generated or sent request are unavailable.</p></div><div className="overflow-x-auto"><table className="w-full min-w-[650px] text-left text-sm"><thead className="bg-slate-50 text-slate-500"><tr><th className="p-4">Select</th><th>Receipt</th><th>Item</th><th>Category</th><th className="pr-4 text-right">Amount</th></tr></thead><tbody>{history?.items.map((item) => { const unavailable = requests.some((request) => ["generated", "sent"].includes(request.status) && request.items.some((covered) => covered.line_item_id === item.line_item_id)); return <tr className="border-t border-slate-100" key={item.line_item_id}><td className="p-4"><input aria-label={`Select ${item.description}`} checked={selected.includes(item.line_item_id)} disabled={unavailable} onChange={() => toggle(item.line_item_id)} type="checkbox" /></td><td>{item.merchant ?? "Unknown merchant"}<span className="block text-xs text-slate-400">{item.receipt_date ?? "—"}</span></td><td>{item.description}</td><td className="capitalize">{item.category?.replaceAll("_", " ") ?? "Uncategorized"}</td><td className="pr-4 text-right font-semibold">{unavailable ? <span className="text-xs font-normal text-slate-400">Requested</span> : money(item.amount_cents, item.currency)}</td></tr>; })}</tbody></table></div></section><aside className="h-fit rounded-xl border border-slate-200 bg-white p-5"><h2 className="font-bold">Create request</h2><p className="mt-2 text-sm text-slate-500">{chosen.length} item{chosen.length === 1 ? "" : "s"} selected · {currencies.length === 1 ? money(total, currencies[0]) : "multiple currencies"}</p><label className="mt-5 block text-sm font-medium">External payer<input className="mt-1 w-full rounded border border-slate-300 p-2" onChange={(event) => setPayer(event.target.value)} placeholder="Employer or client" value={payer} /></label><button className="mt-4 w-full rounded bg-blue-600 px-4 py-2 font-semibold text-white disabled:opacity-50" disabled={busy || !payer.trim() || !selected.length} onClick={() => void generate()} type="button">{busy ? "Starting…" : "Generate email draft"}</button></aside></div>
    {active && <section className="mt-7 rounded-xl border border-slate-200 bg-white p-5"><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="font-bold">Request #{active.id}</h2><p className="mt-1 text-sm text-slate-500">{active.generation_status === "failed" ? active.generation_error ?? "Generation failed." : active.generation_status !== "succeeded" ? "Generating synopsis and email draft…" : `Generated ${timestamp(active.created_at)}`}</p></div><span className="rounded-full bg-blue-50 px-3 py-1 text-sm font-medium text-blue-700">{active.status}</span></div>{active.generation_status === "succeeded" && <div className="mt-5 grid gap-4"><label className="text-sm font-medium">External payer<input className="mt-1 w-full rounded border border-slate-300 p-2" onChange={(event) => setActive({ ...active, external_payer: event.target.value })} value={active.external_payer ?? ""} /></label><label className="text-sm font-medium">Synopsis<textarea className="mt-1 min-h-20 w-full rounded border border-slate-300 p-2" onChange={(event) => setActive({ ...active, synopsis: event.target.value })} value={active.synopsis ?? ""} /></label><label className="text-sm font-medium">Email subject<input className="mt-1 w-full rounded border border-slate-300 p-2" onChange={(event) => setActive({ ...active, subject: event.target.value })} value={active.subject ?? ""} /></label><label className="text-sm font-medium">Email body<textarea className="mt-1 min-h-56 w-full rounded border border-slate-300 p-2" onChange={(event) => setActive({ ...active, body: event.target.value })} value={active.body ?? ""} /></label><div className="flex flex-wrap gap-3"><button className="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white" disabled={busy || active.status === "sent"} onClick={() => void save()} type="button">Save draft</button><button className="rounded border border-slate-300 px-4 py-2 text-sm font-semibold" onClick={() => void copy()} type="button">Copy email</button><button className="rounded border border-slate-300 px-4 py-2 text-sm font-semibold" onClick={download} type="button">Download .eml</button><button className="rounded border border-emerald-300 px-4 py-2 text-sm font-semibold text-emerald-700" disabled={active.status === "sent"} onClick={() => void markSent()} type="button">{active.status === "sent" ? `Sent ${timestamp(active.sent_at)}` : "Mark as sent"}</button></div></div>}</section>}
    <section className="mt-7 rounded-xl border border-slate-200 bg-white p-5"><h2 className="font-bold">Request history</h2>{requests.length ? <ul className="mt-4 divide-y divide-slate-100">{requests.map((request) => <li className="flex flex-wrap items-center justify-between gap-3 py-4" key={request.id}><button className="text-left" onClick={() => { activeId.current = request.id; setActive(request); }} type="button"><span className="font-semibold">{request.external_payer ?? "External payer"}</span><span className="ml-2 text-sm text-slate-500">{request.items.length} item{request.items.length === 1 ? "" : "s"} · generated {timestamp(request.created_at)}</span></button><span className="rounded-full bg-slate-100 px-3 py-1 text-sm capitalize">{request.status}{request.sent_at ? ` · sent ${timestamp(request.sent_at)}` : ""}</span></li>)}</ul> : <p className="mt-3 text-sm text-slate-500">No outbound requests yet.</p>}</section>
  </div></main>;
}
