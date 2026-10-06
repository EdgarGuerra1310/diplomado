import Link from "next/link";
import { DemoSeedButton } from "@/components/demo-seed-button";
import { MoodleImportPanel } from "@/components/moodle-import-panel";
import { getCases } from "@/lib/api";
import type { CaseSummary } from "@/lib/types";

const statusLabel: Record<string, string> = {
  READY_FOR_REVIEW: "Listo para revisar",
  IN_REVIEW: "En revisión",
  REVIEWED: "Revisado",
  PROCESSING: "Procesando",
  DISCOVERED: "Detectado",
};

export default async function Home() {
  let cases: CaseSummary[] = [];
  let unavailable = false;
  try {
    cases = await getCases();
  } catch {
    unavailable = true;
  }

  return (
    <div className="page-shell">
      <section className="page-heading">
        <div>
          <p className="eyebrow">Línea Base 2026</p>
          <h1>Expedientes pedagógicos</h1>
          <p>Señales organizadas por IA para revisión y decisión del especialista.</p>
        </div>
        <DemoSeedButton />
      </section>

      <MoodleImportPanel />

      <section className="stats" aria-label="Resumen de expedientes">
        <article><span>Total</span><strong>{cases.length}</strong><small>expedientes registrados</small></article>
        <article><span>Listos</span><strong>{cases.filter((c) => c.status === "READY_FOR_REVIEW").length}</strong><small>esperando revisión</small></article>
        <article><span>En revisión</span><strong>{cases.filter((c) => c.status === "IN_REVIEW").length}</strong><small>con validación iniciada</small></article>
      </section>

      <section className="panel">
        <div className="panel-title">
          <div><h2>Cola de revisión</h2><p>La IA no califica. Cada señal debe verificarse en su fuente.</p></div>
          <span className="soft-badge">Actualización automática</span>
        </div>
        {unavailable ? (
          <div className="empty"><strong>La API todavía no está disponible.</strong><p>Inicia los servicios con Docker Compose y vuelve a cargar.</p></div>
        ) : cases.length === 0 ? (
          <div className="empty"><strong>No hay expedientes.</strong><p>Carga el caso demostrativo para recorrer el flujo del MVP.</p></div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Docente</th><th>Contexto</th><th>Medición</th><th>Estado</th><th aria-label="Acción" /></tr></thead>
              <tbody>
                {cases.map((item) => (
                  <tr key={item.id}>
                    <td><strong>{item.teacher_code}</strong><small>{item.teacher_display_name ?? "Identidad protegida"}</small></td>
                    <td>{item.ugel ?? "Sin UGEL"}<small>{item.region} · {item.education_level}</small></td>
                    <td><span className="measure">{item.measurement}</span></td>
                    <td><span className={`status status-${item.status.toLowerCase()}`}>{statusLabel[item.status] ?? item.status}</span></td>
                    <td className="align-right"><Link className="button secondary" href={`/expedientes/${item.id}`}>Abrir expediente →</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
