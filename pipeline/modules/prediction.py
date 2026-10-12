"""
Wraps pvacseq run as a Python function.
Returns the path to the MHC_Class_I all_epitopes.tsv output file.
"""
import subprocess
import os
from pathlib import Path


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
