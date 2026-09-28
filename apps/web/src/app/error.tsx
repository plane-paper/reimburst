"use client";

export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <main className="grid min-h-screen place-items-center bg-[#f8faff] p-5 text-[#14213d]"><section className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-7 text-center shadow-sm"><h1 className="text-xl font-bold">Something went wrong</h1><p className="mt-3 text-sm leading-6 text-slate-500">Your information is safe. Try loading this page again.</p><button className="mt-6 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white" onClick={reset} type="button">Try again</button></section></main>;
}
