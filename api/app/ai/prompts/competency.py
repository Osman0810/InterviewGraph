def build_competency_prompt(job_description: str) -> str:
    """Build the input for strict evidence-based competency extraction."""

    return f"""Analyze the following job description for technical-interview preparation.

Extract only competencies explicitly supported by the job description. Do not infer
requirements from a company, title, common industry expectations, or missing context.
Use the closest allowed category for each competency. Merge duplicate or synonymous
competencies into one canonical competency. Keep each jd_evidence value concise and
grounded in the source text. Include practical question topics that directly assess
the competency.

Job description:
---
{job_description}
---"""
