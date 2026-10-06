"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { API_URL } from "@/lib/api";

export function RemoveCmidButton({ caseId, cmId }: { caseId: string; cmId: number }) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  async function remove() {
    if (!window.confirm(`¿Quitar el CMID ${cmId} de este expediente? No se eliminará nada en Moodle.`)) return;
    setLoading(true); setError("");
    try {
      const response = await fetch(`${API_URL}/cases/${caseId}/activities/${cmId}`, { method: "DELETE" });
      const raw = await response.text();
      const payload = raw ? JSON.parse(raw) : {};
      if (!response.ok) throw new Error(payload.detail ?? `No se pudo quitar el CMID (HTTP ${response.status}).`);
      router.refresh();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "No se pudo quitar el CMID."); }
    finally { setLoading(false); }
  }
  return <div className="remove-cmid"><button type="button" onClick={remove} disabled={loading}>{loading ? "Quitando…" : "Quitar CMID"}</button>{error && <small>{error}</small>}</div>;
}
