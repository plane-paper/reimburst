"use client";

import { ReceiptCapture } from "@/components/receipt-capture";
import { useState, type ReactNode } from "react";

type IconName = "building" | "camera" | "chart" | "chevron" | "document" | "home" | "receipt" | "settings" | "user";

function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, ReactNode> = {
    building: <><path d="M4 20h16M6 20V6l6-3 6 3v14M9 20v-4h6v4M9 9h.01M15 9h.01M9 12h.01M15 12h.01" /></>,
    camera: <><path d="M4 8h3l2-3h6l2 3h3v11H4z" /><circle cx="12" cy="13" r="3" /></>,
    chart: <><path d="M4 20V10M10 20V4M16 20v-7M22 20H2" /></>,
    chevron: <path d="m9 18 6-6-6-6" />,
    document: <><path d="M6 3h9l4 4v14H6z" /><path d="M15 3v5h5M9 13h6M9 17h6" /></>,
    home: <><path d="m3 11 9-8 9 8v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" /></>,
    receipt: <><path d="M7 3h10v18l-2-1.5-3 1.5-3-1.5L7 21z" /><path d="M10 8h4M10 12h4M10 16h2" /></>,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.1 2.1-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.56v.1h-3v-.1A1.7 1.7 0 0 0 10.7 18.6a1.7 1.7 0 0 0-1.88.34l-.06.06-2.1-2.1.06-.06A1.7 1.7 0 0 0 7.06 15a1.7 1.7 0 0 0-1.56-1.03h-.1v-3h.1A1.7 1.7 0 0 0 7.06 9.94a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.1-2.1.06.06a1.7 1.7 0 0 0 1.88.34 1.7 1.7 0 0 0 1.03-1.56v-.1h3v.1a1.7 1.7 0 0 0 1.03 1.56 1.7 1.7 0 0 0 1.88-.34l.06-.06 2.1 2.1-.06.06a1.7 1.7 0 0 0-.34 1.88 1.7 1.7 0 0 0 1.56 1.03h.1v3h-.1A1.7 1.7 0 0 0 19.4 15Z" /></>,
    user: <><circle cx="12" cy="8" r="4" /><path d="M4 21c.8-4 3.4-6 8-6s7.2 2 8 6" /></>,
  };
  return <svg aria-hidden="true" className="shrink-0" fill="none" height={size} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" viewBox="0 0 24 24" width={size}>{paths[name]}</svg>;
}

const activity = [
  ["Aug 24, 2025", "Starbucks", "Coffee & snacks", "Food", "$5.47", "Pending"],
  ["Aug 22, 2025", "Marriott Hotel", "Hotel", "Travel", "$342.18", "Approved"],
  ["Aug 20, 2025", "Uber", "Transport", "Transport", "$23.76", "Approved"],
];

const categoryStyles: Record<string, string> = { Food: "bg-amber-50 text-amber-700", Travel: "bg-blue-50 text-blue-700", Transport: "bg-violet-50 text-violet-700" };

export function Dashboard() {
  const [captureOpen, setCaptureOpen] = useState(false);
  const [mode, setMode] = useState<"organization" | "individual">("organization");

  return <main className="min-h-screen bg-[#f8faff] text-[#14213d] lg:flex">
    <aside className="border-b border-slate-200 bg-white px-5 py-5 lg:fixed lg:inset-y-0 lg:w-60 lg:border-r lg:border-b-0 lg:px-4">
      <div className="flex items-center gap-3 px-2"><div className="grid size-9 place-items-center rounded-lg bg-[#2563eb] text-white shadow-sm"><Icon name="receipt" /></div><span className="text-[15px] font-bold leading-tight">Reimbursement<br />Automation</span></div>
      <nav aria-label="Main navigation" className="mt-8 flex gap-1 overflow-x-auto lg:flex-col">
        {[["Home", "home"], ["Receipts", "receipt"], ["Spending", "chart"], ["Requests", "document"], ["Reports", "chart"], ["Settings", "settings"]].map(([label, icon]) => <button className={`flex shrink-0 items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition ${label === "Home" ? "bg-blue-50 text-[#2563eb]" : "text-slate-500 hover:bg-slate-50 hover:text-slate-800"}`} key={label} type="button"><Icon name={icon as IconName} /> {label}{label !== "Home" && <span className="sr-only"> (available in a later phase)</span>}</button>)}
      </nav>
    </aside>
    <section className="min-w-0 flex-1 lg:ml-60">
      <header className="flex h-[72px] items-center justify-end border-b border-slate-200 bg-white px-5 sm:px-10"><button className="flex items-center gap-3 rounded-lg px-2 py-1 text-sm font-medium text-slate-600 hover:bg-slate-50" type="button"><span className="grid size-10 place-items-center rounded-full bg-[#2563eb] text-xs font-bold text-white">RS</span><span className="hidden sm:inline">Richard Su</span><span aria-hidden="true">⌄</span></button></header>
      <div className="mx-auto max-w-[1400px] px-5 py-9 sm:px-10">
        <div className="mb-8"><h1 className="text-3xl font-bold tracking-tight sm:text-[34px]">Good afternoon, Richard</h1><p className="mt-2 text-base text-slate-500">Capture receipts, track your spending, and get reimbursed — all in one place.</p></div>
        <div className="grid gap-4 lg:grid-cols-2"><ModeCard active={mode === "organization"} icon="building" onClick={() => setMode("organization")} subtitle="Submit reimbursement requests through your company’s approval workflow." title="Organization Mode" /><ModeCard active={mode === "individual"} icon="user" onClick={() => setMode("individual")} subtitle="Track your personal spending and create outbound reimbursement requests." title="Individual Mode" /></div>
        <div className="mt-8 grid gap-4 lg:grid-cols-[1.15fr_1fr_1fr]"><button className="group flex items-center justify-between rounded-xl bg-[#2563eb] px-6 py-5 text-left text-white shadow-[0_8px_18px_rgba(37,99,235,.20)] transition hover:bg-blue-700" onClick={() => setCaptureOpen(true)} type="button"><span className="flex items-center gap-4"><Icon name="camera" size={28} /><span><span className="block font-semibold">Scan Receipt</span><span className="mt-1 block text-sm text-blue-100">Take a photo or upload</span></span></span><Icon name="chevron" /></button><a className="flex items-center justify-between rounded-xl border border-slate-200 bg-white px-6 py-5 text-left text-slate-700 shadow-sm transition hover:border-blue-200 hover:bg-blue-50/30" href="/spending"><span className="flex items-center gap-4"><span className="text-slate-500"><Icon name="document" size={26} /></span><span><span className="block font-semibold">View Reports</span><span className="mt-1 block text-sm text-slate-400">Personal spending history</span></span></span><span className="text-slate-400"><Icon name="chevron" /></span></a><PreviewAction icon="receipt" subtitle="Available in P4" title="My Requests" /></div>
        <div className="mt-8 grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
          <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6"><div className="flex items-center justify-between"><div><h2 className="text-lg font-bold">Recent Activity</h2><p className="mt-1 text-xs text-slate-400">Preview data — live receipt history arrives in P3/P4.</p></div><button className="text-sm font-semibold text-[#2563eb]" type="button">View all <span aria-hidden="true">→</span></button></div><div className="mt-5 overflow-x-auto"><table className="w-full min-w-[660px] text-left text-sm"><thead className="border-b border-slate-100 text-xs font-medium text-slate-400"><tr><th className="pb-3">Date</th><th className="pb-3">Description</th><th className="pb-3">Category</th><th className="pb-3">Amount</th><th className="pb-3">Status</th></tr></thead><tbody>{activity.map(([date, merchant, description, category, amount, status]) => <tr className="border-b border-slate-100 last:border-0" key={merchant}><td className="py-4 text-slate-500">{date}</td><td className="py-4"><span className="block font-semibold text-slate-700">{merchant}</span><span className="text-xs text-slate-400">{description}</span></td><td className="py-4"><span className={`rounded-full px-2.5 py-1 text-xs font-medium ${categoryStyles[category]}`}>{category}</span></td><td className="py-4 font-semibold text-slate-700">{amount}<span className="ml-1 text-xs font-normal text-slate-400">CAD</span></td><td className="py-4"><span className={`rounded-full px-2.5 py-1 text-xs font-medium ${status === "Pending" ? "bg-amber-50 text-amber-700" : "bg-emerald-50 text-emerald-700"}`}>{status}</span></td></tr>)}</tbody></table></div></section>
          <aside className="rounded-xl border border-slate-200 bg-white p-7 shadow-sm"><div className="grid size-16 place-items-center rounded-2xl bg-blue-50 text-[#2563eb]"><Icon name="receipt" size={32} /></div><h2 className="mt-7 text-xl font-bold">Turn receipts into reimbursements</h2><p className="mt-3 leading-6 text-slate-500">Snap a photo and we’ll extract the details so you can review them before creating a reimbursement request.</p><div className="mt-7 border-t border-slate-100 pt-5"><p className="text-sm font-semibold">P1 status</p><p className="mt-1 text-sm text-slate-500">Receipt capture and extraction are ready to try.</p><button className="mt-4 text-sm font-semibold text-[#2563eb]" onClick={() => setCaptureOpen(true)} type="button">Scan your first receipt →</button></div></aside>
        </div>
      </div>
    </section>
    {captureOpen && <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-950/35 p-4 backdrop-blur-sm sm:p-8"><div aria-modal="true" className="mx-auto mt-4 max-w-2xl" role="dialog"><div className="mb-3 flex justify-end"><button aria-label="Close receipt capture" className="rounded-full bg-white p-2 text-slate-500 shadow-sm hover:text-slate-900" onClick={() => setCaptureOpen(false)} type="button">✕</button></div><ReceiptCapture /></div></div>}
  </main>;
}

function ModeCard({ active, icon, onClick, subtitle, title }: { active: boolean; icon: IconName; onClick: () => void; subtitle: string; title: string }) {
  return <button className={`relative flex items-center gap-5 rounded-xl border p-6 text-left shadow-sm transition ${active ? "border-[#2563eb] bg-blue-50/50 ring-1 ring-[#2563eb]" : "border-slate-200 bg-white hover:border-blue-200"}`} onClick={onClick} type="button"><span className="grid size-14 place-items-center rounded-full bg-blue-100 text-[#2563eb]"><Icon name={icon} size={28} /></span><span className="min-w-0"><span className="block text-lg font-bold">{title}</span><span className="mt-1 block max-w-md text-sm leading-5 text-slate-500">{subtitle}</span>{active && <span className="mt-3 inline-block rounded-full bg-blue-100 px-2 py-1 text-xs font-semibold text-[#2563eb]">You’re in this mode</span>}</span><span className="ml-auto text-[#2563eb]"><Icon name="chevron" /></span></button>;
}

function PreviewAction({ icon, subtitle, title }: { icon: IconName; subtitle: string; title: string }) {
  return <button aria-label={`${title} (${subtitle})`} className="flex items-center justify-between rounded-xl border border-slate-200 bg-white px-6 py-5 text-left text-slate-700 shadow-sm transition hover:border-blue-200 hover:bg-blue-50/30" type="button"><span className="flex items-center gap-4"><span className="text-slate-500"><Icon name={icon} size={26} /></span><span><span className="block font-semibold">{title}</span><span className="mt-1 block text-sm text-slate-400">{subtitle}</span></span></span><span className="text-slate-400"><Icon name="chevron" /></span></button>;
}
