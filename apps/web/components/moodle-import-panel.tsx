"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { API_URL } from "@/lib/api";
import { ActivityCriteriaEditor } from "@/components/activity-criteria-editor";

type MoodleConfig = {
  configured: boolean;
  base_url: string;
  default_course_id?: number | null;
  default_cm_id?: number | null;
};

type MoodlePreview = {
  site_name: string;
  course_id: number;
  course_name: string;
  selected_cm_id?: number | null;
  selected_cm_ids: number[];
  requested_usernames: string[];
  matched_user_count: number;
  activities: Array<{ assignment_id: number; cm_id: number; name: string; submission_count: number; file_count: number }>;
  submission_count: number;
  file_count: number;
  warnings: string[];
};

type MoodleImportResult = {
  cases_created: number;
  cases_updated: number;
  artifacts_created: number;
  case_ids: string[];
  warnings: string[];
};

export function MoodleImportPanel() {
  const router = useRouter();
  const [config, setConfig] = useState<MoodleConfig | null>(null);
  const [courseId, setCourseId] = useState("");
  const [cmIds, setCmIds] = useState("");
  const [measurement, setMeasurement] = useState<"LB" | "LF">("LB");
  const [usernames, setUsernames] = useState("");
  const [preview, setPreview] = useState<MoodlePreview | null>(null);
  const [result, setResult] = useState<MoodleImportResult | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState<"preview" | "import" | "">("");

  useEffect(() => {
    fetch(`${API_URL}/moodle/config`)
      .then((response) => response.json())
      .then((data: MoodleConfig) => {
        setConfig(data);
        if (data.default_course_id) setCourseId(String(data.default_course_id));
        if (data.default_cm_id) setCmIds(String(data.default_cm_id));
      })
      .catch(() => setError("No se pudo leer la configuración de Moodle."));
  }, []);

  function scopeBody() {
    const selectedUsernames = usernames
      .split(/[\s,;]+/)
      .map((value) => value.trim())
      .filter(Boolean);
    return {
      course_id: courseId ? Number(courseId) : null,
      cm_id: null,
      cm_ids: cmIds.split(/[\s,;]+/).map(Number).filter((value) => Number.isInteger(value) && value > 0),
      usernames: selectedUsernames,
    };
  }

  async function request(path: string, body: object) {
    const response = await fetch(`${API_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail ?? "Moodle devolvió un error.");
    return data;
  }

  async function handlePreview(event: FormEvent) {
    event.preventDefault();
    setError("");
    setResult(null);
    setLoading("preview");
    try {
      setPreview(await request("/moodle/preview", scopeBody()));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "No se pudo consultar Moodle.");
    } finally {
      setLoading("");
    }
  }

  async function handleImport() {
    setError("");
    setLoading("import");
    try {
      const imported = await request("/moodle/import", { ...scopeBody(), measurement });
      setResult(imported);
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "No se pudo importar Moodle.");
    } finally {
      setLoading("");
    }
  }

  return (
    <section className="moodle-panel" aria-labelledby="moodle-import-title">
      <div className="moodle-panel-heading">
        <div>
          <p className="eyebrow">Origen de evidencias</p>
          <h2 id="moodle-import-title">Importar desde Moodle</h2>
          <p>Use el ID del aula completa (courseid) o limite la extracción a una tarea (cmid).</p>
        </div>
        <span className={config?.configured ? "connection connected" : "connection"}>
          {config?.configured ? "Configurado" : "Falta configurar .env"}
        </span>
      </div>

      <form className="moodle-form" onSubmit={handlePreview}>
        <label>Course ID<input type="number" min="1" value={courseId} onChange={(event) => setCourseId(event.target.value)} placeholder="Ej. 2741" /></label>
        <label>CM ID <span>(uno o varios)</span><input value={cmIds} onChange={(event) => setCmIds(event.target.value)} placeholder="Ej. 501, 502, 503, 504" /></label>
        <label>Medición<select value={measurement} onChange={(event) => setMeasurement(event.target.value as "LB" | "LF")}><option value="LB">Línea Base</option><option value="LF">Línea Final</option></select></label>
        <button className="button secondary" disabled={loading !== "" || (!courseId && !cmIds)}>{loading === "preview" ? "Consultando…" : "Consultar aula"}</button>
        <label className="username-field">Username de docentes <span>(recomendado para el piloto; separados por coma, espacio o salto de línea)</span><textarea rows={3} value={usernames} onChange={(event) => setUsernames(event.target.value)} placeholder={"docente01, docente02\ndocente03"} /></label>
      </form>

      {error && <p className="moodle-error">{error}</p>}
      {preview && (
        <div className="moodle-preview">
          <div><strong>{preview.course_name}</strong><span>{preview.site_name} · courseid {preview.course_id}{preview.selected_cm_ids.length ? ` · cmid ${preview.selected_cm_ids.join(", ")}` : ""}{preview.requested_usernames.length ? ` · ${preview.matched_user_count}/${preview.requested_usernames.length} usuarios encontrados` : " · aula completa"}</span></div>
          <div className="preview-numbers"><span><strong>{preview.activities.length}</strong> tareas</span><span><strong>{preview.submission_count}</strong> entregas</span><span><strong>{preview.file_count}</strong> archivos</span></div>
          <button type="button" className="button primary" onClick={handleImport} disabled={loading !== ""}>{loading === "import" ? "Importando…" : "Crear expedientes"}</button>
        </div>
      )}
      {preview && <ActivityCriteriaEditor courseId={preview.course_id} activities={preview.activities} />}
      {result && (
        <div className="import-success"><span>✓ {result.cases_created} expedientes creados, {result.cases_updated} actualizados y {result.artifacts_created} archivos registrados.</span>{result.case_ids[0] && <Link href={`/expedientes/${result.case_ids[0]}`}>Abrir primer expediente →</Link>}</div>
      )}
    </section>
  );
}
