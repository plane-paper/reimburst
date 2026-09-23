"use client";

import { createApiClient, type components } from "@reimburse/contract";
import { ChangeEvent, useEffect, useState } from "react";

const apiClient = createApiClient(process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000");
type Receipt = components["schemas"]["ReceiptDetail"];
type DraftItem = components["schemas"]["ConfirmedLineItem"];
type Category = components["schemas"]["CategoryDetail"];

function formatCents(cents: number | null, currency: string | null | undefined) {
  if (cents === null) return "—";
  const sign = cents < 0 ? "-" : "";
  const value = Math.abs(cents);
  return `${sign}${currency ?? "USD"} ${Math.floor(value / 100).toLocaleString()}.${String(value % 100).padStart(2, "0")}`;
}

function centsToInput(cents: number) {
  const sign = cents < 0 ? "-" : "";
  const value = Math.abs(cents);
  return `${sign}${Math.floor(value / 100)}.${String(value % 100).padStart(2, "0")}`;
}

function inputToCents(value: string): number | null {
  const match = /^(-?)(\d+)(?:\.(\d{0,2}))?$/.exec(value.trim());
  if (!match) return null;
  const cents = Number(match[2]) * 100 + Number((match[3] ?? "").padEnd(2, "0"));
  return match[1] === "-" ? -cents : cents;
}

function Icon({ name }: { name: "camera" | "check" | "sparkle" }) {
  const paths = {
    camera: <><path d="M4 8h3l2-3h6l2 3h3v11H4z" /><circle cx="12" cy="13" r="3" /></>,
    check: <path d="m5 12 4 4L19 6" />,
    sparkle: <><path d="m12 3-1.4 5.6L5 10l5.6 1.4L12 17l1.4-5.6L19 10l-5.6-1.4z" /></>,
  };
  return <svg aria-hidden="true" fill="none" height="24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" viewBox="0 0 24 24" width="24">{paths[name]}</svg>;
}

export function ReceiptCapture() {
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [draftItems, setDraftItems] = useState<DraftItem[]>([]);
  const [amountInputs, setAmountInputs] = useState<Record<number, string>>({});
  const [acknowledgedMismatch, setAcknowledgedMismatch] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const shouldPoll = receipt && (["pending", "processing"].includes(receipt.extraction_status) || (receipt.extraction_status === "succeeded" && ["pending", "processing"].includes(receipt.categorization_status)));
  const reviewReady = receipt?.extraction_status === "succeeded" && ["succeeded", "failed"].includes(receipt.categorization_status);

  function receiveReceipt(nextReceipt: Receipt) {
    setReceipt(nextReceipt);
    if (nextReceipt.extraction_status === "succeeded" && ["succeeded", "failed"].includes(nextReceipt.categorization_status)) {
      setDraftItems(nextReceipt.line_items.map((item) => ({ id: item.id, description: item.description, amount_cents: item.amount_cents, category: item.category ?? "uncategorized" })));
      setAmountInputs(Object.fromEntries(nextReceipt.line_items.map((item) => [item.id, centsToInput(item.amount_cents)])));
      setAcknowledgedMismatch(false);
    }
  }

  useEffect(() => {
    if (!shouldPoll || !receipt) return;
    const timer = window.setTimeout(async () => {
      const { data, error: requestError } = await apiClient.GET("/receipts/{receipt_id}", { params: { path: { receipt_id: receipt.id } } });
      if (data) receiveReceipt(data);
      if (requestError) setError("Could not retrieve the receipt. Please try again.");
    }, 1500);
    return () => window.clearTimeout(timer);
  }, [receipt, shouldPoll]);

  useEffect(() => {
    if (receipt?.extraction_status !== "succeeded") return;
    void (async () => {
      const { data, error: taxonomyError } = await apiClient.GET("/receipts/taxonomy");
      if (data) setCategories(data);
      if (taxonomyError) setError("Could not load categories. Please refresh and try again.");
    })();
  }, [receipt?.extraction_status]);

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploading(true); setError(null); setReceipt(null); setCategories([]);
    try {
      const form = new FormData(); form.append("image", file);
      const { data, error: uploadError } = await apiClient.POST("/receipts", { body: form as never });
      if (uploadError || !data) throw new Error("Upload failed");
      setReceipt({ ...data, merchant: null, total_cents: null, tax_cents: null, currency: null, extraction_error: null, categorization_status: "pending", categorization_error: null, line_items: [], reconciliation: { line_items_total_cents: 0, receipt_total_cents: null, difference_cents: null, matches: false }, confirmed_at: null });
    } catch { setError("We could not upload that receipt. Check your connection and try again."); }
    finally { setUploading(false); event.target.value = ""; }
  }

  function updateItem(id: number, update: Partial<DraftItem>) { setDraftItems((items) => items.map((item) => item.id === id ? { ...item, ...update } : item)); }
  const draftTotal = draftItems.reduce((total, item) => total + item.amount_cents, 0);
  const difference = receipt?.total_cents == null ? null : draftTotal - receipt.total_cents;
  const matches = difference === 0;
  const amountsValid = draftItems.every((item) => inputToCents(amountInputs[item.id] ?? "") === item.amount_cents);
  const descriptionsValid = draftItems.every((item) => item.description.trim().length > 0);
  const canConfirm = Boolean(reviewReady && categories.length && amountsValid && descriptionsValid && (matches || acknowledgedMismatch) && !receipt?.confirmed_at);

  async function confirm() {
    if (!receipt || !canConfirm) return;
    setSaving(true); setError(null);
    try {
      const { data, error: confirmationError } = await apiClient.PUT("/receipts/{receipt_id}/confirmation", { params: { path: { receipt_id: receipt.id } }, body: { line_items: draftItems, acknowledge_reconciliation_mismatch: acknowledgedMismatch } });
      if (confirmationError || !data) throw new Error("Confirmation failed");
      receiveReceipt(data);
    } catch { setError("We could not save your confirmation. Review the receipt and try again."); }
    finally { setSaving(false); }
  }

  return <section className="w-full rounded-xl border border-slate-200 bg-white p-5 shadow-xl shadow-slate-900/10 sm:p-7">
    <div className="flex gap-4"><div className="grid size-11 shrink-0 place-items-center rounded-xl bg-blue-50 text-[#2563eb]"><Icon name="camera" /></div><div><h2 className="text-xl font-bold tracking-tight text-[#14213d]">Scan a receipt</h2><p className="mt-1 text-sm leading-5 text-slate-500">Take a photo or upload an image. Review and correct every item before confirming.</p></div></div>
    <label className={`mt-6 flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-5 py-9 text-center transition ${uploading ? "border-blue-200 bg-blue-50/50" : "border-blue-200 bg-blue-50/30 hover:border-[#2563eb] hover:bg-blue-50"}`}><span className={`grid size-12 place-items-center rounded-full ${uploading ? "bg-blue-100 text-[#2563eb]" : "bg-white text-[#2563eb] shadow-sm"}`}><Icon name={uploading ? "sparkle" : "camera"} /></span><span className="mt-4 font-semibold text-[#14213d]">{uploading ? "Uploading receipt…" : "Take a photo or choose a file"}</span><span className="mt-1 text-sm text-slate-500">JPEG, PNG, or WebP · up to 10 MB</span><input className="sr-only" type="file" accept="image/jpeg,image/png,image/webp" capture="environment" disabled={uploading} onChange={upload} /></label>
    {error && <p className="mt-5 rounded-lg border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700" role="alert">{error}</p>}
    {shouldPoll && <div className="mt-5 flex items-center gap-3 rounded-lg border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-blue-800"><span className="size-2 animate-pulse rounded-full bg-[#2563eb]" />{receipt?.extraction_status === "succeeded" ? "Categorizing line items…" : "Extracting receipt details…"}</div>}
    {receipt?.extraction_status === "failed" && <p className="mt-5 rounded-lg border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">Extraction failed: {receipt.extraction_error ?? "Try another image."}</p>}
    {receipt?.categorization_status === "failed" && <p className="mt-5 rounded-lg border border-amber-100 bg-amber-50 px-4 py-3 text-sm text-amber-800">We extracted this receipt, but could not categorize it. Select a category for every item below.</p>}
    {reviewReady && receipt && <div className="mt-5 space-y-4 rounded-xl border border-slate-200 bg-slate-50/60 p-4 sm:p-5">
      <div className="flex items-start justify-between gap-4"><div><p className="font-semibold text-[#14213d]">{receipt.merchant ?? "Unknown merchant"}</p><p className="mt-1 flex items-center gap-1.5 text-sm text-emerald-700"><Icon name="check" />Ready for your review</p></div><p className="text-lg font-bold text-[#14213d]">{formatCents(receipt.total_cents, receipt.currency)}</p></div>
      {receipt.confirmed_at ? <p className="rounded-lg border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-800">Confirmed breakdown saved. It is ready for the next workflow step.</p> : <>
        {difference !== null && !matches && <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900" role="alert"><p className="font-semibold">The item total differs from the receipt total by {formatCents(difference, receipt.currency)}.</p><p className="mt-1">Correct the items, or explicitly acknowledge this difference before confirming.</p></div>}
        {difference === null && <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900" role="alert">The extracted receipt total is unavailable, so this receipt cannot be confirmed.</div>}
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white"><table className="w-full min-w-[640px] text-left text-sm"><thead className="border-b border-slate-100 bg-slate-50 text-xs font-medium text-slate-500"><tr><th className="px-3 py-3">Description</th><th className="px-3 py-3">Amount</th><th className="px-3 py-3">Category</th></tr></thead><tbody>{draftItems.map((item) => { const source = receipt.line_items.find((line) => line.id === item.id); const invalid = inputToCents(amountInputs[item.id] ?? "") === null; return <tr className={`border-b border-slate-100 last:border-0 ${source?.needs_category_review ? "bg-amber-50/60" : ""}`} key={item.id}><td className="px-3 py-3"><label className="sr-only" htmlFor={`description-${item.id}`}>Description</label><input className="w-full rounded border border-slate-300 px-2 py-1.5 text-slate-800" id={`description-${item.id}`} value={item.description} onChange={(event) => updateItem(item.id, { description: event.target.value })} /></td><td className="px-3 py-3"><label className="sr-only" htmlFor={`amount-${item.id}`}>Amount in {receipt.currency ?? "USD"}</label><input aria-invalid={invalid} className="w-28 rounded border border-slate-300 px-2 py-1.5 text-slate-800 aria-[invalid=true]:border-red-500" id={`amount-${item.id}`} inputMode="decimal" value={amountInputs[item.id] ?? ""} onChange={(event) => { const value = event.target.value; setAmountInputs((values) => ({ ...values, [item.id]: value })); const cents = inputToCents(value); if (cents !== null) updateItem(item.id, { amount_cents: cents }); }} /></td><td className="px-3 py-3"><label className="sr-only" htmlFor={`category-${item.id}`}>Category</label><select className="w-full rounded border border-slate-300 bg-white px-2 py-1.5 text-slate-800" id={`category-${item.id}`} value={item.category} onChange={(event) => updateItem(item.id, { category: event.target.value })}>{categories.map((category) => <option key={category.id} value={category.name}>{category.name.replaceAll("_", " ")}</option>)}</select>{source?.needs_category_review && <p className="mt-1 text-xs font-medium text-amber-700">Needs review</p>}</td></tr>; })}</tbody><tfoot className="bg-slate-50 text-sm font-semibold"><tr><td className="px-3 py-3" colSpan={2}>Line-item total</td><td className="px-3 py-3">{formatCents(draftTotal, receipt.currency)}</td></tr></tfoot></table></div>
        {!amountsValid && <p className="text-sm text-red-700">Enter each amount with no more than two decimal places.</p>}
        {!matches && difference !== null && <label className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"><input className="mt-0.5 size-4" checked={acknowledgedMismatch} onChange={(event) => setAcknowledgedMismatch(event.target.checked)} type="checkbox" /><span>I reviewed the {formatCents(difference, receipt.currency)} difference and want to confirm this breakdown.</span></label>}
        <button className="w-full rounded-lg bg-[#2563eb] px-4 py-3 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300" disabled={!canConfirm || saving} onClick={confirm} type="button">{saving ? "Saving confirmation…" : "Confirm reviewed breakdown"}</button>
      </>}
    </div>}
  </section>;
}
