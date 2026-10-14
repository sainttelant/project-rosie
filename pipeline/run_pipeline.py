#!/usr/bin/env python3
"""
Project Rosie — Pipeline CLI entry point.

Usage (Day 1, sample data with MHCflurry):
  python run_pipeline.py \\
    --vcf data/sample/pvacseq_example_data/annotated.expression.vcf.gz \\
    --sample-name HCC1395_TUMOR_DNA \\
    --alleles HLA-A*29:02,HLA-A*11:01,HLA-B*44:03,HLA-B*56:01,HLA-C*16:01 \\
    --predictors MHCflurry \\
    --output-dir output/

Usage (Day 2, canine data with MHCflurry):
  python run_pipeline.py \\
    --vcf data/canine/tumor_annotated.vcf \\
    --sample-name canine_mammary_001 \\
    --alleles DLA-8803401,DLA-8850101 \\
    --predictors MHCflurry \\
    --species canis_lupus_familiaris \\
    --output-dir output/
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from modules.prediction import run_pvacseq, run_pvacseq_mhcii, validate_mhcii, attach_mhcii_results
from modules.scoring import score_candidates
from modules.visualizations import generate_all
from modules.gemma import generate_clinical_report
from modules.mrna_design import design_mrna, PADRE
from modules.structure import annotate_candidates
# New module for model-based review
from modules.review import generate_review


def parse_args():
    p = argparse.ArgumentParser(description="Project Rosie — neoantigen pipeline")
    p.add_argument("--vcf",         required=True,  help="Path to VEP-annotated VCF")
    p.add_argument("--sample-name", required=True,  help="Tumor sample name (must match VCF column header)")
    p.add_argument("--alleles",     required=True,  help="Comma-separated HLA/DLA alleles")
    p.add_argument("--predictors",  required=True,  help="Space or comma-separated predictors (e.g. MHCflurry or NetMHCpan)")
    p.add_argument("--output-dir",  default="output", help="Output directory")
    p.add_argument("--species",     default="homo_sapiens", help="Species (default: homo_sapiens)")
    p.add_argument("--epitope-lengths", default="8,9,10,11")
    p.add_argument("--skip-prediction", action="store_true",
                   help="Skip pvacseq run and use existing TSV (provide --tsv)")
    p.add_argument("--tsv", help="Existing pVACseq all_epitopes.tsv (use with --skip-prediction)")
    p.add_argument("--mhc-ii", action="store_true", help="Run optional MHC-II prediction")
    p.add_argument("--mhc-ii-alleles", help="Explicit comma-separated MHC-II alleles; never inferred from MHC-I")
    p.add_argument("--mhc-ii-predictors", default="NetMHCIIpan", help="Space or comma-separated MHC-II predictors")
    p.add_argument("--mhc-ii-epitope-lengths", default="15", help="Comma-separated MHC-II peptide lengths (11-30)")
    p.add_argument("--mhc-ii-tsv", help="Reuse an existing MHC-II TSV instead of running prediction (requires --mhc-ii)")
    p.add_argument("--cd4-helper", nargs="?", const=PADRE, default=None,
                   help="Append experimental CD4 helper; defaults to PADRE when supplied without a sequence")
    # Phase 2: AlphaFold2 structural validation (local Docker + GPU, off by default)
    p.add_argument("--structure", action="store_true",
                   help="Run AlphaFold2 structural validation (pLDDT + surface exposure filter)")
    p.add_argument("--structure-gpu", default="0",
                   help="GPU device index for AlphaFold2 (default: 0)")
    p.add_argument("--structure-data-dir", default="/data_fast/aplha_data",
                   help="AF2 database directory (default: /data_fast/aplha_data)")
    p.add_argument("--protein-fasta", default=None,
                   help="Wild-type protein FASTA (default: auto-locate pVACseq 'protein_fasta')")
    p.add_argument("--skip-gemma", action="store_true",
                   help="Skip Gemma 4 clinical report (no GCP credentials needed)")
    # New flag to run a local LLM review (e.g., deepseek-r1:70b). The model name is passed to the review module.
    p.add_argument("--review-model", default="", help="Local LLM model name for pipeline review (e.g., deepseek-r1:70b). If empty, no review is performed.")
    # New flag: generate bilingual report (English + Chinese)
    p.add_argument("--bilingual", action="store_true",
                   help="Generate clinical report in both English and Chinese")
    args = p.parse_args()
    if args.skip_prediction and not args.tsv:
        p.error("--skip-prediction requires --tsv")
    if args.mhc_ii_tsv and not args.mhc_ii:
        p.error("--mhc-ii-tsv requires --mhc-ii")
    if args.mhc_ii:
        try:
            validate_mhcii([allele.strip() for allele in (args.mhc_ii_alleles or "").split(",")],
                           args.mhc_ii_predictors.replace(",", " ").split(), args.mhc_ii_epitope_lengths)
        except ValueError as error:
            p.error(str(error))
    return args


def main():
    args = parse_args()

    alleles    = [a.strip() for a in args.alleles.split(",")]
    predictors = [p.strip() for p in args.predictors.replace(",", " ").split()]
    out_dir    = str(Path(args.output_dir).resolve())

    print(f"\n{'='*60}")
    print(f"  Project Rosie — Neoantigen Pipeline")
    print(f"  Sample : {args.sample_name}")
    print(f"  Species: {args.species}")
    print(f"  Alleles: {', '.join(alleles)}")
    print(f"  Predictors: {', '.join(predictors)}")
    print(f"{'='*60}\n")

    # Step 1: pVACseq prediction
    if args.skip_prediction:
        if not args.tsv:
            print("ERROR: --skip-prediction requires --tsv", file=sys.stderr)
            sys.exit(1)
        tsv_path = args.tsv
        print(f"[pipeline] Skipping prediction, using existing TSV: {tsv_path}")
    else:
        print("[pipeline] Step 1/3: Running pVACseq prediction...")
        tsv_path = run_pvacseq(
            vcf_path=args.vcf,
            sample_name=args.sample_name,
            alleles=alleles,
            predictors=predictors,
            output_dir=out_dir,
            epitope_lengths=args.epitope_lengths,
        )

    mhcii_tsv = None
    mhcii_alleles = [allele.strip() for allele in (args.mhc_ii_alleles or "").split(",")]
    mhcii_predictors = args.mhc_ii_predictors.replace(",", " ").split()
    if args.mhc_ii:
        print("\n[pipeline] Step 1b: MHC-II prediction...")
        mhcii_tsv = args.mhc_ii_tsv or run_pvacseq_mhcii(
            vcf_path=args.vcf, sample_name=args.sample_name, alleles=mhcii_alleles,
            predictors=mhcii_predictors, output_dir=out_dir,
            epitope_lengths=args.mhc_ii_epitope_lengths,
        )

    # Step 2: Score and rank candidates
    print("\n[pipeline] Step 2/3: Scoring and ranking candidates...")
    json_path = score_candidates(
        tsv_path=tsv_path,
        sample_name=args.sample_name,
        alleles=alleles,
        species=args.species,
        output_dir=out_dir,
    )

    mhcii_summary = ""
    if mhcii_tsv:
        mhcii_summary = attach_mhcii_results(
            json_path, mhcii_tsv, mhcii_alleles, mhcii_predictors,
            args.mhc_ii_epitope_lengths, reused=bool(args.mhc_ii_tsv),
        )

    # Step 2b (Phase 2, opt-in): AlphaFold2 structural validation
    if args.structure:
        print("\n[pipeline] Step 2b: AlphaFold2 structural validation (pLDDT + surface exposure)...")
        json_path = annotate_candidates(
            candidates_json_path=json_path,
            output_dir=out_dir,
            protein_fasta_path=args.protein_fasta,
            data_dir=args.structure_data_dir,
            gpu_device=args.structure_gpu,
        )

    # Step 3: Generate visualizations
    print("\n[pipeline] Step 3/4: Generating visualizations...")
    png_paths = generate_all(candidates_json_path=json_path, tsv_path=tsv_path)

    # Step 4: Gemma 4 clinical report
    report_path = str(Path(out_dir) / f"{args.sample_name}_clinical_report.md")
    if args.skip_gemma:
        print("\n[pipeline] Step 4/4: Skipping Gemma 4 report (--skip-gemma)")
        report = ""
    else:
        print("\n[pipeline] Step 4/4: Generating clinical report with Gemma 4...")
        report = generate_clinical_report(
            candidates_json_path=json_path,
            binding_affinity_png=png_paths["binding_affinity"],
            mutation_landscape_png=png_paths["mutation_landscape"],
            bilingual=args.bilingual,
        )
        Path(report_path).write_text(report)
        print(f"[gemma] Clinical report → {report_path}")

    if mhcii_summary:
        report = report + "\n\n" + mhcii_summary
        Path(report_path).write_text(report)
        print(f"[pipeline] MHC-II evidence appended to {report_path}")

    # Step 4b: Optional LLM review of the generated report
    if args.review_model:
        print("\n[pipeline] Step 4b: Running LLM review using model {0}...".format(args.review_model))
        review_text = generate_review(report, model_name=args.review_model)
        # Append review to the report file if it exists
        if report_path and Path(report_path).exists():
            with open(report_path, "a", encoding="utf-8") as f:
                f.write("\n---\n\n# LLM Review ({0})\n\n".format(args.review_model))
                f.write(review_text)
            print(f"[review] Review appended to {report_path}")
        else:
            # If no report file, just output review
            print("[review] Generated review (no report file to append):")
            print(review_text)

    # Step 5: mRNA design
    print("\n[pipeline] Step 5/5: Designing mRNA vaccine construct...")
    mrna_result = design_mrna(
        candidates_json_path=json_path,
        output_dir=out_dir,
        species=args.species,
        cd4_helper=args.cd4_helper,
    )
    fasta_path = mrna_result["fasta_path"] if isinstance(mrna_result, dict) else str(mrna_result)

    print(f"\n{'='*60}")
    print(f"  DONE")
    print(f"  Candidates JSON  : {json_path}")
    print(f"  Clinical Report  : {report_path}")
    print(f"  mRNA FASTA       : {fasta_path}")
    print(f"{'='*60}\n")
    return json_path


if __name__ == "__main__":
    main()
