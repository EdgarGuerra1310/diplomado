# Plugin local DIFODS Copilot

## Instalación

1. Copiar `difodscopilot` dentro de `local/` en Moodle.
2. Ejecutar la actualización de Moodle.
3. Configurar endpoint, secreto y cursos habilitados.
4. Crear una cuenta técnica de Web Services con mínimo privilegio.
5. Autorizar el servicio `difodscopilot` y habilitar descarga de archivos.
6. Confirmar que cron se ejecuta al menos una vez por minuto.

El observador solo registra un evento duradero y encola una tarea. El envío HTTP ocurre fuera de la transacción de la entrega.

## Estado MVP

El manifiesto implementa entregas de archivos de `mod_assign`. Para otros plugins de entrega o actividades se deben agregar adaptadores. La tarea de reconciliación está creada como punto de extensión y debe completar la estrategia de cursor antes de producción.
