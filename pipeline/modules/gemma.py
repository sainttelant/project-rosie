"""
Gemma 4 integration via Vertex AI.
Generates clinical reports, interprets visualizations, and produces mRNA synthesis specifications.
"""
import os
import json
import base64
from pathlib import Path
from google import genai
from google.genai import types

GCP_PROJECT = os.getenv("GCP_PROJECT_ID", "project-1ea30ea7-dc79-4a14-84b")
GCP_REGION  = os.getenv("GCP_REGION", "global")
MODEL       = os.getenv("GEMMA_MODEL", "gemma-4-26b-a4b-it-maas")

_SYSTEM_PROMPT_TEMPLATE = """You are an AI assistant helping {audience} understand personalized cancer vaccine candidates for their patients.

You will receive:
1. A JSON file with ranked neoantigen candidates identified from a tumor DNA sample
2. Two charts: a binding affinity bar chart and a mutation landscape pie chart

Your job is to write a clear, honest clinical report that {audience_short} can act on.

Report structure:
- Case Summary (2-3 sentences: species, cancer type if known, total mutations analyzed, candidates identified)
- Top Vaccine Candidates (explain the top 3-5 in plain language: what gene is affected, why this peptide was ranked highly, what the IC50 score means in practical terms)
- Visual Findings (interpret what the charts show — binding affinity distribution, mutation type breakdown)
- Recommended Next Steps (what the oncologist should do with this information — consult with RNA synthesis lab, consider immunotherapy combination, etc.)
- Limitations and Uncertainties (be honest: what the pipeline cannot tell them, what validation is still needed)

{species_notes}

Tone: clinical but accessible. No jargon without explanation. Write for {audience_tone}.
Length: 400-600 words."""

_SPECIES_CONFIG = {
    "canis_lupus_familiaris": {
        "audience":      "veterinary oncologists",
        "audience_short": "a veterinary oncologist",
        "audience_tone": "a vet who is expert in oncology but not in computational biology",
        "species_notes": (
            "The alleles are DLA (Dog Leukocyte Antigen) alleles, not human HLA. "
            "Name them explicitly — e.g. \"DLA-88*50101\" — when discussing which alleles each peptide binds. "
            "IC50 thresholds: < 50 nM = strong binder, 50–500 nM = weak binder."
        ),
    },
    "homo_sapiens": {
        "audience":      "oncologists",
        "audience_short": "an oncologist",
        "audience_tone": "a clinician who is expert in oncology but not in computational biology",
        "species_notes": (
            "The alleles are HLA (Human Leukocyte Antigen) alleles. "
            "Use HLA allele names as given (e.g. \"HLA-A*02:01\"). "
            "IC50 thresholds: < 50 nM = strong binder, 50–500 nM = weak binder."
        ),
    },
    "felis_catus": {
        "audience":      "veterinary oncologists",
        "audience_short": "a veterinary oncologist",
        "audience_tone": "a vet who is expert in oncology but not in computational biology",
        "species_notes": (
            "This is a feline case. The MHC alleles are feline leukocyte antigen (FLA) alleles. "
            "IC50 thresholds: < 50 nM = strong binder, 50–500 nM = weak binder."
        ),
    },
}

_DEFAULT_SPECIES_CONFIG = {
    "audience":      "oncologists",
    "audience_short": "an oncologist",
    "audience_tone": "a clinician who is expert in oncology but not in computational biology",
    "species_notes": "Use allele names as given. IC50 thresholds: < 50 nM = strong binder, 50–500 nM = weak binder.",
}


def _build_system_prompt(species: str) -> str:
    cfg = _SPECIES_CONFIG.get(species, _DEFAULT_SPECIES_CONFIG)
    return _SYSTEM_PROMPT_TEMPLATE.format(**cfg)


def _encode_image(path: str) -> tuple[str, str]:
    data = Path(path).read_bytes()
    return base64.b64encode(data).decode(), "image/png"


# ── Local (Ollama) backend ────────────────────────────────────────────────────
# Set GEMMA_BACKEND=ollama to route report generation through a local Ollama
# server instead of Vertex AI. Useful for offline / zero-cost runs.
OLLAMA_URL   = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:31b")


def _backend() -> str:
    return os.getenv("GEMMA_BACKEND", "vertex").strip().lower()


def _generate_via_ollama(system_prompt: str, summary: dict,
                         binding_affinity_png: str, mutation_landscape_png: str) -> str:
    """Generate the clinical report via a local Ollama server (OpenAI-style chat API).

    gemma4 is a *thinking* model: it emits a `thinking` field before the final
    `content`. We give it a generous token budget so the answer is not cut off
    inside the reasoning phase.
    """
    import requests

    text = (
        system_prompt + "\n\n"
        + "Here are the ranked neoantigen candidates:\n\n```json\n"
        + json.dumps(summary, indent=2) + "\n```\n\n"
        + "Please write the clinical report now."
    )

    images = []
    for p in (binding_affinity_png, mutation_landscape_png):
        if p and Path(p).exists():
            images.append(base64.b64encode(Path(p).read_bytes()).decode())

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": text, "images": images}],
        "stream": False,
        "options": {"num_predict": 4096, "temperature": 0.3},
    }

    print(f"[gemma] Using local Ollama backend: {OLLAMA_URL} / {OLLAMA_MODEL}", flush=True)
    resp = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=900)
    resp.raise_for_status()
    data = resp.json()
    content = data.get("message", {}).get("content", "").strip()
    if not content:
        raise RuntimeError(
            "Ollama returned an empty report. "
            f"thinking={data.get('message', {}).get('thinking', '')[:200]!r}"
        )
    return content


def generate_clinical_report(
    candidates_json_path: str,
    binding_affinity_png: str,
    mutation_landscape_png: str,
    bilingual: bool = False,
) -> str:
    client = genai.Client(vertexai=True, project=GCP_PROJECT, location=GCP_REGION)

    with open(candidates_json_path) as f:
        candidates = json.load(f)

    species = candidates.get("species", "homo_sapiens")
    system_prompt = _build_system_prompt(species)
    # If bilingual output is requested, extend the prompt with explicit instruction.
    if bilingual:
        system_prompt += "\nPlease write the clinical report first in English, then repeat the same content in Chinese."

    summary = {
        "case_id":                    candidates["case_id"],
        "species":                    species,
        "alleles":                    candidates["alleles"],
        "total_mutations_analyzed":   candidates["total_mutations_analyzed"],
        "candidates_after_filtering": candidates["candidates_after_filtering"],
        "top_candidates":             candidates["top_candidates"][:5],
    }

    # ── Local Ollama backend (offline / zero-cost) ──
    if _backend() == "ollama":
        report = _generate_via_ollama(
            system_prompt=system_prompt,
            summary=summary,
            binding_affinity_png=binding_affinity_png,
            mutation_landscape_png=mutation_landscape_png,
        )
        return _embed_images(
            report=report,
            binding_affinity_png=binding_affinity_png,
            mutation_landscape_png=mutation_landscape_png,
        )

    parts = [
        types.Part(text=system_prompt),
        types.Part(text=f"Here are the ranked neoantigen candidates:\n\n```json\n{json.dumps(summary, indent=2)}\n```"),
    ]

    if Path(binding_affinity_png).exists():
        ba_data, ba_mime = _encode_image(binding_affinity_png)
        parts.append(types.Part(text="Binding affinity chart:"))
        parts.append(types.Part(inline_data=types.Blob(mime_type=ba_mime, data=ba_data)))

    if Path(mutation_landscape_png).exists():
        ml_data, ml_mime = _encode_image(mutation_landscape_png)
        parts.append(types.Part(text="Somatic mutation landscape:"))
        parts.append(types.Part(inline_data=types.Blob(mime_type=ml_mime, data=ml_data)))

    parts.append(types.Part(text="Please write the clinical report now."))

    contents = [types.Content(role="user", parts=parts)]

    response = client.models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            max_output_tokens=1024,
            temperature=0.3,
        ),
    )

    return _embed_images(
        report=response.text,
        binding_affinity_png=binding_affinity_png,
        mutation_landscape_png=mutation_landscape_png,
    )


def _embed_images(report: str, binding_affinity_png: str, mutation_landscape_png: str) -> str:
    ba_name = Path(binding_affinity_png).name
    ml_name = Path(mutation_landscape_png).name

    ba_block = f"\n![Binding Affinity Chart](./{ba_name})\n"
    ml_block = f"\n![Mutation Landscape](./{ml_name})\n"

    # Inject after the Visual Findings header if present, otherwise append at end
    visual_headers = ["**Visual Findings**", "## Visual Findings", "### Visual Findings"]
    next_section_markers = ["**Recommended", "## Recommended", "### Recommended",
                            "**Limitations", "## Limitations", "### Limitations"]

    lines = report.splitlines(keepends=True)
    result = []
    i = 0
    inserted_ba = False
    inserted_ml = False

    while i < len(lines):
        line = lines[i]
        result.append(line)

        # After the Visual Findings header, inject binding affinity chart first
        if not inserted_ba and any(h in line for h in visual_headers):
            result.append(ba_block)
            inserted_ba = True

        # Before the next major section after Visual Findings, inject mutation landscape
        if inserted_ba and not inserted_ml and any(m in line for m in next_section_markers):
            result.insert(-1, ml_block)  # insert before this line
            inserted_ml = True

        i += 1

    # Fallback: append both at the end if headers not found
    if not inserted_ba:
        result.append(f"\n---\n{ba_block}{ml_block}")
    elif not inserted_ml:
        result.append(ml_block)

    return "".join(result)
