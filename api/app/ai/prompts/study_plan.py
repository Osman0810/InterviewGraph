from __future__ import annotations

from typing import Any


def build_study_plan_prompt(*, gaps: list[dict[str, Any]]) -> str:
    """Use saved signals only; never include résumé text or full interview answers."""
    return f"""Create a targeted technical interview study plan from the supplied competency signals.
Do not create a generic curriculum. Focus only on the listed gaps and role importance.
Do not infer technologies, achievements, or experience not present in these signals.

Put only highest-impact gaps in Critical, meaningful gaps in Important, and lower-impact reinforcement in Optional.
Each topic's priority must match its group: Critical, Important, or Optional.
Give practical, role-relevant objectives, concrete concepts, one hands-on task, and practice questions.

Competency signals:
{gaps}
"""
