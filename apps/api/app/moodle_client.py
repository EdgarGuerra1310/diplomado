from typing import Any

import httpx

from app.config import Settings


class MoodleAPIError(RuntimeError):
    def __init__(self, message: str, *, error_code: str | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code


class MoodleClient:
    """Cliente mínimo para Web Services REST de Moodle.

    El token nunca se incorpora a logs, URLs almacenadas ni respuestas de la API.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not settings.moodle_base_url or not settings.moodle_token:
            raise MoodleAPIError(
                "Moodle no está configurado. Define MOODLE_BASE_URL y un MOODLE_TOKEN nuevo."
            )
        self.base_url = settings.moodle_base_url.rstrip("/")
        self.service_url = f"{self.base_url}{settings.moodle_service_path}"
        self.token = settings.moodle_token
        timeout = httpx.Timeout(settings.moodle_timeout_seconds, connect=15)
        self.client = httpx.Client(timeout=timeout, follow_redirects=True, transport=transport)

    def close(self) -> None:
        self.client.close()

    def call(self, function: str, **params: Any) -> Any:
        payload = {
            "wstoken": self.token,
            "moodlewsrestformat": "json",
            "wsfunction": function,
            **params,
        }
        try:
            response = self.client.post(self.service_url, data=payload)
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise MoodleAPIError(f"No se pudo consultar Moodle: {error}") from error
        if isinstance(data, dict) and (data.get("exception") or data.get("errorcode")):
            message = data.get("message") or "Moodle devolvió un error no especificado."
            raise MoodleAPIError(message, error_code=data.get("errorcode"))
        return data

    def site_info(self) -> dict[str, Any]:
        return self.call("core_webservice_get_site_info")

    def resolve_course_id(self, course_id: int | None, cm_id: int | None) -> int:
        if course_id:
            return course_id
        if not cm_id:
            raise MoodleAPIError("Debes indicar courseid o cmid.")
        result = self.call("core_course_get_course_module", cmid=cm_id)
        module = result.get("cm", result) if isinstance(result, dict) else {}
        resolved = module.get("course") or module.get("courseid")
        if not resolved:
            raise MoodleAPIError(
                "El servicio no pudo resolver el curso desde cmid. Indica también courseid."
            )
        return int(resolved)

    def course_contents(self, course_id: int) -> list[dict[str, Any]]:
        data = self.call("core_course_get_contents", courseid=course_id)
        return data if isinstance(data, list) else []

    def assignments(self, course_id: int) -> tuple[str, list[dict[str, Any]], list[str]]:
        data = self.call("mod_assign_get_assignments", **{"courseids[0]": course_id})
        courses = data.get("courses", []) if isinstance(data, dict) else []
        warnings = [str(item.get("message", item)) for item in data.get("warnings", [])]
        if not courses:
            return f"Curso {course_id}", [], warnings
        course = courses[0]
        return (
            str(course.get("fullname") or course.get("shortname") or course_id),
            course.get("assignments", []),
            warnings,
        )

    def submissions(self, assignment_ids: list[int]) -> tuple[list[dict[str, Any]], list[str]]:
        if not assignment_ids:
            return [], []
        params = {f"assignmentids[{index}]": value for index, value in enumerate(assignment_ids)}
        data = self.call("mod_assign_get_submissions", **params)
        assignments = data.get("assignments", []) if isinstance(data, dict) else []
        warnings = [str(item.get("message", item)) for item in data.get("warnings", [])]
        return assignments, warnings

    def users_by_usernames(self, usernames: list[str]) -> list[dict[str, Any]]:
        if not usernames:
            return []
        params: dict[str, Any] = {"field": "username"}
        params.update({f"values[{index}]": value for index, value in enumerate(usernames)})
        data = self.call("core_user_get_users_by_field", **params)
        return data if isinstance(data, list) else []

    def users_by_ids(self, user_ids: list[int]) -> list[dict[str, Any]]:
        users: list[dict[str, Any]] = []
        unique_ids = list(dict.fromkeys(user_ids))
        for offset in range(0, len(unique_ids), 100):
            batch = unique_ids[offset : offset + 100]
            params: dict[str, Any] = {"field": "id"}
            params.update({f"values[{index}]": value for index, value in enumerate(batch)})
            data = self.call("core_user_get_users_by_field", **params)
            if isinstance(data, list):
                users.extend(data)
        return users

    def submission_status(self, assignment_id: int, user_id: int) -> dict[str, Any] | None:
        data = self.call(
            "mod_assign_get_submission_status",
            assignid=assignment_id,
            userid=user_id,
        )
        last_attempt = data.get("lastattempt", {}) if isinstance(data, dict) else {}
        submission = last_attempt.get("submission")
        return submission if isinstance(submission, dict) else None

    def enrolled_users(self, course_id: int) -> list[dict[str, Any]]:
        data = self.call("core_enrol_get_enrolled_users", courseid=course_id)
        return data if isinstance(data, list) else []


def flatten_submission_files(submission: dict[str, Any]) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for plugin in submission.get("plugins", []):
        for filearea in plugin.get("fileareas", []) or []:
            for file in filearea.get("files", []) or []:
                files.append(
                    {
                        **file,
                        "plugin_type": plugin.get("type", "unknown"),
                        "file_area": filearea.get("area", "submission_files"),
                    }
                )
    return files
