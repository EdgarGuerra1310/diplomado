import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Copiloto Pedagógico DIFODS",
  description: "Revisión asistida y trazable de evidencias pedagógicas",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es">
      <body>
        <header className="app-header">
          <Link href="/" className="brand" aria-label="Ir al inicio">
            <span className="brand-mark">DI</span>
            <span>
              <strong>Copiloto Pedagógico</strong>
              <small>Especialistas DIFODS</small>
            </span>
          </Link>
          <nav aria-label="Navegación principal">
            <Link href="/" className="nav-link active">Expedientes</Link>
            <Link href="/analitica" className="nav-link">Analítica</Link>
          </nav>
          <div className="user-pill"><span>EP</span> Especialista pedagógico</div>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
