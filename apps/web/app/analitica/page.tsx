import Link from "next/link";
import { AnalyticsSelection } from "@/components/analytics-selection";
import { getAnalytics } from "@/lib/api";

export default async function AnalyticsPage() {
  let data;
  try { data = await getAnalytics(); } catch { data = null; }
  return <div className="page-shell">
    <section className="page-heading"><div><p className="eyebrow">Visión institucional</p><h1>Analítica de evidencias</h1><p>Selecciona los expedientes y compara sus CMID, coherencia, documentos y videos.</p></div><Link className="button secondary" href="/">Ver expedientes</Link></section>
    {!data ? <section className="panel empty"><strong>No se pudo cargar la analítica.</strong></section> : <>
      <section className="stats analytics-stats"><article><span>Docentes disponibles</span><strong>{data.teachers}</strong><small>para seleccionar</small></article><article><span>Entregas</span><strong>{data.submissions}</strong><small>{data.submitted} enviadas</small></article><article><span>Archivos</span><strong>{data.files}</strong><small>documentos y videos</small></article><article><span>CMID</span><strong>{data.activities.length}</strong><small>actividades relacionadas</small></article></section>
      <section className="panel coverage-panel"><div className="panel-title"><div><h2>Cobertura general por CMID</h2><p>Antes de aplicar la selección de expedientes.</p></div></div><div className="table-wrap"><table><thead><tr><th>Actividad</th><th>CMID</th><th>Registros</th><th>Enviadas</th><th>Archivos</th></tr></thead><tbody>{data.activities.map((item) => <tr key={`${item.cm_id}-${item.activity_name}`}><td><strong>{item.activity_name}</strong></td><td>{item.cm_id}</td><td>{item.submissions}</td><td>{item.submitted}</td><td>{item.files}</td></tr>)}</tbody></table></div></section>
      <AnalyticsSelection initial={data} />
    </>}
  </div>;
}
