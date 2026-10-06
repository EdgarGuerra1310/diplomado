import Link from "next/link";
import { notFound } from "next/navigation";
import { CopilotPanel } from "@/components/copilot-panel";
import { AnalyzeCaseButton } from "@/components/analysis-actions";
import { RemoveCmidButton } from "@/components/remove-cmid-button";
import { RubricReview } from "@/components/rubric-review";
import { IndicatorReview } from "@/components/indicator-review";
import { getCase } from "@/lib/api";

function duration(seconds?: number | null) {
  if (!seconds) return null;
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")} min`;
}

export default async function CasePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let data;
  try { data = await getCase(id); } catch { notFound(); }
  const reviewed = data.indicators.filter((item) => item.reviews.length > 0).length;
  const artifactById = new Map(data.artifacts.map((artifact) => [artifact.id, artifact]));
  const identityName = data.identity?.full_name ?? data.identity?.username ?? data.teacher_code;

  return (
    <div className="page-shell detail-page">
      <Link href="/" className="back-link">← Volver a expedientes</Link>
      <section className="case-header">
        <div>
          <p className="eyebrow">Expediente {data.measurement}</p>
          <h1>{identityName}</h1>
          <p>{data.identity?.username ? `@${data.identity.username} · ` : ""}{data.teacher_code}</p>
          <div className="meta-row"><span>{data.course_name}</span>{data.region && <span>{data.region}</span>}{data.ugel && <span>{data.ugel}</span>}{data.education_level && <span>{data.education_level}</span>}</div>
        </div>
        <div className="review-progress"><strong>{reviewed}/{data.indicators.length}</strong><span>señales revisadas</span><div><i style={{ width: `${(reviewed / Math.max(data.indicators.length, 1)) * 100}%` }} /></div></div>
      </section>

      <div className="notice"><strong>Lectura asistida</strong><span>Este resumen fue generado por IA. No constituye evaluación ni calificación.</span><AnalyzeCaseButton caseId={data.id} /></div>

      <div className="detail-grid">
        <div className="main-column">
          <section className="panel summary-panel"><p className="eyebrow">Resumen ejecutivo</p><h2>Visión inicial del expediente</h2><p className="summary-copy">{data.executive_summary ?? "El expediente aún no tiene resumen."}</p></section>

          <section className="panel ai-findings-panel">
            <div className="panel-title"><div><h2>Hallazgos automáticos</h2><p>Pertinencia, integridad, patrones y similitudes para revisión humana.</p></div><span className={`risk-badge risk-${(data.ai_analysis?.risk_level ?? "unknown").toLowerCase()}`}>{data.ai_analysis?.risk_level ?? "SIN ANALIZAR"}</span></div>
            {!data.ai_analysis ? <div className="empty compact">Ejecuta el análisis para revisar el contenido de las entregas.</div> : data.ai_analysis.status === "FAILED" ? <div className="empty compact"><strong>El análisis falló.</strong><p>{data.ai_analysis.error_message}</p></div> : <>
              <div className="cluster-summary"><span>Clúster temático</span><strong>{data.ai_analysis.cluster_label ?? "Sin clasificar"}</strong><small>{data.ai_analysis.analyzed_at ? `Actualizado ${new Date(data.ai_analysis.analyzed_at).toLocaleString("es-PE")}` : data.ai_analysis.status}</small></div>
              <div className="finding-list">{data.ai_analysis.findings.map((finding, index) => <article className={`finding finding-${finding.severity.toLowerCase()}`} key={`${finding.type}-${index}`}><div><span>{finding.type.replaceAll("_", " ")}{finding.cm_id ? ` · CMID ${finding.cm_id}` : ""}{finding.validation_status ? ` · ${finding.validation_status}` : ""}</span><strong>{finding.title}</strong><p>{finding.detail}</p>{(finding.score != null || finding.similarity_score != null) && <div className="score-row">{finding.score != null && <span>Puntaje <b>{Math.round(finding.score)}/100</b></span>}{finding.similarity_score != null && <span>Similitud <b>{Math.round(finding.similarity_score)}%</b></span>}</div>}</div><b>{Math.round(finding.confidence * 100)}%</b></article>)}{data.ai_analysis.findings.length === 0 && <div className="empty compact">No se generaron alertas.</div>}</div>
            </>}
          </section>

          <section className="panel rubric-panel">
            <div className="panel-title"><div><h2>Rúbrica del Marco de Buen Desempeño Docente</h2><p>Valoración propuesta por IA para cada CMID; el especialista confirma o corrige el nivel.</p></div><span className="soft-badge">6 dimensiones</span></div>
            <RubricReview assessments={data.rubric_assessments} />
          </section>

          <section className="panel">
            <div className="panel-title"><div><h2>Historial de entregas por actividad</h2><p>Relación Moodle: docente → cmid → intento → archivos.</p></div><span className="soft-badge">{data.moodle_submissions.length} entregas</span></div>
            {data.moodle_submissions.length === 0 ? <div className="empty compact"><p>Este expediente no proviene todavía de una importación Moodle.</p></div> : (
              <div className="delivery-list">
                {[...data.moodle_submissions].sort((a, b) => a.cm_id - b.cm_id).map((delivery) => (
                  <article className="delivery" key={delivery.id}>
                    <div className="delivery-heading"><div><span className="dimension">CMID {delivery.cm_id}</span><h3>{delivery.activity_name}</h3><p>Intento {delivery.attempt_number + 1} · submission {delivery.submission_id}{delivery.time_modified ? ` · ${new Date(delivery.time_modified).toLocaleString("es-PE")}` : ""}</p></div><div className="delivery-actions"><span className={`delivery-status ${delivery.status.toLowerCase()}`}>{delivery.status}</span><RemoveCmidButton caseId={data.id} cmId={delivery.cm_id} /></div></div>
                    <div className="delivery-files">
                      {delivery.artifact_ids.length === 0 ? <span className="no-files">Sin archivos asociados</span> : delivery.artifact_ids.map((artifactId) => {
                        const artifact = artifactById.get(artifactId);
                        if (!artifact) return null;
                        return <a key={artifact.id} href={`/api/backend/artifacts/${artifact.id}/content`} target="_blank" rel="noreferrer"><span>{artifact.mime_type.startsWith("video") ? "▶" : "DOC"}</span><div><strong>{artifact.filename}</strong><small>{artifact.evidence_type.replaceAll("_", " ")}</small></div><b>Ver archivo ↗</b></a>;
                      })}
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>

          <section className="panel">
            <div className="panel-title"><div><h2>Señales para revisar</h2><p>Abra cada evidencia antes de validar la propuesta de IA.</p></div><span className="soft-badge">{data.indicators.length} resultados</span></div>
            <div className="indicator-list">
              {data.indicators.map((indicator) => <IndicatorReview key={indicator.id} indicator={indicator} artifacts={data.artifacts} />)}
            </div>
          </section>

          <section className="panel">
            <div className="panel-title"><div><h2>Inventario de evidencias</h2><p>Archivos procesados desde Moodle.</p></div><span className="soft-badge">{data.artifacts.length} archivos</span></div>
            <div className="artifact-grid">
              {data.artifacts.map((artifact) => (
                <article className="artifact" key={artifact.id}>
                  <div className="file-icon">{artifact.mime_type.startsWith("video") ? "▶" : "DOC"}</div>
                  <div><span>{artifact.evidence_type.replaceAll("_", " ")}</span><strong>{artifact.filename}</strong><small>{duration(artifact.duration_seconds) ?? `${artifact.page_count ?? 0} páginas`} · {artifact.technical_analysis?.status ?? artifact.processing_status}</small>{artifact.technical_analysis && <div className="artifact-metrics">{artifact.technical_analysis.modality === "VIDEO" ? <>{artifact.technical_analysis.metrics.width && <em>{String(artifact.technical_analysis.metrics.width)}×{String(artifact.technical_analysis.metrics.height)}</em>}<em>{String(artifact.technical_analysis.metrics.sampled_frames ?? 0)} fotogramas</em><em>{artifact.technical_analysis.metrics.has_audio ? "Con audio" : "Sin audio"}</em></> : <><em>{String(artifact.technical_analysis.metrics.word_count ?? 0)} palabras</em><em>{String(artifact.technical_analysis.metrics.character_count ?? 0)} caracteres</em></>}</div>}</div>
                </article>
              ))}
            </div>
          </section>
        </div>
        <aside><CopilotPanel caseId={data.id} /></aside>
      </div>
    </div>
  );
}
