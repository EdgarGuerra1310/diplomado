"use client";

import { useEffect, useState } from "react";
import { API_URL } from "@/lib/api";

type Activity = { cm_id: number; name: string };
type Draft = { description: string; expected_evidence: string; review_criteria: string };

export function ActivityCriteriaEditor({ courseId, activities }: { courseId: number; activities: Activity[] }) {
  const [drafts, setDrafts] = useState<Record<number, Draft>>({});
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetch(`${API_URL}/activity-criteria?course_id=${courseId}`)
      .then((response) => response.json())
      .then((rows: Array<{ cm_id: number; description: string; expected_evidence: string; review_criteria: string[] }>) => {
        const existing = new Map(rows.map((row) => [row.cm_id, row]));
        setDrafts(Object.fromEntries(activities.map((activity) => {
          const row = existing.get(activity.cm_id);
          return [activity.cm_id, { description: row?.description ?? "", expected_evidence: row?.expected_evidence ?? "", review_criteria: row?.review_criteria.join("\n") ?? "" }];
        })));
      })
      .catch(() => setMessage("No se pudieron cargar las fichas existentes."));
  }, [courseId, activities]);

  function update(cmId: number, key: keyof Draft, value: string) {
    setDrafts((current) => ({ ...current, [cmId]: { ...current[cmId], [key]: value } }));
  }

  async function save() {
    setSaving(true); setMessage("");
    try {
      for (const activity of activities) {
        const draft = drafts[activity.cm_id];
        if (!draft?.description.trim() || !draft.expected_evidence.trim() || !draft.review_criteria.trim()) throw new Error(`Completa la ficha del CMID ${activity.cm_id}.`);
        const response = await fetch(`${API_URL}/activity-criteria/${activity.cm_id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ course_id: courseId, cm_id: activity.cm_id, activity_name: activity.name, description: draft.description, expected_evidence: draft.expected_evidence, review_criteria: draft.review_criteria.split("\n").map((value) => value.trim()).filter(Boolean) }) });
        const raw = await response.text();
        let payload: { detail?: string } = {};
        if (raw) {
          try { payload = JSON.parse(raw) as { detail?: string }; }
          catch { payload = {}; }
        }
        if (!response.ok) throw new Error(payload.detail ?? `No se guardó el CMID ${activity.cm_id} (HTTP ${response.status}).`);
      }
      setMessage("Fichas guardadas. La IA utilizará estos criterios por CMID.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "No se pudieron guardar las fichas."); }
    finally { setSaving(false); }
  }

  return <section className="criteria-editor"><div className="criteria-heading"><div><strong>Ficha de revisión por CMID</strong><span>Define qué representa cada actividad y qué debe validar la IA.</span></div><button type="button" className="button secondary" onClick={save} disabled={saving}>{saving ? "Guardando…" : "Guardar criterios"}</button></div><div className="criteria-grid">{activities.map((activity) => <article key={activity.cm_id}><div><b>CMID {activity.cm_id}</b><strong>{activity.name}</strong></div><label>Descripción de la actividad<textarea rows={3} value={drafts[activity.cm_id]?.description ?? ""} onChange={(event) => update(activity.cm_id, "description", event.target.value)} placeholder="Propósito y relación con la secuencia pedagógica…" /></label><label>Evidencia esperada<textarea rows={2} value={drafts[activity.cm_id]?.expected_evidence ?? ""} onChange={(event) => update(activity.cm_id, "expected_evidence", event.target.value)} placeholder="Documento, contenido mínimo, producto esperado…" /></label><label>Criterios de revisión <span>(uno por línea)</span><textarea rows={4} value={drafts[activity.cm_id]?.review_criteria ?? ""} onChange={(event) => update(activity.cm_id, "review_criteria", event.target.value)} placeholder={"Corresponde a la actividad\nPresenta información completa\nMantiene coherencia con el CMID anterior"} /></label></article>)}</div>{message && <p className="criteria-message">{message}</p>}</section>;
}
