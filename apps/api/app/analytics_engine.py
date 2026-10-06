import math
import re
from collections import Counter, defaultdict
from itertools import combinations
from typing import Any

from app.models import Artifact, CaseAIAnalysis, CaseFile, MoodleSubmissionRecord, RubricAssessment


EDGE_MIN_SCORE = 35.0
CLUSTER_MIN_SCORE = 45.0


def _average(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _tokens(value: str) -> list[str]:
    return re.findall(r"[a-záéíóúñü0-9]{3,}", value.lower())


def build_multimodal_analytics(
    cases: list[CaseFile],
    deliveries: list[MoodleSubmissionRecord],
    artifacts: list[Artifact],
    analyses: list[CaseAIAnalysis],
    rubric_assessments: list[RubricAssessment],
    texts: dict[str, str] | None = None,
) -> dict[str, Any]:
    case_by_id = {case.id: case for case in cases}
    artifact_delivery: dict[str, MoodleSubmissionRecord] = {}
    for delivery in deliveries:
        for artifact_id in delivery.artifact_ids:
            artifact_delivery.setdefault(artifact_id, delivery)

    document_rows: list[dict[str, Any]] = []
    video_rows: list[dict[str, Any]] = []
    for artifact in artifacts:
        technical = artifact.technical_analysis
        if not technical:
            continue
        delivery = artifact_delivery.get(artifact.id)
        case = case_by_id.get(artifact.case_id)
        row = {
            "case_id": artifact.case_id,
            "teacher": (case.teacher_display_name or case.teacher_code) if case else artifact.case_id,
            "artifact_id": artifact.id,
            "filename": artifact.filename,
            "cm_id": delivery.cm_id if delivery else None,
            "activity_name": delivery.activity_name if delivery else None,
            "status": technical.status,
            **(technical.metrics or {}),
        }
        if technical.modality == "VIDEO":
            video_rows.append(row)
        else:
            document_rows.append(row)

    doc_sizes = [float(row["size_bytes"]) for row in document_rows if row.get("size_bytes")]
    char_counts = [float(row["character_count"]) for row in document_rows if row.get("character_count")]
    word_counts = [float(row["word_count"]) for row in document_rows if row.get("word_count")]
    page_counts = [float(row["page_count"]) for row in document_rows if row.get("page_count")]
    video_sizes = [float(row["size_bytes"]) for row in video_rows if row.get("size_bytes")]
    durations = [float(row["duration_seconds"]) for row in video_rows if row.get("duration_seconds")]
    frame_rates = [float(row["fps"]) for row in video_rows if row.get("fps")]
    sampled_frames = [float(row["sampled_frames"]) for row in video_rows if row.get("sampled_frames")]

    document_metrics = {
        "count": len(document_rows),
        "total_size_bytes": int(sum(doc_sizes)),
        "average_size_bytes": _average(doc_sizes),
        "average_characters": _average(char_counts),
        "average_words": _average(word_counts),
        "average_pages": _average(page_counts),
        "total_characters": int(sum(char_counts)),
        "total_words": int(sum(word_counts)),
        "extractable_count": sum(bool(row.get("extractable_text")) for row in document_rows),
        "needs_review_count": sum(row.get("status") == "NEEDS_REVIEW" for row in document_rows),
    }
    video_metrics = {
        "count": len(video_rows),
        "total_size_bytes": int(sum(video_sizes)),
        "average_size_bytes": _average(video_sizes),
        "total_duration_seconds": round(sum(durations), 2),
        "average_duration_seconds": _average(durations),
        "minimum_duration_seconds": min(durations) if durations else None,
        "maximum_duration_seconds": max(durations) if durations else None,
        "average_fps": _average(frame_rates),
        "average_sampled_frames": _average(sampled_frames),
        "with_audio_count": sum(bool(row.get("has_audio")) for row in video_rows),
        "full_hd_or_higher_count": sum(
            int(row.get("width") or 0) >= 1920 and int(row.get("height") or 0) >= 1080
            for row in video_rows
        ),
        "transcribed_count": sum(
            row.get("transcription_status") == "COMPLETED" for row in video_rows
        ),
    }

    similarity_edges, similarity_meta = _cross_case_similarities(
        artifacts, artifact_delivery, case_by_id, texts or {}
    )
    feedback_types: Counter[str] = Counter()
    feedback_confidence: dict[str, list[float]] = defaultdict(list)
    for analysis in analyses:
        for finding in analysis.findings or []:
            finding_type = str(finding.get("type") or "OTHER")
            feedback_types[finding_type] += 1
            if finding.get("confidence") is not None:
                feedback_confidence[finding_type].append(float(finding["confidence"]))
    feedback_patterns = [
        {
            "type": finding_type,
            "count": count,
            "average_confidence": _average(feedback_confidence[finding_type]),
        }
        for finding_type, count in feedback_types.most_common()
    ]
    graph = _cluster_graph(cases, analyses, similarity_edges)
    rubric_analytics = _rubric_analytics(rubric_assessments, case_by_id)
    return {
        "document_metrics": document_metrics,
        "document_comparison": document_rows,
        "video_metrics": video_metrics,
        "video_comparison": video_rows,
        "similarity_edges": similarity_edges,
        "similarity_meta": similarity_meta,
        "feedback_patterns": feedback_patterns,
        "cluster_graph": graph,
        "rubric_analytics": rubric_analytics,
    }


def _rubric_analytics(
    assessments: list[RubricAssessment], case_by_id: dict[str, CaseFile]
) -> dict[str, Any]:
    dimension_levels: dict[str, list[int]] = defaultdict(list)
    dimension_distribution: dict[str, Counter[int]] = defaultdict(Counter)
    teacher_rows: dict[tuple[str, int], dict[str, Any]] = {}
    for assessment in assessments:
        level = assessment.validated_level or assessment.proposed_level
        dimension = assessment.criterion_ref.dimension
        dimension_levels[dimension].append(level)
        dimension_distribution[dimension][level] += 1
        key = (assessment.case_id, assessment.cm_id)
        case = case_by_id.get(assessment.case_id)
        row = teacher_rows.setdefault(
            key,
            {
                "case_id": assessment.case_id,
                "teacher": case.teacher_display_name or case.teacher_code if case else assessment.case_id,
                "cm_id": assessment.cm_id,
                "levels": [],
                "pending_validation": 0,
            },
        )
        row["levels"].append(level)
        row["pending_validation"] += assessment.validation_status != "VALIDATED_BY_HUMAN"
    for row in teacher_rows.values():
        row["average_level"] = _average([float(value) for value in row.pop("levels")])
    return {
        "assessment_count": len(assessments),
        "validated_count": sum(
            item.validation_status == "VALIDATED_BY_HUMAN" for item in assessments
        ),
        "dimensions": [
            {
                "dimension": dimension,
                "average_level": _average([float(value) for value in levels]),
                "level_4": dimension_distribution[dimension][4],
                "level_3": dimension_distribution[dimension][3],
                "level_2": dimension_distribution[dimension][2],
                "level_1": dimension_distribution[dimension][1],
            }
            for dimension, levels in dimension_levels.items()
        ],
        "by_teacher_cmid": list(teacher_rows.values()),
    }


def _shingles(text: str, size: int = 5) -> set[int]:
    words = re.findall(r"[a-záéíóúñü0-9]{2,}", text.lower())
    return {hash(tuple(words[i : i + size])) for i in range(max(len(words) - size + 1, 0))}


def _cross_case_similarities(
    artifacts: list[Artifact],
    artifact_delivery: dict[str, MoodleSubmissionRecord],
    case_by_id: dict[str, CaseFile],
    texts: dict[str, str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    documents = [
        artifact
        for artifact in artifacts
        if texts.get(artifact.id) and artifact.case_id in case_by_id
    ]
    pairs: dict[tuple[str, str], dict[str, Any]] = {}

    def add_pair(left: Artifact, right: Artifact, score: float, literal: float | None, method: str) -> None:
        key = tuple(sorted((left.id, right.id)))
        if key in pairs and float(pairs[key]["score"]) >= score:
            return
        left_delivery = artifact_delivery.get(left.id)
        right_delivery = artifact_delivery.get(right.id)
        left_case = case_by_id[left.case_id]
        right_case = case_by_id[right.case_id]
        pairs[key] = {
            "source_case_id": left.case_id,
            "target_case_id": right.case_id,
            "source_teacher": left_case.teacher_display_name or left_case.teacher_code,
            "target_teacher": right_case.teacher_display_name or right_case.teacher_code,
            "source_artifact_id": left.id,
            "target_artifact_id": right.id,
            "source_filename": left.filename,
            "target_filename": right.filename,
            "source_cm_id": left_delivery.cm_id if left_delivery else None,
            "target_cm_id": right_delivery.cm_id if right_delivery else None,
            "same_cmid": bool(
                left_delivery and right_delivery and left_delivery.cm_id == right_delivery.cm_id
            ),
            "score": round(score, 1),
            "literal": None if literal is None else round(literal, 1),
            "method": method,
        }

    exact_groups: dict[str, list[Artifact]] = defaultdict(list)
    for artifact in artifacts:
        exact_groups[artifact.content_hash].append(artifact)
    exact_pairs = 0
    for group in exact_groups.values():
        if len({item.case_id for item in group}) < 2:
            continue
        for left, right in combinations(group[:30], 2):
            if left.case_id != right.case_id and left.case_id in case_by_id and right.case_id in case_by_id:
                exact_pairs += 1
                add_pair(left, right, 100.0, 100.0, "EXACT_HASH")

    token_lists = [_tokens(texts[artifact.id]) for artifact in documents]
    document_frequency: Counter[str] = Counter()
    for tokens in token_lists:
        document_frequency.update(set(tokens))
    count = max(len(documents), 1)
    vectors: list[dict[str, float]] = []
    for tokens in token_lists:
        vector = {
            term: frequency * (math.log((count + 1) / (document_frequency[term] + 1)) + 1)
            for term, frequency in Counter(tokens).items()
        }
        norm = math.sqrt(sum(value * value for value in vector.values())) or 1.0
        vectors.append({term: value / norm for term, value in vector.items()})
    shingle_sets: dict[int, set[int]] = {}
    delivery_cm = [
        (artifact_delivery[artifact.id].cm_id if artifact.id in artifact_delivery else None)
        for artifact in documents
    ]
    same_activity_only = len(documents) > 400
    compared = 0
    for left_index, right_index in combinations(range(len(documents)), 2):
        left, right = documents[left_index], documents[right_index]
        if left.case_id == right.case_id:
            continue
        if same_activity_only and (
            delivery_cm[left_index] is None or delivery_cm[left_index] != delivery_cm[right_index]
        ):
            continue
        small, large = sorted((vectors[left_index], vectors[right_index]), key=len)
        similarity = sum(weight * large.get(term, 0.0) for term, weight in small.items()) * 100
        compared += 1
        if similarity < 1:
            continue
        literal = None
        if similarity >= 10:
            for index in (left_index, right_index):
                if index not in shingle_sets:
                    shingle_sets[index] = _shingles(texts[documents[index].id])
            left_set, right_set = shingle_sets[left_index], shingle_sets[right_index]
            if left_set and right_set:
                literal = len(left_set & right_set) / min(len(left_set), len(right_set)) * 100
        add_pair(left, right, similarity, literal, "TEXT_TFIDF")

    edges = sorted(pairs.values(), key=lambda item: item["score"], reverse=True)[:1500]
    scores = sorted(float(item["score"]) for item in pairs.values())
    buckets = [0] * 10
    for value in scores:
        buckets[min(int(value // 10), 9)] += 1
    document_artifacts = [item for item in artifacts if not _is_video_artifact(item)]
    meta = {
        "total_documents": len(document_artifacts),
        "documents_with_text": len(documents),
        "teachers_with_text": len({item.case_id for item in documents}),
        "pending_documents": len(document_artifacts) - len(documents),
        "pairs_compared": compared,
        "pairs_with_similarity": len(scores),
        "exact_duplicate_pairs": exact_pairs,
        "max_score": scores[-1] if scores else 0.0,
        "mean_score": round(sum(scores) / len(scores), 1) if scores else 0.0,
        "median_score": scores[len(scores) // 2] if scores else 0.0,
        "distribution": buckets,
        "same_activity_only": same_activity_only,
        "edge_min_score": EDGE_MIN_SCORE,
        "cluster_min_score": CLUSTER_MIN_SCORE,
    }
    return edges, meta


def _is_video_artifact(artifact: Artifact) -> bool:
    return artifact.mime_type.startswith("video/") or artifact.filename.lower().endswith(
        (".mp4", ".mov", ".webm")
    )


def _cluster_graph(
    cases: list[CaseFile], analyses: list[CaseAIAnalysis], edges: list[dict[str, Any]]
) -> dict[str, Any]:
    analysis_by_case = {item.case_id: item for item in analyses}
    adjacency: dict[str, set[str]] = {case.id: set() for case in cases}
    for edge in edges:
        if float(edge["score"]) >= CLUSTER_MIN_SCORE:
            adjacency[edge["source_case_id"]].add(edge["target_case_id"])
            adjacency[edge["target_case_id"]].add(edge["source_case_id"])
    cluster_by_case: dict[str, int] = {}
    cluster_id = 0
    for case in cases:
        if case.id in cluster_by_case:
            continue
        cluster_id += 1
        pending = [case.id]
        while pending:
            current = pending.pop()
            if current in cluster_by_case:
                continue
            cluster_by_case[current] = cluster_id
            pending.extend(adjacency[current] - cluster_by_case.keys())
    return {
        "nodes": [
            {
                "id": case.id,
                "label": case.teacher_display_name or case.teacher_code,
                "cluster": cluster_by_case[case.id],
                "ai_cluster": analysis_by_case[case.id].cluster_label
                if case.id in analysis_by_case
                else None,
            }
            for case in cases
        ],
        "edges": edges,
        "cluster_count": len(set(cluster_by_case.values())),
    }
