"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { seedDemo } from "@/lib/api";

export function DemoSeedButton() {
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  async function createDemo() {
    setLoading(true);
    try {
      const result = await seedDemo();
      router.push(`/expedientes/${result.id}`);
      router.refresh();
    } finally {
      setLoading(false);
    }
  }

  return <button className="button primary" onClick={createDemo} disabled={loading}>{loading ? "Preparando…" : "Cargar expediente demo"}</button>;
}

