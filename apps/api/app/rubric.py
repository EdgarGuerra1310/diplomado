from sqlalchemy.orm import Session

from app.models import RubricCriterion

RUBRIC = [
    {
        "id": "MBDD_PLANIFICACION",
        "dimension": "Planificación pedagógica",
        "criterion": "Los propósitos de aprendizaje son claros y coherentes.",
        "level_4": "Los propósitos son precisos, pertinentes y totalmente alineados con las competencias y evidencias.",
        "level_3": "Los propósitos son claros y guardan coherencia con las competencias.",
        "level_2": "Los propósitos presentan inconsistencias o poca claridad.",
        "level_1": "Los propósitos son confusos o no guardan relación con las competencias.",
    },
    {
        "id": "MBDD_CONTEXTUALIZACION",
        "dimension": "Contextualización",
        "criterion": "Considera las características y necesidades de los estudiantes.",
        "level_4": "Integra de manera pertinente el contexto, intereses y diversidad de los estudiantes.",
        "level_3": "Considera las principales características del grupo.",
        "level_2": "Hace referencias generales al contexto sin incorporarlo plenamente.",
        "level_1": "No considera el contexto ni las características de los estudiantes.",
    },
    {
        "id": "MBDD_ESTRATEGIAS",
        "dimension": "Estrategias metodológicas",
        "criterion": "Selecciona estrategias que favorecen el aprendizaje.",
        "level_4": "Propone estrategias variadas, activas y pertinentes que promueven autonomía y pensamiento crítico.",
        "level_3": "Propone estrategias adecuadas para lograr el aprendizaje esperado.",
        "level_2": "Las estrategias son parcialmente pertinentes o poco variadas.",
        "level_1": "Las estrategias no favorecen el logro del aprendizaje.",
    },
    {
        "id": "MBDD_EVALUACION_FORMATIVA",
        "dimension": "Evaluación formativa",
        "criterion": "Diseña mecanismos para recoger evidencias y retroalimentar.",
        "level_4": "Los criterios, evidencias e instrumentos son coherentes y permiten una retroalimentación efectiva.",
        "level_3": "Existe coherencia entre criterios, evidencias e instrumentos.",
        "level_2": "La evaluación presenta inconsistencias o escasa relación con los propósitos.",
        "level_1": "No se evidencian criterios ni mecanismos adecuados de evaluación.",
    },
    {
        "id": "MBDD_INCLUSION",
        "dimension": "Inclusión y atención a la diversidad",
        "criterion": "Considera las diferentes necesidades de aprendizaje.",
        "level_4": "Incorpora adecuaciones y estrategias inclusivas pertinentes.",
        "level_3": "Considera algunas acciones para atender la diversidad.",
        "level_2": "Menciona la diversidad, pero sin estrategias claras.",
        "level_1": "No considera la diversidad del aula.",
    },
    {
        "id": "MBDD_REFLEXION",
        "dimension": "Reflexión pedagógica",
        "criterion": "Analiza críticamente su práctica y plantea mejoras.",
        "level_4": "Reflexiona de manera profunda sustentando fortalezas y oportunidades de mejora con evidencias.",
        "level_3": "Identifica fortalezas y aspectos por mejorar de forma pertinente.",
        "level_2": "La reflexión es superficial o poco fundamentada.",
        "level_1": "No realiza reflexión sobre su práctica.",
    },
]


def seed_rubric(db: Session) -> None:
    for order, item in enumerate(RUBRIC, start=1):
        criterion = db.get(RubricCriterion, item["id"])
        if criterion is None:
            criterion = RubricCriterion(id=item["id"])
            db.add(criterion)
        for key, value in item.items():
            if key != "id":
                setattr(criterion, key, value)
        criterion.display_order = order
        criterion.active = True
    db.commit()
