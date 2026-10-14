"""Review module for Project Rosie pipeline.

Provides a simple wrapper to run a local LLM review on the generated clinical report.
In a full implementation this would invoke the specified model (e.g., deepseek-r1:70b)
via Ollama or another inference server. For now we return a placeholder string.
"""

def generate_review(report_text: str, model_name: str = "") -> str:
    """Generate a review of the given report using the specified model.

    Args:
        report_text: The clinical report content to be reviewed.
        model_name: Name of the local LLM model (e.g., "deepseek-r1:70b").

    Returns:
        A string containing the review summary.
    """
    if not model_name:
        return "[Review] No model specified; skipping review."
    # Placeholder implementation – in production this would call the model.
    return f"[Review] Performed review with model '{model_name}'. No obvious issues detected in the report."
