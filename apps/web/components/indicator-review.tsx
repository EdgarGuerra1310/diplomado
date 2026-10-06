"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { API_URL } from "@/lib/api";
import { Artifact, Indicator } from "@/lib/types";

const decisions = [
  ["CONFIRMED", "Confirmar"],
  ["INSUFFICIENT_EVIDENCE", "Evidencia insuficiente"],
  ["DISMISSED", "Descartar"],
] as const;

function locator(indicator: Indicator) {
  const citation = indicator.citations[0];
  if (!citation) return "Sin localizador";
  if (citation.start_seconds != null) {
    const minute = Math.floor(citation.start_seconds / 60);
    const second = String(citation.start_seconds % 60).padStart(2, "0");
    return `Video · ${minute}:${second}`;
  }
  return `Página ${citation.page ?? "—"} · párrafo ${citation.paragraph ?? "—"}`;
}

export function IndicatorReview({ indicator, artifacts }: { indicator: Indicator; artifacts: Artifact[] }) {
  const [review, setReview] = useState(indicator.reviews.at(-1));
  const [saving, setSaving] = useState(false);
  const router = useRouter();
  const citation = indicator.citations[0];
  const artifact = artifacts.find((item) => item.id === citation?.artifact_id);

  async function decide(decision: string) {
    setSaving(true);
    try {
      const response = await fetch(`${API_URL}/indicator-results/${indicator.id}/reviews`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision, reviewer_id: "especialista-demo" }),
      });
      if (response.ok) {
        setReview(await response.json());
        router.refresh();
      }
    } finally { setSaving(false); }
  }

  return (
    <article className="indicator-card">
      <div className="indicator-top"><span className="dimension">{indicator.dimension}</span><span className="confidence">Confianza técnica {Math.round(indicator.confidence * 100)}%</span></div>
      <h3>{indicator.label}</h3>
      <p>{indicator.explanation}</p>
      {citation && <blockquote><span>“{citation.quote}”</span><small>{artifact?.filename} · {locator(indicator)}</small></blockquote>}
      <div className="decision-row">
        {decisions.map(([value, label]) => <button key={value} disabled={saving} onClick={() => decide(value)} className={review?.decision === value ? "selected" : ""}>{label}</button>)}
      </div>
      {review && <p className="reviewed-label">✓ Decisión humana registrada: {review.decision.replaceAll("_", " ")}</p>}
    </article>
  );
}
