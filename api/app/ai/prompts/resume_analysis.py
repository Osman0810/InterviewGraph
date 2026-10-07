from collections.abc import Sequence


def build_resume_analysis_prompt(resume_text: str, competencies: Sequence[object]) -> str:
    """Build one evidence-only résumé analysis prompt for the full competency graph."""

    competency_context = "\n".join(
        f"- Name: {item.name}\n  Category: {item.category}\n  Description: {item.description}\n"
        f"  Required level: {item.required_level}\n  JD evidence: {item.jd_evidence}"
        for item in competencies
    )
    return f"""Analyze the résumé against every supplied job-description competency in one pass.

Return one result for every supplied competency name, using that exact name. Ground all
evidence strictly in the résumé. Never invent employers, projects, technologies,
responsibilities, achievements, or qualifications. Absence from the résumé is not proof
that the candidate lacks a skill; state only that no meaningful résumé evidence was found.

Use evidence_strength as follows:
- 0-20: no meaningful résumé evidence
- 21-40: skill mentioned with little demonstrated use
- 41-60: some practical evidence
- 61-80: strong demonstrated experience
- 81-100: repeated or substantial demonstrated experience

Competencies:
---
{competency_context}
---

Résumé:
---
{resume_text}
---"""
