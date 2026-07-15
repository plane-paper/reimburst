import { HealthCheck } from "@/components/health-check";

export default function Home() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-zinc-50 font-sans dark:bg-black">
      <h1 className="text-2xl font-semibold text-black dark:text-zinc-50">
        Reimburse
      </h1>
      <HealthCheck />
    </div>
  );
}
