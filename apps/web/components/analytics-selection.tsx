"use client";

import Link from "next/link";
import { useState } from "react";
import { API_URL } from "@/lib/api";
import type { AnalyticsOverview } from "@/lib/types";

function bytes(value?: number | null) { if (!value) return "0 MB"; return `${(value / 1024 / 1024).toFixed(2)} MB`; }
function minutes(value?: number | null) { if (!value) return "0 min"; return `${(value / 60).toFixed(1)} min`; }

type Meta = NonNullable<AnalyticsOverview["similarity_meta"]>;
type Edge = AnalyticsOverview["similarity_edges"][number];
const CLUSTER_COLORS = ["#1f5f8b", "#bd1e2d", "#1d7650", "#9b6411", "#7653a6", "#247c87"];

function ClusterGraph({ nodes: allNodes, pairs, threshold }: { nodes: AnalyticsOverview["cluster_graph"]["nodes"]; pairs: Edge[]; threshold: number }) {
  const nodes = allNodes.slice(0, 80);
  const nodeIds = new Set(nodes.map((node) => node.id));
  const best = new Map<string, { a: string; b: string; score: number }>();
  pairs.forEach((edge) => {
    if (!nodeIds.has(edge.source_case_id) || !nodeIds.has(edge.target_case_id)) return;
    const key = [edge.source_case_id, edge.target_case_id].sort().join("|");
    const current = best.get(key);
    if (!current || edge.score > current.score) best.set(key, { a: edge.source_case_id, b: edge.target_case_id, score: edge.score });
  });
  const edges = [...best.values()].sort((x, y) => y.score - x.score);
  const parent = new Map(nodes.map((node) => [node.id, node.id]));
  const find = (id: string): string => { let root = id; while (parent.get(root) !== root) root = parent.get(root)!; return root; };
  edges.forEach((edge) => parent.set(find(edge.a), find(edge.b)));
  const members = new Map<string, typeof nodes>();
  nodes.forEach((node) => members.set(find(node.id), [...(members.get(find(node.id)) ?? []), node]));
  const multi = [...members.entries()].filter(([, list]) => list.length > 1).sort((x, y) => y[1].length - x[1].length);
  const singles = [...members.values()].filter((list) => list.length === 1).map((list) => list[0]);
  const groupNumber = new Map(multi.map(([root], index) => [root, index + 1]));
  const positions = new Map<string, { x: number; y: number }>();
  multi.forEach(([, list], groupIndex) => {
    const others = multi.length - 1;
    const angle = ((groupIndex - 1) / Math.max(others, 1)) * Math.PI * 2 - Math.PI / 2;
    const centre = groupIndex === 0 ? { x: 400, y: 260 } : { x: 400 + Math.cos(angle) * 250, y: 260 + Math.sin(angle) * 160 };
    const needed = (list.length * 44) / (Math.PI * 2);
    const radiusX = Math.min(Math.max(needed, 40), groupIndex === 0 ? (multi.length === 1 ? 300 : 150) : 60);
    const radiusY = radiusX * 0.8;
    list.forEach((node, index) => positions.set(node.id, { x: centre.x + Math.cos((index / list.length) * Math.PI * 2) * radiusX, y: centre.y + Math.sin((index / list.length) * Math.PI * 2) * radiusY }));
  });
  singles.forEach((node, index) => positions.set(node.id, { x: 400 + Math.cos((index / Math.max(singles.length, 1)) * Math.PI * 2) * (multi.length ? 350 : 300), y: 260 + Math.sin((index / Math.max(singles.length, 1)) * Math.PI * 2) * (multi.length ? 235 : 205) }));
  const colorOf = (id: string) => { const number = groupNumber.get(find(id)); return number ? CLUSTER_COLORS[(number - 1) % CLUSTER_COLORS.length] : "#9aa9b3"; };
  const groupSize = (id: string) => members.get(find(id))?.length ?? 1;
  const groupRange = new Map<string, { min: number; max: number }>();
  edges.forEach((edge) => { const root = find(edge.a); const range = groupRange.get(root) ?? { min: 100, max: 0 }; groupRange.set(root, { min: Math.min(range.min, edge.score), max: Math.max(range.max, edge.score) }); });
  return <div className="cluster-graph">
    {nodes.length ? <svg viewBox="0 0 800 520" role="img" aria-label="Grafo de similitud entre expedientes">
      {edges.map((edge) => {
        const source = positions.get(edge.a)!; const target = positions.get(edge.b)!;
        const mx = (source.x + target.x) / 2; const my = (source.y + target.y) / 2;
        return <g key={`${edge.a}-${edge.b}`}>
          <line x1={source.x} y1={source.y} x2={target.x} y2={target.y} stroke="#4b6b80" strokeOpacity={0.35 + edge.score / 160} strokeWidth={Math.max(1.2, edge.score / 20)}><title>{`${edge.score}% de similitud`}</title></line>
          {groupSize(edge.a) <= 4 && <g><rect x={mx - 17} y={my - 8} width="34" height="15" rx="7" fill="#fff" stroke="#c5d2da" /><text className="edge-label" x={mx} y={my + 3} textAnchor="middle">{Math.round(edge.score)}%</text></g>}
        </g>;
      })}
      {nodes.map((node) => { const point = positions.get(node.id)!; const number = groupNumber.get(find(node.id)); return <g key={node.id}><circle cx={point.x} cy={point.y} r="16" fill={colorOf(node.id)} stroke="#fff" strokeWidth="2"><title>{`${node.label} · ${number ? `grupo ${number}` : `sin coincidencias ≥ ${threshold}%`}`}</title></circle><text x={point.x} y={point.y + 29} textAnchor="middle">{node.label.slice(0, 14)}</text></g>; })}
    </svg> : <div className="empty compact">No hay expedientes seleccionados.</div>}
    <div className="graph-legend">
      {multi.map(([root, list]) => <span key={root}><i style={{ background: CLUSTER_COLORS[(groupNumber.get(root)! - 1) % CLUSTER_COLORS.length] }} />Grupo {groupNumber.get(root)}: {list.length} docentes (similitud {Math.round(groupRange.get(root)?.min ?? 0)}–{Math.round(groupRange.get(root)?.max ?? 0)}%)</span>)}
      {singles.length > 0 && <span><i style={{ background: "#9aa9b3" }} />{singles.length} docente(s) sin coincidencias ≥ {threshold}%</span>}
    </div>
  </div>;
}

function SimilaritySection({ data, minScore, setMinScore, onlySame, setOnlySame, preparing, onPrepare, pairsShown, setPairsShown }: { data: AnalyticsOverview; minScore: number; setMinScore: (value: number) => void; onlySame: boolean; setOnlySame: (value: boolean) => void; preparing: boolean; onPrepare: (retry: boolean) => void; pairsShown: number; setPairsShown: (value: number) => void }) {
  const meta = data.similarity_meta;
  const all = data.similarity_edges;
  const filtered = all.filter((edge) => edge.score >= minScore && (!onlySame || edge.same_cmid));
  const maxBucket = Math.max(1, ...(meta?.distribution ?? [0]));
  const pending = meta?.pending_documents ?? 0;
  return <section className="panel similarity-section">
    <div className="panel-title"><div><h2>Similitud entre los productos que suben</h2><p>Se compara el contenido de los archivos (PDF, Word, texto) de los docentes seleccionados. Los videos no se comparan.</p></div>{meta && <span className="soft-badge">{meta.documents_with_text}/{meta.total_documents} documentos leídos</span>}</div>
    {pending > 0 && <div className="similarity-prepare"><p><strong>{pending} documento(s) sin leer.</strong> Para calcular la similitud hay que descargar y leer el texto de cada archivo seleccionado. Si ya lo intentaste, los restantes fallaron o son escaneados sin texto legible.</p><button className="button primary" onClick={() => onPrepare(true)} disabled={preparing}>{preparing ? "Leyendo documentos…" : "Preparar comparación"}</button></div>}
    {meta && meta.documents_with_text > 0 && <>
      <div className="metric-grid similarity-stats"><div><span>Comparaciones hechas</span><strong>{meta.pairs_compared.toLocaleString("es-PE")}</strong></div><div><span>Similitud máxima</span><strong>{meta.max_score}%</strong></div><div><span>Similitud mediana</span><strong>{meta.median_score}%</strong></div><div><span>Archivos idénticos</span><strong>{meta.exact_duplicate_pairs}</strong></div></div>
      <div className="similarity-histogram"><h3>Cuántas comparaciones hay en cada rango de similitud</h3><div>{meta.distribution.map((count, index) => <div key={index} className="bar"><strong>{count}</strong><i style={{ height: `${Math.max(2, (count / maxBucket) * 90)}px` }} /><span>{index * 10}–{index === 9 ? 100 : index * 10 + 9}%</span></div>)}</div></div>
      <div className="similarity-controls"><label>Mostrar desde <strong>{minScore}%</strong><input type="range" min={0} max={100} step={5} value={minScore} onChange={(event) => setMinScore(Number(event.target.value))} /></label><label className="check"><input type="checkbox" checked={onlySame} onChange={(event) => setOnlySame(event.target.checked)} /> Solo entre entregas de la misma actividad (CMID)</label></div>
      <ClusterGraph nodes={data.cluster_graph.nodes} pairs={filtered} threshold={minScore} />
      <small className="similarity-note"><b>Similitud de contenido</b>: qué tanto se parecen en vocabulario y tema. <b>Coincidencia literal</b>: % de frases de 5 palabras que aparecen iguales en ambos textos; es la señal más útil para detectar copia. Los textos de una misma actividad comparten vocabulario, por eso valores bajos o medios son normales. Es una señal para revisar, no implica plagio.</small>
      <div className="table-wrap"><table><thead><tr><th>Docente A</th><th>Docente B</th><th>Archivos</th><th>CMID</th><th>Similitud de contenido</th><th>Coincidencia literal</th></tr></thead><tbody>{filtered.slice(0, pairsShown).map((edge, index) => <tr key={`${edge.source_artifact_id ?? index}-${edge.target_artifact_id ?? index}`}><td>{edge.source_teacher}</td><td>{edge.target_teacher}</td><td><small>{edge.source_filename}</small><small>{edge.target_filename}</small></td><td>{edge.source_cm_id ?? "—"} ↔ {edge.target_cm_id ?? "—"}</td><td><strong>{edge.score}%</strong></td><td><span className={`literal-chip ${edge.literal != null && edge.literal >= 50 ? "high" : edge.literal != null && edge.literal >= 20 ? "mid" : ""}`}>{edge.literal != null ? `${edge.literal}%` : "—"}</span></td></tr>)}</tbody></table>{!filtered.length && <div className="empty compact">Ninguna comparación llega a {minScore}%. Baja el filtro para ver más{meta.max_score < minScore ? ` (la mayor coincidencia es ${meta.max_score}%)` : ""}.</div>}</div>
      <div className="similarity-footer"><span>Mostrando {Math.min(pairsShown, filtered.length)} de {filtered.length} comparaciones (de {(meta?.pairs_with_similarity ?? all.length).toLocaleString("es-PE")} con alguna similitud).</span>{filtered.length > pairsShown && <button onClick={() => setPairsShown(pairsShown + 100)}>Ver 100 más</button>}</div>
    </>}
    {meta && meta.documents_with_text === 0 && pending === 0 && <div className="empty compact">Ningún documento tiene texto legible (pueden ser escaneados o fallar la descarga). <button onClick={() => onPrepare(true)} disabled={preparing}>Reintentar</button></div>}
  </section>;
}

export function AnalyticsSelection({ initial }: { initial: AnalyticsOverview }) {
  const allIds = initial.teacher_analysis.map((item) => item.case_id);
  const [selected, setSelected] = useState<string[]>(allIds);
  const [data, setData] = useState(initial);
  const [loading, setLoading] = useState<"view" | "run" | "">("");
  const [message, setMessage] = useState("");
  const [minScore, setMinScore] = useState(50);
  const [onlySame, setOnlySame] = useState(true);
  const [preparing, setPreparing] = useState(false);
  const [pairsShown, setPairsShown] = useState(100);

  function toggle(caseId: string) {
    setSelected((current) => current.includes(caseId) ? current.filter((value) => value !== caseId) : [...current, caseId]);
  }
  async function refreshSelection() {
    if (!selected.length) { setMessage("Selecciona al menos un expediente."); return; }
    setLoading("view"); setMessage("");
    try {
      const response = await fetch(`${API_URL}/analytics/overview?case_ids=${encodeURIComponent(selected.join(","))}`);
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "No se pudo calcular la analítica.");
      setData(payload); setMessage(`Analítica actualizada para ${selected.length} expediente(s).`);
    } catch (error) { setMessage(error instanceof Error ? error.message : "No se pudo calcular."); }
    finally { setLoading(""); }
  }
  async function prepareComparison(retry: boolean) {
    if (!selected.length) { setMessage("Selecciona al menos un expediente."); return; }
    setPreparing(true); setMessage("");
    try {
      let retryNow = retry;
      for (let round = 0; round < 400; round++) {
        const response = await fetch(`${API_URL}/analysis/prepare-similarity`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ case_ids: selected, batch_size: 8, retry_failed: retryNow }) });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.detail ?? "No se pudo leer los documentos.");
        retryNow = false;
        setMessage(`Leyendo documentos… ${payload.total - payload.pending}/${payload.total} (${payload.failed} con error)`);
        if (payload.pending === 0 || payload.processed === 0) break;
      }
      await refreshSelection();
    } catch (error) { setMessage(error instanceof Error ? error.message : "No se pudo preparar la comparación."); }
    finally { setPreparing(false); }
  }
  async function runSelected() {
    if (!selected.length) { setMessage("Selecciona al menos un expediente."); return; }
    if (!window.confirm(`Se enviarán exactamente ${selected.length} expediente(s) al análisis IA. ¿Continuar?`)) return;
    setLoading("run"); setMessage("");
    try {
      const response = await fetch(`${API_URL}/analysis/run`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ case_ids: selected, force: false }) });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "No se pudo iniciar el análisis.");
      setMessage(`${payload.queued} expediente(s) enviados a la cola de análisis.`);
    } catch (error) { setMessage(error instanceof Error ? error.message : "No se pudo iniciar."); }
    finally { setLoading(""); }
  }

  return <section className="selection-analytics">
    <section className="panel"><div className="panel-title"><div><h2>Seleccionar expedientes</h2><p>La analítica y las llamadas IA se limitarán a la selección.</p></div><span className="soft-badge">{selected.length}/{allIds.length} seleccionados</span></div><div className="selection-toolbar"><button onClick={() => setSelected(allIds)}>Seleccionar todos</button><button onClick={() => setSelected([])}>Limpiar</button><button className="button secondary" onClick={refreshSelection} disabled={loading !== ""}>{loading === "view" ? "Calculando…" : "Ver analítica seleccionada"}</button><button className="button secondary" onClick={() => prepareComparison(false)} disabled={loading !== "" || preparing}>{preparing ? "Leyendo…" : "Comparar documentos"}</button><button className="button primary" onClick={runSelected} disabled={loading !== ""}>{loading === "run" ? "Enviando…" : "Analizar selección con IA"}</button></div>{message && <p className="selection-message">{message}</p>}<div className="case-check-grid">{initial.teacher_analysis.map((item) => <label key={item.case_id}><input type="checkbox" checked={selected.includes(item.case_id)} onChange={() => toggle(item.case_id)} /><span><strong>{item.teacher}</strong><small>{item.username ? `@${item.username}` : item.case_id}</small></span></label>)}</div></section>

    <section className="stats analytics-stats ai-stats"><article><span>Expedientes mostrados</span><strong>{data.cases}</strong><small>{data.analyzed_cases} analizados por IA</small></article><article><span>Documentos</span><strong>{data.document_metrics.count ?? 0}</strong><small>{bytes(data.document_metrics.average_size_bytes)} promedio</small></article><article><span>Videos</span><strong>{data.video_metrics.count ?? 0}</strong><small>{minutes(data.video_metrics.total_duration_seconds)} acumulados</small></article><article><span>Clústeres</span><strong>{data.cluster_graph.cluster_count ?? 0}</strong><small>{data.similarity_edges.length} relaciones encontradas</small></article></section>

    <div className="analytics-grid metric-panels"><section className="panel"><div className="panel-title"><div><h2>Métricas de documentos</h2><p>Calculadas únicamente sobre la selección.</p></div></div><div className="metric-grid"><div><span>Tamaño promedio</span><strong>{bytes(data.document_metrics.average_size_bytes)}</strong></div><div><span>Caracteres promedio</span><strong>{Math.round(data.document_metrics.average_characters ?? 0).toLocaleString("es-PE")}</strong></div><div><span>Palabras promedio</span><strong>{Math.round(data.document_metrics.average_words ?? 0).toLocaleString("es-PE")}</strong></div><div><span>Páginas promedio</span><strong>{data.document_metrics.average_pages ?? "—"}</strong></div><div><span>Texto extraíble</span><strong>{data.document_metrics.extractable_count ?? 0}</strong></div><div><span>Requieren revisión</span><strong>{data.document_metrics.needs_review_count ?? 0}</strong></div></div></section><section className="panel"><div className="panel-title"><div><h2>Métricas de videos</h2><p>Propiedades técnicas y cobertura del muestreo.</p></div></div><div className="metric-grid"><div><span>Duración promedio</span><strong>{minutes(data.video_metrics.average_duration_seconds)}</strong></div><div><span>Duración mínima</span><strong>{minutes(data.video_metrics.minimum_duration_seconds)}</strong></div><div><span>Duración máxima</span><strong>{minutes(data.video_metrics.maximum_duration_seconds)}</strong></div><div><span>Tamaño promedio</span><strong>{bytes(data.video_metrics.average_size_bytes)}</strong></div><div><span>FPS promedio</span><strong>{data.video_metrics.average_fps ?? "—"}</strong></div><div><span>Con audio</span><strong>{data.video_metrics.with_audio_count ?? 0}</strong></div><div><span>Full HD o superior</span><strong>{data.video_metrics.full_hd_or_higher_count ?? 0}</strong></div><div><span>Transcritos</span><strong>{data.video_metrics.transcribed_count ?? 0}</strong></div></div></section></div>

    <div className="analytics-grid selected-results"><section className="panel"><div className="panel-title"><div><h2>Coherencia del expediente</h2><p>Relación lógica entre los CMID en el orden de la secuencia.</p></div></div><div className="table-wrap"><table><thead><tr><th>Docente</th><th>Promedio CMID</th><th>Coherencia</th><th>Detalle por CMID</th></tr></thead><tbody>{data.teacher_analysis.map((item) => <tr key={item.case_id}><td><Link href={`/expedientes/${item.case_id}`}><strong>{item.teacher}</strong><small>{item.status}</small></Link></td><td>{item.average_cmid_score != null ? `${item.average_cmid_score}/100` : "—"}</td><td>{item.coherence_score != null ? `${item.coherence_score}/100` : "—"}</td><td>{item.cmid_scores.length ? item.cmid_scores.map((score) => `CMID ${score.cm_id}: ${score.score ?? "—"} (sim. ${score.similarity_score ?? "—"}%)`).join(" · ") : "Sin análisis"}</td></tr>)}</tbody></table></div></section><section className="panel"><div className="panel-title"><div><h2>Evidencias por CMID</h2><p>Clasificación contextual, no solo por extensión.</p></div></div><div className="table-wrap"><table><thead><tr><th>CMID</th><th>Tipo</th><th>Cantidad</th></tr></thead><tbody>{data.evidence_by_cmid.map((item) => <tr key={`${item.cm_id}-${item.evidence_type}`}><td><strong>{item.cm_id}</strong><small>{item.activity_name}</small></td><td>{item.evidence_type.replaceAll("_", " ")}</td><td>{item.count}</td></tr>)}</tbody></table></div></section></div>

    <section className="panel rubric-analytics"><div className="panel-title"><div><h2>Rúbrica MBDD de la selección</h2><p>Distribución de niveles propuestos o validados para los expedientes seleccionados.</p></div><span className="soft-badge">{data.rubric_analytics.validated_count ?? 0}/{data.rubric_analytics.assessment_count ?? 0} validados</span></div><div className="table-wrap"><table><thead><tr><th>Dimensión</th><th>Promedio</th><th>Nivel 4</th><th>Nivel 3</th><th>Nivel 2</th><th>Nivel 1</th></tr></thead><tbody>{data.rubric_analytics.dimensions?.map((item) => <tr key={item.dimension}><td><strong>{item.dimension}</strong></td><td><span className="rubric-level">{item.average_level.toFixed(2)}</span></td><td>{item.level_4}</td><td>{item.level_3}</td><td>{item.level_2}</td><td>{item.level_1}</td></tr>)}</tbody></table>{!data.rubric_analytics.dimensions?.length && <div className="empty compact">Analiza los expedientes para generar la rúbrica por CMID.</div>}</div><div className="rubric-bars">{data.rubric_analytics.dimensions?.map((item) => <div key={item.dimension}><span>{item.dimension}</span><div><i style={{width: `${item.average_level / 4 * 100}%`}} /></div><strong>{item.average_level.toFixed(2)}/4</strong></div>)}</div></section>

    <section className="panel document-comparison"><div className="panel-title"><div><h2>Comparación de documentos</h2><p>Tamaño, extensión textual y legibilidad por docente y CMID.</p></div></div><div className="table-wrap"><table><thead><tr><th>Docente</th><th>CMID / archivo</th><th>Tamaño</th><th>Páginas</th><th>Palabras</th><th>Caracteres</th><th>Estado</th></tr></thead><tbody>{data.document_comparison.map((document, index) => <tr key={`${String(document.artifact_id)}-${index}`}><td>{String(document.teacher ?? "—")}</td><td><strong>CMID {String(document.cm_id ?? "—")}</strong><small>{String(document.filename ?? "—")}</small></td><td>{bytes(typeof document.size_bytes === "number" ? document.size_bytes : null)}</td><td>{String(document.page_count ?? "—")}</td><td>{Number(document.word_count ?? 0).toLocaleString("es-PE")}</td><td>{Number(document.character_count ?? 0).toLocaleString("es-PE")}</td><td>{String(document.status ?? "—")}</td></tr>)}</tbody></table>{!data.document_comparison.length && <div className="empty compact">Los documentos aparecerán después de analizar los expedientes seleccionados.</div>}</div></section>

    <section className="panel video-comparison"><div className="panel-title"><div><h2>Comparación de videos</h2><p>Duración, calidad técnica, audio y cobertura visual por docente y CMID.</p></div></div><div className="table-wrap"><table><thead><tr><th>Docente</th><th>CMID / archivo</th><th>Duración</th><th>Resolución</th><th>FPS</th><th>Audio</th><th>Fotogramas</th></tr></thead><tbody>{data.video_comparison.map((video) => <tr key={`${video.case_id}-${video.cm_id}-${video.filename}`}><td>{video.teacher}</td><td><strong>CMID {video.cm_id}</strong><small>{video.filename}</small></td><td>{video.duration_seconds != null ? `${Math.round(video.duration_seconds)} s` : "—"}</td><td>{video.width && video.height ? `${video.width}×${video.height}` : "—"}</td><td>{video.fps ?? "—"}</td><td>{video.has_audio == null ? "—" : video.has_audio ? "Sí" : "No"}</td><td>{video.sampled_frames ?? "—"}</td></tr>)}</tbody></table>{!data.video_comparison.length && <div className="empty compact">Los videos aparecerán después de analizar los expedientes seleccionados.</div>}</div></section>
    <SimilaritySection data={data} minScore={minScore} setMinScore={setMinScore} onlySame={onlySame} setOnlySame={setOnlySame} preparing={preparing} onPrepare={prepareComparison} pairsShown={pairsShown} setPairsShown={setPairsShown} />
    <section className="panel"><div className="panel-title"><div><h2>Patrones de retroalimentación IA</h2><p>Consolida los hallazgos previamente generados.</p></div></div><div className="pattern-list">{data.feedback_patterns.map((pattern) => <div key={pattern.type}><span>{pattern.type.replaceAll("_", " ")}</span><strong>{pattern.count}</strong><small>{pattern.average_confidence != null ? `${Math.round(pattern.average_confidence * 100)}% confianza` : ""}</small></div>)}{!data.feedback_patterns.length && <div className="empty compact">Sin retroalimentaciones analizadas.</div>}</div></section>
    </section>;
}
