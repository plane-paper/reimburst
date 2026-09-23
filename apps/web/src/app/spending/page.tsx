"use client";

import { createApiClient, type components } from "@reimburse/contract";
import Link from "next/link";
import { useEffect, useState } from "react";

const api = createApiClient(process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000");
type History = components["schemas"]["SpendingHistory"];
type Report = components["schemas"]["SpendingReport"];

function money(cents: number, currency: string | null) {
  return `${currency ?? "USD"} ${(cents / 100).toFixed(2)}`;
}

export default function SpendingPage() {
  const [history, setHistory] = useState<History | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [category, setCategory] = useState("");
  const [merchant, setMerchant] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      setError(null);
      const query = {
        ...(category ? { category } : {}), ...(merchant ? { merchant } : {}),
        ...(startDate ? { start_date: startDate } : {}), ...(endDate ? { end_date: endDate } : {}),
      };
      const [items, totals] = await Promise.all([
        api.GET("/spending/history", { params: { query } }),
        api.GET("/spending/report", { params: { query: { ...query, group_by: "category" } } }),
      ]);
      if (!items.data || !totals.data) setError("Could not load spending history. Please try again.");
      else { setHistory(items.data); setReport(totals.data); }
    })();
  }, [category, merchant, startDate, endDate]);

  const categories = [...new Set(history?.items.map((item) => item.category).filter(Boolean) ?? [])];
  const exportUrl = new URL("/spending/export.csv", process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000");
  if (category) exportUrl.searchParams.set("category", category);
  if (merchant) exportUrl.searchParams.set("merchant", merchant);
  if (startDate) exportUrl.searchParams.set("start_date", startDate);
  if (endDate) exportUrl.searchParams.set("end_date", endDate);

  return <main className="min-h-screen bg-[#f8faff] px-5 py-10 text-[#14213d] sm:px-10"><div className="mx-auto max-w-6xl">
    <Link className="text-sm font-semibold text-blue-600" href="/">← Home</Link>
    <div className="mt-5 flex flex-wrap items-end justify-between gap-4"><div><h1 className="text-3xl font-bold">Personal spending</h1><p className="mt-2 text-slate-500">Your confirmed receipt items, ready for your records.</p></div><a className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white" href={exportUrl.toString()}>Download CSV</a></div>
    <div className="mt-7 grid gap-3 rounded-xl border border-slate-200 bg-white p-4 md:grid-cols-4"><label className="text-sm">From<input className="mt-1 w-full rounded border border-slate-300 p-2" onChange={(event) => setStartDate(event.target.value)} type="date" value={startDate} /></label><label className="text-sm">To<input className="mt-1 w-full rounded border border-slate-300 p-2" onChange={(event) => setEndDate(event.target.value)} type="date" value={endDate} /></label><label className="text-sm">Category<select className="mt-1 w-full rounded border border-slate-300 bg-white p-2" onChange={(event) => setCategory(event.target.value)} value={category}><option value="">All</option>{categories.map((value) => <option key={value} value={value ?? ""}>{value?.replaceAll("_", " ")}</option>)}</select></label><label className="text-sm">Merchant<input className="mt-1 w-full rounded border border-slate-300 p-2" onChange={(event) => setMerchant(event.target.value)} placeholder="Search merchant" value={merchant} /></label></div>
    {error && <p className="mt-5 rounded bg-red-50 p-3 text-red-700">{error}</p>}
    <div className="mt-6 grid gap-6 lg:grid-cols-[300px_1fr]"><section className="rounded-xl border border-slate-200 bg-white p-5"><h2 className="font-bold">Spend by category</h2>{report?.groups.length ? <ul className="mt-4 space-y-3">{report.groups.map((group) => <li className="flex justify-between gap-3" key={`${group.name}-${group.currency}`}><span className="capitalize text-slate-600">{group.name.replaceAll("_", " ")}</span><strong>{money(group.total_cents, group.currency)}</strong></li>)}</ul> : <p className="mt-4 text-sm text-slate-500">No confirmed spending yet.</p>}</section><section className="overflow-hidden rounded-xl border border-slate-200 bg-white"><div className="border-b border-slate-100 p-5"><h2 className="font-bold">Confirmed history</h2></div><div className="overflow-x-auto"><table className="w-full min-w-[650px] text-left text-sm"><thead className="bg-slate-50 text-slate-500"><tr><th className="p-4">Date</th><th>Merchant</th><th>Item</th><th>Category</th><th className="pr-4 text-right">Amount</th></tr></thead><tbody>{history?.items.map((item) => <tr className="border-t border-slate-100" key={item.line_item_id}><td className="p-4 text-slate-500">{item.receipt_date ?? "—"}</td><td>{item.merchant ?? "Unknown merchant"}</td><td>{item.description}</td><td className="capitalize">{item.category?.replaceAll("_", " ") ?? "Uncategorized"}</td><td className="pr-4 text-right font-semibold">{money(item.amount_cents, item.currency)}</td></tr>)}</tbody></table></div></section></div>
  </div></main>;
}
