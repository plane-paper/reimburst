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

  return (
    <section className="w-full max-w-2xl rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm">
      <div className="space-y-1">
        <h2 className="text-xl font-semibold text-zinc-950">Scan a receipt</h2>
        <p className="text-sm text-zinc-600">Take a photo or choose a JPEG, PNG, or WebP image up to 10 MB.</p>
      </div>
      <label className="mt-5 flex cursor-pointer items-center justify-center rounded-lg border border-dashed border-zinc-400 px-4 py-8 text-center text-sm font-medium text-zinc-700 hover:border-zinc-950">
        <span>{uploading ? "Uploading receipt…" : "Choose a receipt image"}</span>
        <input
          className="sr-only"
          type="file"
          accept="image/jpeg,image/png,image/webp"
          capture="environment"
          disabled={uploading}
          onChange={upload}
        />
      </label>
      {error && <p className="mt-4 text-sm text-red-700">{error}</p>}
      {waiting && <p className="mt-4 text-sm text-zinc-600">Extracting receipt details…</p>}
      {receipt?.extraction_status === "failed" && (
        <p className="mt-4 text-sm text-red-700">Extraction failed: {receipt.extraction_error ?? "Try another image."}</p>
      )}
      {receipt?.extraction_status === "succeeded" && (
        <div className="mt-5 space-y-4 border-t border-zinc-200 pt-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="font-medium text-zinc-950">{receipt.merchant ?? "Unknown merchant"}</p>
              <p className="text-sm text-zinc-600">Extracted receipt</p>
            </div>
            <p className="font-semibold text-zinc-950">{formatCents(receipt.total_cents, receipt.currency)}</p>
          </div>
          <ul className="divide-y divide-zinc-100 rounded-lg border border-zinc-200">
            {receipt.line_items.map((item, index) => (
              <li className="flex justify-between gap-4 px-4 py-3 text-sm" key={`${item.description}-${index}`}>
                <span>{item.description}</span>
                <span>{formatCents(item.amount_cents, receipt.currency)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
