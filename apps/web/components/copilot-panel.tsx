"use client";

import { FormEvent, useState } from "react";
import { API_URL } from "@/lib/api";
import { Citation } from "@/lib/types";

type Answer = { answer: string; limitation: string; citations: Citation[]; sources?: Array<{ artifact_id: string; filename: string; excerpt: string }> };

export function CopilotPanel({ caseId }: { caseId: string }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (question.trim().length < 3) return;
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${API_URL}/cases/${caseId}/queries`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }) });
      const payload = await response.json();
      if (response.ok) setAnswer(payload);
      else setError(payload.detail ?? "No se pudo consultar el expediente.");
    } catch {
      setError("No se pudo conectar con el servicio de IA.");
    } finally { setLoading(false); }
  }

  return (
    <section className="copilot-panel">
      <div className="copilot-title"><span>✦</span><div><h2>Consultar evidencias</h2><p>Respuestas limitadas al expediente</p></div></div>
      <div className="suggestions">
        {["¿Dónde aparece pensamiento crítico?", "Muéstrame la retroalimentación", "¿Qué señala la reflexión docente?"].map((text) => <button key={text} onClick={() => setQuestion(text)}>{text}</button>)}
      </div>
      {error && <div className="copilot-error">{error}</div>}
      {answer && <div className="answer"><strong>Respuesta asistida</strong><p>{answer.answer}</p>{answer.citations.slice(0, 2).map((c) => <blockquote key={c.id}>“{c.quote}”</blockquote>)}{answer.sources?.slice(0, 3).map((source) => <a className="answer-source" key={source.artifact_id} href={`/api/backend/artifacts/${source.artifact_id}/content`} target="_blank">Fuente: {source.filename} ↗</a>)}<small>{answer.limitation}</small></div>}
      <form onSubmit={submit}><label htmlFor="question">Pregunta sobre este expediente</label><textarea id="question" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Busca una evidencia…" rows={3} /><button className="button primary" disabled={loading}>{loading ? "Buscando…" : "Consultar expediente"}</button></form>
    </section>
  );
}
