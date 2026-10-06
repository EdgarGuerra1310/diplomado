import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app, get_moodle_client


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_seed_and_read_case() -> None:
    with TestClient(app) as client:
        seeded = client.post("/api/v1/demo/seed")
        assert seeded.status_code == 200
        case = seeded.json()
        assert case["status"] == "READY_FOR_REVIEW"
        assert len(case["artifacts"]) == 5
        assert all(indicator["citations"] for indicator in case["indicators"])

        fetched = client.get(f"/api/v1/cases/{case['id']}")
        assert fetched.status_code == 200
        assert fetched.json()["teacher_code"] == "DOC-LB-0001"


def test_grounded_query_has_citation() -> None:
    with TestClient(app) as client:
        case = client.post("/api/v1/demo/seed").json()
        response = client.post(
            f"/api/v1/cases/{case['id']}/queries",
            json={"question": "¿Dónde aparece pensamiento crítico?"},
        )
        assert response.status_code == 200
        assert response.json()["citations"]


def test_human_review_changes_case_status() -> None:
    with TestClient(app) as client:
        case = client.post("/api/v1/demo/seed").json()
        indicator_id = case["indicators"][0]["id"]
        reviewed = client.post(
            f"/api/v1/indicator-results/{indicator_id}/reviews",
            json={"decision": "CONFIRMED", "reviewer_id": "especialista-prueba"},
        )
        assert reviewed.status_code == 201
        assert reviewed.json()["decision"] == "CONFIRMED"
        assert client.get(f"/api/v1/cases/{case['id']}").json()["status"] == "IN_REVIEW"


def test_moodle_event_is_idempotent() -> None:
    event_id = str(uuid.uuid4())
    submission_id = uuid.uuid4().int % 2_000_000_000
    payload = {
        "event_id": event_id,
        "event_type": "submission.finalized",
        "occurred_at": datetime.now(UTC).isoformat(),
        "moodle_site_id": "sifods-test",
        "course_id": 2741,
        "course_name": "Diplomado 2026",
        "submission_id": submission_id,
        "teacher_pseudonym_id": "tch_test",
        "measurement": "LB",
        "manifest_version": 1,
        "correlation_id": str(uuid.uuid4()),
    }
    with TestClient(app) as client:
        first = client.post("/api/v1/moodle/events", json=payload)
        duplicate = client.post("/api/v1/moodle/events", json=payload)
        assert first.status_code == 202
        assert first.json()["duplicate"] is False
        assert duplicate.status_code == 200
        assert duplicate.json()["duplicate"] is True
        assert duplicate.json()["case_id"] == first.json()["case_id"]


class FakeMoodleClient:
    base_url = "https://moodle.example.test"

    def close(self) -> None:
        pass

    def site_info(self) -> dict:
        return {"sitename": "Moodle de prueba", "siteurl": self.base_url}

    def resolve_course_id(self, course_id: int | None, cm_id: int | None) -> int:
        return course_id or 999

    def assignments(self, course_id: int):
        return (
            "Aula de Línea Base",
            [{"id": 91, "cmid": 501, "name": "Video de clase"}],
            [],
        )

    def submissions(self, assignment_ids: list[int]):
        return (
            [
                {
                    "assignmentid": 91,
                    "submissions": [
                        {
                            "id": 7001,
                            "userid": 42,
                            "attemptnumber": 0,
                            "plugins": [
                                {
                                    "type": "file",
                                    "fileareas": [
                                        {
                                            "area": "submission_files",
                                            "files": [
                                                {
                                                    "filename": "video_clase.mp4",
                                                    "mimetype": "video/mp4",
                                                    "contenthash": "abc123",
                                                    "fileurl": "https://moodle.example.test/file.mp4?token=secret",
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
            [],
        )

    def users_by_usernames(self, usernames: list[str]) -> list[dict]:
        return (
            [{"id": 42, "username": "doc42", "fullname": "Docente de Prueba"}]
            if "doc42" in usernames
            else []
        )

    def users_by_ids(self, user_ids: list[int]) -> list[dict]:
        return [
            {"id": user_id, "username": f"doc{user_id}", "fullname": "Docente de Prueba"}
            for user_id in user_ids
        ]

    def submission_status(self, assignment_id: int, user_id: int) -> dict:
        return {
            "id": 7001,
            "userid": user_id,
            "attemptnumber": 0,
            "plugins": [
                {
                    "type": "file",
                    "fileareas": [
                        {
                            "area": "submission_files",
                            "files": [
                                {
                                    "filename": "video_clase.mp4",
                                    "mimetype": "video/mp4",
                                    "contenthash": "abc123",
                                    "fileurl": "https://moodle.example.test/file.mp4?token=secret",
                                }
                            ],
                        }
                    ],
                }
            ],
        }

    def enrolled_users(self, course_id: int) -> list[dict]:
        return []


def test_moodle_preview_and_import() -> None:
    course_id = uuid.uuid4().int % 2_000_000_000
    fake = FakeMoodleClient()
    app.dependency_overrides[get_moodle_client] = lambda: fake
    try:
        with TestClient(app) as client:
            preview = client.post(
                "/api/v1/moodle/preview", json={"course_id": course_id, "cm_id": 501}
            )
            assert preview.status_code == 200
            assert preview.json()["submission_count"] == 1
            assert preview.json()["file_count"] == 1

            targeted = client.post(
                "/api/v1/moodle/preview",
                json={
                    "course_id": course_id,
                    "cm_id": 501,
                    "usernames": ["doc42", "no_existe"],
                },
            )
            assert targeted.status_code == 200
            assert targeted.json()["matched_user_count"] == 1
            assert targeted.json()["requested_usernames"] == ["doc42", "no_existe"]
            assert any("no_existe" in warning for warning in targeted.json()["warnings"])

            imported = client.post(
                "/api/v1/moodle/import",
                json={"course_id": course_id, "cm_id": 501, "measurement": "LB"},
            )
            assert imported.status_code == 200
            assert imported.json()["cases_created"] == 1
            assert imported.json()["artifacts_created"] == 1
            case_id = imported.json()["case_ids"][0]
            case = client.get(f"/api/v1/cases/{case_id}").json()
            assert case["artifacts"][0]["evidence_type"] == "VIDEO_CLASE"
            assert "token=" not in (case["artifacts"][0]["source_url"] or "")
            assert case["identity"]["username"] == "doc42"
            assert case["identity"]["full_name"] == "Docente de Prueba"
            assert case["moodle_submissions"][0]["cm_id"] == 501
            assert case["moodle_submissions"][0]["artifact_ids"] == [case["artifacts"][0]["id"]]

            analytics = client.get("/api/v1/analytics/overview")
            assert analytics.status_code == 200
            assert analytics.json()["teachers"] == 1
            assert analytics.json()["submissions"] == 1
            assert analytics.json()["files"] == 1

            unavailable_file = client.get(f"/api/v1/artifacts/{case['artifacts'][0]['id']}/content")
            assert unavailable_file.status_code == 400

            removed = client.delete(f"/api/v1/cases/{case_id}/activities/501")
            assert removed.status_code == 200
            assert removed.json()["moodle_unchanged"] is True
            updated_case = client.get(f"/api/v1/cases/{case_id}").json()
            assert updated_case["moodle_submissions"] == []
            assert updated_case["artifacts"] == []
    finally:
        app.dependency_overrides.pop(get_moodle_client, None)
