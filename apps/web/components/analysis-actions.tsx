"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { API_URL } from "@/lib/api";

export function AnalyzeCaseButton({ caseId }: { caseId: string }) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  async function run() {
    setLoading(true); setMessage("");
    try {
      const response = await fetch(`${API_URL}/cases/${caseId}/analyze`, { method: "POST" });
      const raw = await response.text();
      const payload = raw ? JSON.parse(raw) : {};
      if (!response.ok) throw new Error(payload.detail ?? "No se pudo analizar.");
      if (payload.status === "NEEDS_CONFIGURATION") {
        setMessage(payload.error_message ?? "Falta configurar la ficha de uno o más CMID.");
      } else if (payload.status === "FAILED") {
        setMessage(payload.error_message ?? "El análisis no pudo completarse.");
      } else {
        setMessage("Análisis actualizado.");
      }
      router.refresh();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Error de análisis."); }
    finally { setLoading(false); }
  }
  return <div className="analysis-action"><button className="button primary" onClick={run} disabled={loading}>{loading ? "Analizando archivos…" : "Analizar con IA"}</button>{message && <small>{message}</small>}</div>;
}

export function AnalyzeAllButton() {
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  async function run() {
    setLoading(true); setMessage("");
    try {
      const response = await fetch(`${API_URL}/analysis/run`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ case_ids: [], force: false }) });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "No se pudo iniciar.");
      setMessage(`${payload.queued} expediente(s) enviados. Actualiza en unos minutos.`);
    } catch (error) { setMessage(error instanceof Error ? error.message : "Error al iniciar."); }
    finally { setLoading(false); }
  }
  return <div className="analysis-action global"><button className="button primary" onClick={run} disabled={loading}>{loading ? "Enviando…" : "Analizar pendientes con IA"}</button>{message && <small>{message}</small>}</div>;
}
