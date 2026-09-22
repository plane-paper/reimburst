"use client";

import { createApiClient, type components } from "@reimburse/contract";
import { ChangeEvent, useEffect, useState } from "react";

const apiClient = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

type Receipt = components["schemas"]["ReceiptDetail"];

function formatCents(cents: number | null, currency: string | null | undefined) {
  if (cents === null) return "—";
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: currency ?? "USD",
  }).format(cents / 100);
}

function CaptureIcon({ name }: { name: "camera" | "check" | "sparkle" }) {
  const paths = {
    camera: <><path d="M4 8h3l2-3h6l2 3h3v11H4z" /><circle cx="12" cy="13" r="3" /></>,
    check: <path d="m5 12 4 4L19 6" />,
    sparkle: <><path d="m12 3-1.4 5.6L5 10l5.6 1.4L12 17l1.4-5.6L19 10l-5.6-1.4z" /><path d="m19 16-.6 2.4L16 19l2.4.6L19 22l.6-2.4L22 19l-2.4-.6z" /></>,
  };
  return <svg aria-hidden="true" fill="none" height="24" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" viewBox="0 0 24 24" width="24">{paths[name]}</svg>;
}

export function ReceiptCapture() {
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!receipt || !["pending", "processing"].includes(receipt.extraction_status)) {
      return;
    }
    const timer = window.setTimeout(async () => {
      const { data, error: requestError } = await apiClient.GET("/receipts/{receipt_id}", {
        params: { path: { receipt_id: receipt.id } },
      });
      if (data) setReceipt(data);
      if (requestError) setError("Could not retrieve the extraction result. Please try again.");
    }, 1500);
    return () => window.clearTimeout(timer);
  }, [receipt]);

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    setReceipt(null);
    try {
      const form = new FormData();
      form.append("image", file);
      const { data, error: uploadError } = await apiClient.POST("/receipts", {
        body: form as never,
      });
      if (uploadError || !data) throw new Error("Upload failed");
      const created = data;
      setReceipt({
        ...created,
        merchant: null,
        total_cents: null,
        tax_cents: null,
        currency: null,
        extraction_error: null,
        categorization_status: "pending",
        categorization_error: null,
        line_items: [],
      });
    } catch {
      setError("We could not upload that receipt. Check your connection and try again.");
    } finally {
      setUploading(false);
      event.target.value = "";
    }
  }

  const waiting = receipt && ["pending", "processing"].includes(receipt.extraction_status);
  const categorizing = receipt?.extraction_status === "succeeded" && ["pending", "processing"].includes(receipt.categorization_status);

  return (
    <section className="w-full rounded-xl border border-slate-200 bg-white p-5 shadow-xl shadow-slate-900/10 sm:p-7">
      <div className="flex gap-4">
        <div className="grid size-11 shrink-0 place-items-center rounded-xl bg-blue-50 text-[#2563eb]">
          <CaptureIcon name="camera" />
        </div>
        <div>
          <h2 className="text-xl font-bold tracking-tight text-[#14213d]">Scan a receipt</h2>
          <p className="mt-1 text-sm leading-5 text-slate-500">Take a photo or upload an image. We’ll extract the details for you to review.</p>
        </div>
      </div>
      <label className={`mt-6 flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-5 py-9 text-center transition ${uploading ? "border-blue-200 bg-blue-50/50" : "border-blue-200 bg-blue-50/30 hover:border-[#2563eb] hover:bg-blue-50"}`}>
        <span className={`grid size-12 place-items-center rounded-full ${uploading ? "bg-blue-100 text-[#2563eb]" : "bg-white text-[#2563eb] shadow-sm"}`}>
          <CaptureIcon name={uploading ? "sparkle" : "camera"} />
        </span>
        <span className="mt-4 font-semibold text-[#14213d]">{uploading ? "Uploading receipt…" : "Take a photo or choose a file"}</span>
        <span className="mt-1 text-sm text-slate-500">JPEG, PNG, or WebP · up to 10 MB</span>
        <input
          className="sr-only"
          type="file"
          accept="image/jpeg,image/png,image/webp"
          capture="environment"
          disabled={uploading}
          onChange={upload}
        />
      </label>
      {error && <p className="mt-5 rounded-lg border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}
      {waiting && <div className="mt-5 flex items-center gap-3 rounded-lg border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-blue-800"><span className="size-2 animate-pulse rounded-full bg-[#2563eb]" />Extracting receipt details…</div>}
      {receipt?.extraction_status === "failed" && (
        <p className="mt-5 rounded-lg border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">Extraction failed: {receipt.extraction_error ?? "Try another image."}</p>
      )}
      {categorizing && <div className="mt-5 flex items-center gap-3 rounded-lg border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-blue-800"><span className="size-2 animate-pulse rounded-full bg-[#2563eb]" />Categorizing line items…</div>}
      {receipt?.categorization_status === "failed" && <p className="mt-5 rounded-lg border border-amber-100 bg-amber-50 px-4 py-3 text-sm text-amber-800">We extracted this receipt, but could not categorize it. You can categorize the items during review.</p>}
      {receipt?.extraction_status === "succeeded" && (
        <div className="mt-5 space-y-4 rounded-xl border border-slate-200 bg-slate-50/60 p-4 sm:p-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="font-semibold text-[#14213d]">{receipt.merchant ?? "Unknown merchant"}</p>
              <p className="mt-1 flex items-center gap-1.5 text-sm text-emerald-700"><CaptureIcon name="check" />Extracted successfully</p>
            </div>
            <p className="text-lg font-bold text-[#14213d]">{formatCents(receipt.total_cents, receipt.currency)}</p>
          </div>
          <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white">
            {receipt.line_items.map((item, index) => (
              <li className="flex justify-between gap-4 px-4 py-3 text-sm" key={`${item.description}-${index}`}>
                <span className="text-slate-600">{item.description}{item.category && <span className={`ml-2 rounded-full px-2 py-0.5 text-xs font-medium ${item.needs_category_review ? "bg-amber-50 text-amber-700" : "bg-blue-50 text-blue-700"}`}>{item.needs_category_review ? "Needs review: " : ""}{item.category.replaceAll("_", " ")}</span>}</span>
                <span className="font-semibold text-slate-700">{formatCents(item.amount_cents, receipt.currency)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
