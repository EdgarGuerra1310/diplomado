"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { API_URL } from "@/lib/api";
import type { CaseDetail } from "@/lib/types";

export function RubricReview({ assessments }: { assessments: CaseDetail["rubric_assessments"] }) {
  const router = useRouter();
  const [saving, setSaving] = useState("");
  const [error, setError] = useState("");
  const cmIds = [...new Set(assessments.map((item) => item.cm_id))].sort((a, b) => a - b);
  async function validate(id: string, level: number) {
    setSaving(id); setError("");
    try {
      const response = await fetch(`${API_URL}/rubric-assessments/${id}/validation`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ validated_level: level }) });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "No se pudo validar.");
      router.refresh();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "No se pudo validar."); }
    finally { setSaving(""); }
  }
  if (!assessments.length) return <div className="empty compact">La rúbrica aparecerá después de analizar el expediente con IA.</div>;
  return <div className="rubric-review">{error && <p className="rubric-error">{error}</p>}{cmIds.map((cmId) => <section key={cmId}><div className="rubric-cmid"><strong>CMID {cmId}</strong><span>Propuesta IA pendiente de validación humana</span></div><div className="table-wrap"><table><thead><tr><th>Dimensión y criterio</th><th>Propuesta IA</th><th>Justificación</th><th>Validar nivel</th></tr></thead><tbody>{assessments.filter((item) => item.cm_id === cmId).sort((a, b) => a.criterion_ref.display_order - b.criterion_ref.display_order).map((item) => { const effective = item.validated_level ?? item.proposed_level; const descriptor = item.criterion_ref[`level_${effective}` as "level_1" | "level_2" | "level_3" | "level_4"]; return <tr key={item.id}><td><strong>{item.criterion_ref.dimension}</strong><small>{item.criterion_ref.criterion}</small></td><td><span className={`rubric-level level-${effective}`}>Nivel {effective}</span><small>{descriptor}</small><small>{Math.round(item.confidence * 100)}% confianza IA</small></td><td>{item.justification}</td><td><div className="level-buttons">{[1, 2, 3, 4].map((level) => <button key={level} className={effective === level ? "selected" : ""} onClick={() => validate(item.id, level)} disabled={saving === item.id}>{level}</button>)}</div><small>{item.validation_status === "VALIDATED_BY_HUMAN" ? "Validado por especialista" : "Pendiente"}</small></td></tr>; })}</tbody></table></div></section>)}</div>;
}
