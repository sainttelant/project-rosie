"""
Wraps pvacseq run as a Python function.
Returns the path to the MHC_Class_I all_epitopes.tsv output file.
"""
import subprocess
import os
import csv
import json
import shutil
from pathlib import Path

MHC_II_PREDICTORS = {"NetMHCIIpan", "NetMHCIIpanEL", "NNalign", "SMMalign", "MHCnuggetsII", "MixMHC2pred"}


def validate_mhcii(alleles: list[str], predictors: list[str], epitope_lengths: str) -> None:
    """Validate explicit class-II configuration without substituting class-I alleles."""
    if not alleles or any(not allele for allele in alleles):
        raise ValueError("MHC-II requires explicit --mhc-ii-alleles")
    if any(allele.startswith(("DLA-88", "HLA-A", "HLA-B", "HLA-C")) for allele in alleles):
        raise ValueError("MHC-I alleles cannot be used for MHC-II prediction")
    if not predictors or any(predictor not in MHC_II_PREDICTORS for predictor in predictors):
        raise ValueError(f"Choose MHC-II predictors from {sorted(MHC_II_PREDICTORS)}")
    try:
        lengths = [int(length) for length in epitope_lengths.split(",")]
    except ValueError as error:
        raise ValueError("MHC-II lengths must be comma-separated integers") from error
    if any(length < 11 or length > 30 for length in lengths):
        raise ValueError("MHC-II epitope lengths must be between 11 and 30")


def run_pvacseq_mhcii(
    vcf_path: str,
    sample_name: str,
    alleles: list[str],
    predictors: list[str],
    output_dir: str,
    epitope_lengths: str = "15",
) -> str:
    """Run class II in a dedicated directory, preserving all class-I artifacts."""
    validate_mhcii(alleles, predictors, epitope_lengths)
    if shutil.which("pvacseq") is None:
        raise RuntimeError("pvacseq is not installed; use the pipeline image or --mhc-ii-tsv")
    if shutil.which("pvactools") is None:
        raise RuntimeError("pvactools is not installed; it is required to query supported alleles")
    for predictor in predictors:
        if predictor == "MixMHC2pred" and shutil.which(predictor) is None:
            raise RuntimeError("MixMHC2pred is not installed; install its licensed distribution first")
        supported = subprocess.run(
            ["pvactools", "valid_alleles", "-p", predictor],
            capture_output=True, text=True,
        )
        if supported.returncode != 0:
            raise RuntimeError(f"Cannot query {predictor} supported alleles: {supported.stderr[-2000:]}")
        supported_alleles = set(supported.stdout.split())
        unsupported = [allele for allele in alleles if allele not in supported_alleles]
        if unsupported:
            raise ValueError(f"{predictor} does not support MHC-II alleles {unsupported}; no HLA/DLA substitution is permitted")

    vcf_sample = _vcf_sample_id(vcf_path)
    out = Path(output_dir) / "mhc_ii"
    out.mkdir(parents=True, exist_ok=True)
    cmd = ["pvacseq", "run", str(vcf_path), vcf_sample, ",".join(alleles),
           *predictors, str(out), "-e2", epitope_lengths, "-m", "median", "-b", "500", "-c", "1"]
    print(f"[prediction] MHC-II for {sample_name}: {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"MHC-II pVACseq exited {result.returncode}.\nSTDERR:\n{(result.stderr or '')[-2000:]}")
    tsv = out / "MHC_Class_II" / f"{vcf_sample}.MHC_II.all_epitopes.tsv"
    if not tsv.is_file():
        raise FileNotFoundError(f"Expected MHC-II pVACseq output not found: {tsv}")
    return str(tsv)


def attach_mhcii_results(
    candidates_json_path: str,
    tsv_path: str,
    alleles: list[str],
    predictors: list[str],
    epitope_lengths: str,
    reused: bool = False,
) -> str:
    """Attach unfiltered class-II evidence separately and return a deterministic report section."""
    lengths = {int(length) for length in epitope_lengths.split(",")}
    preview = []
    total = 0
    with open(tsv_path, newline="") as source:
        reader = csv.DictReader(source, delimiter="\t")
        if not {"MT Epitope Seq", "HLA Allele"}.issubset(reader.fieldnames or []):
            raise ValueError("MHC-II TSV requires MT Epitope Seq and HLA Allele columns")
        for row in reader:
            if row["HLA Allele"] not in alleles or len(row["MT Epitope Seq"]) not in lengths:
                raise ValueError("MHC-II TSV contains an allele or peptide length outside the requested configuration")
            total += 1
            if len(preview) < 20:
                preview.append({
                    "peptide": row["MT Epitope Seq"], "gene": row.get("Gene Name", "NA"),
                    "allele": row["HLA Allele"],
                    "ic50_nm": row.get("Median MT IC50 Score", "NA"),
                    "percentile_rank": row.get("Median MT Percentile", "NA"),
                })
    path = Path(candidates_json_path)
    data = json.loads(path.read_text())
    data["mhc_ii"] = {
        "status": "reused" if reused else "predicted",
        "alleles": alleles, "predictors": predictors, "epitope_lengths": sorted(lengths),
        "all_epitopes_tsv": str(Path(tsv_path).resolve()), "total_epitopes": total,
        "preview": preview, "selection": "First 20 unfiltered rows; not ranked or included in the CTL construct",
    }
    data.setdefault("visualization_paths", {})["mhc_ii_tsv"] = str(Path(tsv_path).resolve())
    path.write_text(json.dumps(data, indent=2))
    lines = ["## MHC-II Prediction (Research Only)", "",
             f"Source: `{tsv_path}` ({'reused' if reused else 'new prediction'}).",
             f"Algorithms: {', '.join(predictors)}. Alleles: {', '.join(alleles)}.",
             f"Total predicted epitope/allele rows: {total}. Preview: first {len(preview)} unfiltered rows.", "",
             "These results are separate from MHC-I ranking and are not automatically encoded in the vaccine.",
             "Binding prediction alone does not demonstrate CD4 activation or canine applicability.", "",
             "| Peptide | Gene | Allele | Median IC50 (nM) | Median percentile |",
             "|---|---|---|---|---|"]
    for row in preview:
        cells = [str(row[key]).replace("|", "\\|").replace("\n", " ")
                 for key in ("peptide", "gene", "allele", "ic50_nm", "percentile_rank")]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def _dla_numeric_to_star(allele: str) -> str:
    """Convert numeric DLA format to star format.
    DLA-8850101 → DLA-88*501:01
    DLA-8803401 → DLA-88*034:01
    Already-star alleles are returned unchanged.
    """
    if "*" in allele:
        return allele
    # DLA-<2 digits><3 digits><2 digits>
    import re
    m = re.match(r"^(DLA-\d{2})(\d{3})(\d{2})$", allele)
    if m:
        return f"{m.group(1)}*{m.group(2)}:{m.group(3)}"
    return allele


def _vcf_sample_id(vcf_path: str) -> str:
    """Return the first sample column name from the VCF #CHROM header line."""
    with open(vcf_path) as fh:
        for line in fh:
            if line.startswith("#CHROM"):
                cols = line.strip().split("\t")
                # Columns after FORMAT (index 8) are sample IDs
                if len(cols) > 9:
                    return cols[9]
                break
    return "TUMOR"  # safe fallback


def run_pvacseq(
    vcf_path: str,
    sample_name: str,
    alleles: list[str],
    predictors: list[str],
    output_dir: str,
    epitope_lengths: str = "8,9,10,11",
) -> str:
    # pVACseq requires sample_name to match a column in the VCF #CHROM header.
    # The user-facing display name won't match, so read the actual sample ID.
    vcf_sample = _vcf_sample_id(vcf_path)
    print(f"[prediction] VCF sample ID: {vcf_sample!r} (display name: {sample_name!r})", flush=True)

    # If any allele is a canine DLA identifier, use MixMHCpred (installed) which
    # supports non‑human alleles, and drop human‑only predictors.
    if any(a.startswith("DLA-") for a in alleles):
        # Remove MHCflurry and any mhcnuggets entries (they reject DLA).
        predictors = [p for p in predictors if p.lower() not in ("mhcflurry", "mhcnuggets", "mhcnuggetsI", "mhcnuggetsII")]
        # Ensure MixMHCpred is present (pvacseq recognises this name).
        if "MixMHCpred" not in predictors:
            predictors.append("MixMHCpred")
        # pVACseq's MixMHCpred whitelist uses star format (DLA-88*501:01).
        # Convert numeric DLA alleles (DLA-8850101) to star format.
        alleles = [_dla_numeric_to_star(a) for a in alleles]
        print(f"[prediction] DLA alleles detected → predictors: {predictors}, alleles: {alleles}", flush=True)

    alleles_str = ",".join(alleles)

    algorithms_str = " ".join(predictors)

    # Fix MixMHCpred symlink issue: /usr/local/bin/MixMHCpred is a symlink to
    # /opt/MixMHCpred/MixMHCpred, but the script uses BASH_SOURCE[0] to locate
    # its code/ directory.  When invoked via the symlink it looks for
    # /usr/local/bin/code/main.py (missing).  Replace the symlink with a
    # wrapper that execs the real path.
    if "MixMHCpred" in predictors:
        import stat
        mix_path = "/usr/local/bin/MixMHCpred"
        if os.path.islink(mix_path):
            os.unlink(mix_path)
            with open(mix_path, "w") as f:
                f.write('#!/bin/bash\nexec /opt/MixMHCpred/MixMHCpred "$@"\n')
            os.chmod(mix_path, 0o755)
            print("[prediction] Fixed MixMHCpred symlink → wrapper script", flush=True)

    out = Path(output_dir)
    # Ensure a clean run: pvacseq aborts if a previous run's restart metadata
    # exists in the output directory. Since the output directory is a Docker
    # volume mount, we cannot remove the mount point itself. Instead, delete all
    # its contents while preserving the directory.
    if out.exists():
        import shutil
        for child in out.iterdir():
            try:
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            except Exception:
                # Ignore errors (e.g., busy files) – pvacseq will overwrite as needed.
                pass
    out.mkdir(parents=True, exist_ok=True)

    cmd = [
        "pvacseq", "run",
        str(vcf_path),
        vcf_sample,          # use VCF column name, not display name
        alleles_str,
        algorithms_str,
        str(out),
        "-e1", epitope_lengths,
        "-m", "median",
        "-b", "500",
        "-c", "1",
    ]

    print(f"[prediction] Running: {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        stderr_tail = (result.stderr or "")[-2000:]
        raise RuntimeError(
            f"pVACseq exited {result.returncode}.\nSTDERR:\n{stderr_tail}"
        )

    # Output file uses the vcf_sample name as prefix
    tsv = out / "MHC_Class_I" / f"{vcf_sample}.MHC_I.all_epitopes.tsv"
    if not tsv.exists():
        raise FileNotFoundError(f"Expected pVACseq output not found: {tsv}")

    return str(tsv)
