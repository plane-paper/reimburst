import { ReceiptCapture } from "@/components/receipt-capture";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-zinc-50 p-6 font-sans">
      <div className="mb-8 w-full max-w-2xl">
        <p className="text-sm font-semibold tracking-wide text-zinc-600">REIMBURST</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-zinc-950">Capture an expense</h1>
        <p className="mt-2 text-zinc-600">Upload a receipt and we’ll extract its details for you to review.</p>
      </div>
      <ReceiptCapture />
    </main>
  );
}
