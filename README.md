# Copiloto Pedagógico Inteligente DIFODS

MVP institucional para organizar y revisar evidencias pedagógicas provenientes de Moodle. La IA prepara expedientes con citas; el especialista valida, corrige o descarta cada señal.

## Componentes

- `apps/api`: API FastAPI, modelos, ingesta y workers Celery.
- `apps/web`: interfaz Next.js para especialistas.
- `moodle/local/difodscopilot`: plugin local de integración.
- `infra`: inicialización de PostgreSQL/pgvector.
- `docs`: arquitectura funcional y técnica.

## Inicio rápido con Docker

```bash
cp .env.example .env
docker compose up --build
```

Servicios:

- Aplicación: http://localhost:3000
- API/OpenAPI: http://localhost:7001/docs
- MinIO: http://localhost:9001
- RabbitMQ: http://localhost:15672

Para cargar el expediente demostrativo:

```bash
curl -X POST http://localhost:7001/api/v1/demo/seed
```

## Conectar con Moodle

1. Copiar `.env.example` como `.env`.
2. Colocar un token Moodle nuevo en `MOODLE_TOKEN`.
3. Configurar `MOODLE_BASE_URL` y `MOODLE_SERVICE_PATH`.
4. Opcionalmente definir `MOODLE_COURSE_ID` o `MOODLE_CM_ID` como selección inicial.
5. Abrir la aplicación y usar **Importar desde Moodle**.

Para aulas masivas se recomienda `MOODLE_TIMEOUT_SECONDS=120` o un valor mayor si la infraestructura de Moodle lo requiere.

La pantalla acepta:

- `courseid`: consulta todas las actividades `mod_assign` accesibles del aula.
- `cmid`: limita la extracción a una tarea concreta. Si el servicio Moodle no permite resolver el curso desde el módulo, debe proporcionarse también `courseid`.
- `username`: permite pegar hasta 100 docentes separados por comas, espacios o saltos de línea. En este modo se consulta cada entrega individualmente y se evita cargar primero las miles de entregas del aula.

Funciones REST requeridas para el token:

- `core_webservice_get_site_info`
- `core_course_get_course_module` (solo cuando se usa `cmid` sin `courseid`)
- `mod_assign_get_assignments`
- `mod_assign_get_submissions`
- `core_user_get_users_by_field` y `mod_assign_get_submission_status` para el modo filtrado por username
- `core_enrol_get_enrolled_users` únicamente si `MOODLE_INCLUDE_NAMES=true`

La importación primero presenta una vista previa. Después crea un expediente por docente y agrupa allí los archivos de las tareas seleccionadas. Los parámetros `token` se eliminan de las URLs antes de almacenarlas.

## Relación de evidencias

Cada importación conserva la relación:

```text
usuario Moodle → curso → cmid/tarea → submission/intento → archivos
```

El expediente muestra username, nombre completo, estado de la entrega, fecha de modificación, intento y los PDF, DOC/DOCX o MP4 asociados. El botón **Ver archivo** utiliza un proxy autenticado: el token Moodle permanece en el backend y nunca se entrega al navegador.

La página `/analitica` consolida docentes, entregas, archivos, estados por CMID, tipos de evidencia y validaciones realizadas por especialistas. Al volver a importar un docente se actualizan sus relaciones sin duplicar archivos con el mismo `contenthash`.

Nunca confirme credenciales en Git. Si una clave o token se comparte por un canal no seguro, debe revocarse y generarse nuevamente.

## Principios

- Moodle conserva la evidencia original.
- Ningún indicador es una calificación.
- Toda señal incluye una cita navegable.
- La validación humana es obligatoria.
- Las integraciones son idempotentes y auditables.

La arquitectura completa se encuentra en [docs/arquitectura-copiloto-pedagogico-difods.md](docs/arquitectura-copiloto-pedagogico-difods.md).
