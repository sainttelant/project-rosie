"""
AlphaFold2 structural validation module (Phase 2).

Predicts wild-type protein structures via the official AlphaFold2 Docker image,
then extracts per-residue pLDDT confidence and surface exposure (SASA) at each
candidate epitope's mutation site.

Design notes:
- Uses WILD-TYPE structures: a point mutation rarely changes overall folding,
  so one structure per protein serves all its candidate epitopes.
- Runs AF2 as a separate GPU container (same pattern as annotation.py for VEP):
  data crosses the container boundary only via mounted volumes.
- The pipeline image stays CPU-only; this module shells out to `docker run`.

Environment prerequisites (see README_ALPHAFOLD.md):
- Image built:  docker build -f docker/Dockerfile -t alphafold:local .
- Databases:    /data_fast/aplha_data  (reduced_dbs preset)
- GPU:          free VRAM on the target device (ollama moved off it)

Outputs per candidate:
- plddt:            pLDDT confidence at the mutation residue (0-100)
- surface_exposed:  True if the mutation site is accessible to solvent
- sasa_fraction:    relative solvent accessibility of the mutation residue
"""
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path

import numpy as np

# ─── Configuration ────────────────────────────────────────────────────────────

AF2_IMAGE       = "alphafold:local"
AF2_DATA_DIR    = "/data_fast/aplha_data"   # reduced_dbs databases
AF2_GPU_DEVICE  = "0"                        # --gpus '"device=0"'

# Hard-filter thresholds (mirrors HARD_FILTER_* in scoring.py)
PLDDT_MIN       = 70.0    # below this, the local structure is unreliable
SASA_MIN        = 0.20    # <20% solvent-accessible → treated as buried

# SASA probe geometry (Å)
PROBE_RADIUS    = 1.4     # water oxygen probe
VDW_RADIUS_CA   = 1.8     # effective radius of a heavy atom for occlusion
N_PROBE_POINTS  = 120     # Fibonacci-sphere sampling points per residue


# ─── Step 1: collect unique proteins to fold ─────────────────────────────────

def _parse_hgsp_position(hgvsp: str) -> int | None:
    """Extract the residue position from an HGVSp string, e.g. 'p.Arg123Pro' → 123."""
    m = re.search(r"p\.[A-Z][a-z]{2}(\d+)", hgvsp or "")
    return int(m.group(1)) if m else None


def _load_protein_fasta(fasta_path: str) -> dict[str, str]:
    """
    Load a FASTA file into {name: sequence}.

    Indexes each sequence under EVERY token of its header (pVACseq headers look
    like 'ENST00000471741|TP53|...' so both transcript and gene names resolve).
    """
    seqs: dict[str, str] = {}
    name = None
    chunks: list[str] = []
    with open(fasta_path) as fh:
        for line in fh:
            line = line.strip()
            if line.startswith(">"):
                if name is not None:
                    seqs[name] = "".join(chunks)
                name = line[1:].split()[0]
                chunks = []
            elif name is not None:
                chunks.append(line)
    if name is not None:
        seqs[name] = "".join(chunks)

    indexed: dict[str, str] = {}
    for full_name, seq in seqs.items():
        indexed[full_name] = seq
        for token in full_name.replace("|", " ").split():
            indexed[token] = seq
    return indexed


def find_protein_fasta(output_dir: str, explicit_path: str | None = None) -> str | None:
    """
    Locate the wild-type protein FASTA.

    Priority: explicit path > pVACseq's 'protein_fasta' in the output dir
    (pVACseq emits it automatically — no external download needed).
    """
    if explicit_path:
        return explicit_path if Path(explicit_path).exists() else None
    for candidate in (
        Path(output_dir) / "protein_fasta",
        Path(output_dir) / "MHC_Class_I" / "protein_fasta",
    ):
        if candidate.exists():
            return str(candidate)
    return None


def collect_targets(
    candidates_json_path: str,
    protein_fasta_path: str,
) -> dict[str, list[int]]:
    """
    Group top candidates by protein and collect the residue positions to check.

    Returns {protein_name: sorted list of mutation positions}.
    Proteins without a sequence in the FASTA are skipped with a warning.

    TODO(phase2): protein_fasta_path must contain WILD-TYPE sequences keyed by
    the same name used in candidates' 'transcript' field. Upstream source is
    not yet wired — for now the caller provides the FASTA explicitly.
    """
    with open(candidates_json_path) as fh:
        data = json.load(fh)

    seqs = _load_protein_fasta(protein_fasta_path)

    positions: dict[str, set[int]] = defaultdict(set)
    for cand in data["top_candidates"]:
        name = cand.get("transcript") or cand.get("gene") or ""
        pos = _parse_hgsp_position(cand.get("hgvsp", ""))
        if not name or pos is None:
            continue
        if name not in seqs:
            print(f"[structure] WARNING: no sequence for {name!r} — skipping", flush=True)
            continue
        if pos > len(seqs[name]):
            print(f"[structure] WARNING: {name} pos {pos} exceeds seq length — skipping", flush=True)
            continue
        positions[name].add(pos)

    return {name: sorted(pos) for name, pos in positions.items()}


# ─── Step 2: run AlphaFold2 in Docker ────────────────────────────────────────

def predict_structures(
    targets: dict[str, list[int]],
    protein_fasta_path: str,
    output_dir: str,
    data_dir: str = AF2_DATA_DIR,
    image: str = AF2_IMAGE,
    gpu_device: str = AF2_GPU_DEVICE,
) -> dict[str, Path]:
    """
    Fold all target proteins in a single AF2 container run.

    Returns {protein_name: path to <output_dir>/<name>/ ranked_0.pdb}.
    Raises RuntimeError if the container exits non-zero.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # One multi-sequence FASTA is NOT valid for monomer mode (AF2 would treat
    # it as a multimer). Write one single-sequence FASTA per protein instead.
    fasta_dir = out / "_fastas"
    fasta_dir.mkdir(exist_ok=True)
    seqs = _load_protein_fasta(protein_fasta_path)
    fasta_paths = []
    for name in targets:
        fp = fasta_dir / f"{name}.fasta"
        fp.write_text(f">{name}\n{seqs[name]}\n")
        fasta_paths.append(str(fp))

    # Database paths (reduced_dbs preset — must match what was downloaded)
    d = Path(data_dir)
    db_paths = [
        ("data_dir",                str(d)),
        ("small_bfd_database_path", str(d / "small_bfd" / "bfd-first_non_consensus_sequences.fasta")),
        ("mgnify_database_path",    str(d / "mgnify" / "mgy_clusters_2022_05.fa")),
        ("uniref90_database_path",  str(d / "uniref90" / "uniref90.fasta")),
        ("pdb70_database_path",     str(d / "pdb70" / "pdb70")),
        ("template_mmcif_dir",      str(d / "pdb_mmcif" / "mmcif_files")),
        ("obsolete_pdbs_path",      str(d / "pdb_mmcif" / "obsolete.dat")),
    ]
    for _, p in db_paths:
        if not Path(p).exists():
            raise FileNotFoundError(f"AF2 database missing: {p} — is the download complete?")

    cmd = [
        "docker", "run", "--rm",
        "--gpus", f'"device={gpu_device}"',
        "-v", f"{d}:{d}:ro",
        "-v", f"{fasta_dir}:{fasta_dir}:ro",
        "-v", f"{out}:{out}",
        image,
        "--fasta_paths=" + ",".join(fasta_paths),
        "--output_dir=" + str(out),
        "--db_preset=reduced_dbs",
        "--model_preset=monomer",
        "--models_to_relax=best",
        # run_alphafold.py requires these two flags to be non-None
        # (absl flags, NOT env vars — the image entrypoint just passes "$@"):
        "--max_template_date=2021-09-30",
        "--use_gpu_relax=true",
    ]
    for name, p in db_paths:
        if name != "data_dir":
            cmd.append(f"--{name}={p}")

    print(f"[structure] Folding {len(targets)} protein(s) via {image} (GPU {gpu_device})...", flush=True)
    result = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        stderr_tail = (result.stderr or "")[-3000:]
        raise RuntimeError(f"AlphaFold2 exited {result.returncode}.\nSTDERR:\n{stderr_tail}")

    pdb_paths: dict[str, Path] = {}
    for name in targets:
        pdb = out / name / "ranked_0.pdb"
        if not pdb.exists():
            raise FileNotFoundError(f"AF2 output missing for {name}: {pdb}")
        pdb_paths[name] = pdb
    return pdb_paths


# ─── Step 3: extract pLDDT + surface exposure ────────────────────────────────

def extract_plddt(target_out_dir: Path) -> np.ndarray | None:
    """
    Per-residue pLDDT from ranking_debug.json (preferred) or PDB B-factors.
    Returns array of shape (n_res,) or None if unavailable.
    """
    debug = target_out_dir / "ranking_debug.json"
    if debug.exists():
        with open(debug) as fh:
            data = json.load(fh)
        # ranking_debug.json: {model_name: {residue_index: plddt}}
        for entry in data.values():
            if isinstance(entry, dict) and entry:
                idx = sorted(int(k) for k in entry)
                return np.array([float(entry[k]) for k in idx])
    # Fallback: B-factor column of ranked_0.pdb (pLDDT is stored there)
    pdb = target_out_dir / "ranked_0.pdb"
    if pdb.exists():
        vals = []
        with open(pdb) as fh:
            for line in fh:
                if line.startswith("ATOM") and line[12:16].strip() == "CA":
                    vals.append(float(line[60:66]))
        if vals:
            return np.array(vals)
    return None


def _fibonacci_sphere(n: int, radius: float) -> np.ndarray:
    """n points roughly uniformly distributed on a sphere of given radius."""
    i = np.arange(n)
    golden = np.pi * (3.0 - np.sqrt(5.0))
    y = 1.0 - (i / max(n - 1, 1)) * 2.0
    r = np.sqrt(np.clip(1.0 - y * y, 0.0, 1.0))
    theta = golden * i
    return radius * np.stack([np.cos(theta) * r, y, np.sin(theta) * r], axis=1)


def sasa_fraction(pdb_path: Path, residue_positions: list[int]) -> dict[int, float]:
    """
    Relative solvent accessibility at given 1-based residue positions.

    Heuristic: for each residue's CA atom, sample points on a probe sphere
    (PROBE_RADIUS) and measure the fraction NOT occluded by any heavy atom
    within (PROBE_RADIUS + VDW_RADIUS_CA). 1.0 = fully exposed, 0.0 = buried.

    This is a fast geometric proxy, not a rigorous Lee-Richards SASA —
    sufficient for a buried/surface hard filter.
    """
    from Bio.PDB import PDBParser
    from Bio.PDB.Polypeptide import is_aa

    parser = PDBParser(QUIET=True)
    structure = parser.get_structure("target", str(pdb_path))

    # Collect heavy-atom coordinates (exclude hydrogens)
    coords: list[np.ndarray] = []
    ca_by_resnum: dict[int, np.ndarray] = {}
    for chain in structure.get_chains():
        for res in chain.get_residues():
            if not is_aa(res.get_id()):
                continue
            for atom in res:
                if atom.element == "H":
                    continue
                c = np.array(atom.get_coord(), dtype=np.float64)
                coords.append(c)
                if atom.name == "CA" and res.get_id() not in ca_by_resnum:
                    ca_by_resnum[res.get_id()] = c

    if not coords:
        raise RuntimeError(f"No atoms parsed from {pdb_path}")
    all_coords = np.stack(coords)  # (N, 3)

    probes = _fibonacci_sphere(N_PROBE_POINTS, PROBE_RADIUS)  # (P, 3)
    cutoff = PROBE_RADIUS + VDW_RADIUS_CA

    result: dict[int, float] = {}
    for pos in residue_positions:
        if pos not in ca_by_resnum:
            result[pos] = 0.0  # residue not modeled → treat as buried
            continue
        ca = ca_by_resnum[pos]
        # distance from each probe point (on the sphere around CA) to every atom
        d = np.min(np.linalg.norm(all_coords[None, :, :] - (ca + probes)[:, None, :], axis=2), axis=1)
        result[pos] = float(np.mean(d > cutoff))
    return result


# ─── Step 4: annotate candidates ─────────────────────────────────────────────

def annotate_candidates(
    candidates_json_path: str,
    output_dir: str,
    protein_fasta_path: str | None = None,
    data_dir: str = AF2_DATA_DIR,
    image: str = AF2_IMAGE,
    gpu_device: str = AF2_GPU_DEVICE,
    apply_filter: bool = True,
) -> str:
    """
    End-to-end: fold → extract pLDDT/SASA → annotate (and optionally filter)
    the candidates JSON. Returns the path to the annotated JSON.

    protein_fasta_path may be omitted — the wild-type protein FASTA is then
    auto-located (pVACseq emits 'protein_fasta' in the output dir).

    apply_filter=True  → candidates failing PLDDT_MIN / SASA_MIN are dropped
                         and the remaining list are re-ranked (composite order kept).
    apply_filter=False → fields are added but nothing is dropped (reporting only).
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    fasta = find_protein_fasta(output_dir, protein_fasta_path)
    if fasta is None:
        raise FileNotFoundError(
            "No wild-type protein FASTA found. Provide --protein-fasta or run "
            "pVACseq first (it emits 'protein_fasta' in the output dir)."
        )
    print(f"[structure] Using protein FASTA: {fasta}", flush=True)

    targets = collect_targets(candidates_json_path, fasta)
    if not targets:
        print("[structure] No foldable targets — returning candidates unchanged.", flush=True)
        return candidates_json_path

    pdb_paths = predict_structures(targets, fasta, str(out),
                                   data_dir=data_dir, image=image, gpu_device=gpu_device)

    # Per-protein structural metrics
    metrics: dict[str, dict] = {}
    for name, pdb in pdb_paths.items():
        target_dir = pdb.parent
        plddt = extract_plddt(target_dir)
        sasa = sasa_fraction(pdb, targets[name])
        metrics[name] = {"plddt": plddt, "sasa": sasa, "pdb": str(pdb)}
        print(f"[structure] {name}: {len(targets[name])} site(s) checked, "
              f"pdb → {pdb}", flush=True)

    with open(candidates_json_path) as fh:
        data = json.load(fh)

    kept = []
    for cand in data["top_candidates"]:
        name = cand.get("transcript") or cand.get("gene") or ""
        pos = _parse_hgsp_position(cand.get("hgvsp", ""))
        m = metrics.get(name)
        if m and pos is not None and pos in m["sasa"]:
            plddt_val = float(m["plddt"][pos - 1]) if m["plddt"] is not None else None
            sasa_val = m["sasa"][pos]
            cand["plddt"] = round(plddt_val, 1) if plddt_val is not None else None
            cand["sasa_fraction"] = round(sasa_val, 3)
            cand["surface_exposed"] = sasa_val >= SASA_MIN
            if apply_filter:
                if plddt_val is not None and plddt_val < PLDDT_MIN:
                    print(f"[structure] FILTERED {name} pos {pos}: pLDDT {plddt_val:.1f} < {PLDDT_MIN}", flush=True)
                    continue
                if not cand["surface_exposed"]:
                    print(f"[structure] FILTERED {name} pos {pos}: SASA {sasa_val:.2f} < {SASA_MIN}", flush=True)
                    continue
        kept.append(cand)

    # Re-rank: keep original composite order, renumber ranks
    for i, cand in enumerate(kept):
        cand["rank"] = i + 1

    data["top_candidates"] = kept
    data["structure_validation"] = {
        "applied": apply_filter,
        "proteins_folded": list(targets.keys()),
        "plddt_min": PLDDT_MIN,
        "sasa_min": SASA_MIN,
        "pdb_paths": {name: m["pdb"] for name, m in metrics.items()},
    }

    annotated_path = out / Path(candidates_json_path).name
    with open(annotated_path, "w") as fh:
        json.dump(data, fh, indent=2)

    print(f"[structure] {len(kept)}/{len(data['top_candidates'])} candidates kept → {annotated_path}", flush=True)
    return str(annotated_path)


# ─── Standalone smoke test ────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="AlphaFold2 structural validation (standalone)")
    p.add_argument("--candidates", required=True, help="Path to candidates JSON")
    p.add_argument("--protein-fasta", default=None,
                   help="FASTA of wild-type protein sequences (default: auto-locate pVACseq 'protein_fasta')")
    p.add_argument("--output-dir", default="output/structure")
    p.add_argument("--data-dir", default=AF2_DATA_DIR)
    p.add_argument("--gpu", default=AF2_GPU_DEVICE)
    p.add_argument("--no-filter", action="store_true", help="Annotate only, do not filter")
    a = p.parse_args()
    annotate_candidates(a.candidates, a.output_dir,
                        protein_fasta_path=a.protein_fasta,
                        data_dir=a.data_dir, gpu_device=a.gpu,
                        apply_filter=not a.no_filter)
