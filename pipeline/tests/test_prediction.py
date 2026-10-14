import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.modules.prediction import attach_mhcii_results, run_pvacseq_mhcii, validate_mhcii


class MhcIITests(unittest.TestCase):
    def test_configuration_rejects_class_i_and_bad_lengths(self):
        for alleles, predictors, lengths in [([], ["NetMHCIIpan"], "15"),
                                             (["DLA-8850101"], ["NetMHCIIpan"], "15"),
                                             (["HLA-A*02:01"], ["NetMHCIIpan"], "15"),
                                             (["DRB1*01:01"], ["MHCflurry"], "15"),
                                             (["DRB1*01:01"], ["NetMHCIIpan"], "9")]:
            with self.assertRaises(ValueError):
                validate_mhcii(alleles, predictors, lengths)

    @patch("pipeline.modules.prediction.shutil.which", return_value="/bin/pvacseq")
    def test_class_ii_command_preserves_class_i(self, which):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vcf = root / "input.vcf"
            vcf.write_text("#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tTUMOR\n")
            marker = root / "MHC_Class_I" / "keep.tsv"
            marker.parent.mkdir()
            marker.write_text("keep")
            output = root / "mhc_ii" / "MHC_Class_II" / "TUMOR.MHC_II.all_epitopes.tsv"
            output.parent.mkdir(parents=True)
            output.write_text("result")
            supported = subprocess.CompletedProcess([], 0, "DRB1*01:01\n", "")
            complete = subprocess.CompletedProcess([], 0, "", "")
            with patch("pipeline.modules.prediction.subprocess.run", side_effect=[supported, supported, complete]) as run:
                path = run_pvacseq_mhcii(str(vcf), "display", ["DRB1*01:01"],
                                        ["NetMHCIIpan", "NNalign"], directory)
                command = run.call_args.args[0]
                self.assertEqual(run.call_args_list[0].args[0], ["pvactools", "valid_alleles", "-p", "NetMHCIIpan"])
                self.assertEqual(command[5:7], ["NetMHCIIpan", "NNalign"])
                self.assertEqual(command[command.index("-e2") + 1], "15")
                self.assertEqual(path, str(output))
                self.assertEqual(marker.read_text(), "keep")

    @patch("pipeline.modules.prediction.shutil.which", return_value="/bin/pvacseq")
    def test_unsupported_allele_is_not_substituted(self, which):
        supported = subprocess.CompletedProcess([], 0, "DRB1*01:01\n", "")
        with patch("pipeline.modules.prediction.subprocess.run", return_value=supported) as run:
            with self.assertRaisesRegex(ValueError, "no HLA/DLA substitution"):
                run_pvacseq_mhcii("missing.vcf", "test", ["DLA-DRB1*001:01"], ["NetMHCIIpan"], "unused")
            self.assertEqual(run.call_count, 1)

    @patch("pipeline.modules.prediction.shutil.which", return_value=None)
    def test_missing_tool_fails_clearly(self, which):
        with self.assertRaisesRegex(RuntimeError, "pvacseq is not installed"):
            run_pvacseq_mhcii("missing.vcf", "test", ["DRB1*01:01"], ["NetMHCIIpan"], "unused")

    def test_json_and_report_keep_class_ii_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "candidates.json"
            original = [{"peptide": "MPMCEFDMVK", "gene": "PIK3CA"}]
            source.write_text(json.dumps({"top_candidates": original, "visualization_paths": {"binding_affinity": "plot.png"}}))
            tsv = root / "mhcii.tsv"
            tsv.write_text("MT Epitope Seq\tHLA Allele\tGene Name\tMedian MT IC50 Score\n"
                           "AKFVAAWTLKAAAGG\tDRB1*01:01\tTEST\tNA\n")
            summary = attach_mhcii_results(str(source), str(tsv), ["DRB1*01:01"], ["NetMHCIIpan"], "15", reused=True)
            data = json.loads(source.read_text())
            self.assertEqual(data["top_candidates"], original)
            self.assertEqual(data["mhc_ii"]["total_epitopes"], 1)
            self.assertEqual(data["mhc_ii"]["status"], "reused")
            self.assertEqual(data["visualization_paths"]["binding_affinity"], "plot.png")
            self.assertIn("not automatically encoded", summary)
            with self.assertRaises(ValueError):
                attach_mhcii_results(str(source), str(tsv), ["DRB1*02:01"], ["NetMHCIIpan"], "15")

    def test_cli_reuses_class_ii_and_writes_report_without_gemma(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            class_i = root / "class_i.tsv"
            class_i.write_text("MT Epitope Seq\tHLA Allele\tGene Name\tMedian MT IC50 Score\tTumor DNA VAF\tMutation\n"
                               "MPMCEFDMV\tHLA-A*02:01\tTEST\t100\t0.3\tSNV\n")
            class_ii = root / "class_ii.tsv"
            class_ii.write_text("MT Epitope Seq\tHLA Allele\tGene Name\tMedian MT IC50 Score\n"
                                "AKFVAAWTLKAAAGG\tDRB1*01:01\tTEST\tNA\n")
            script = Path(__file__).resolve().parents[1] / "run_pipeline.py"
            result = subprocess.run([
                sys.executable, str(script), "--vcf", "not-used.vcf", "--sample-name", "test",
                "--alleles", "HLA-A*02:01", "--predictors", "MHCflurry",
                "--skip-prediction", "--tsv", str(class_i), "--skip-gemma",
                "--output-dir", str(root / "out"), "--mhc-ii", "--mhc-ii-tsv", str(class_ii),
                "--mhc-ii-alleles", "DRB1*01:01", "--cd4-helper",
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads((root / "out/test_candidates.json").read_text())
            self.assertEqual(data["mhc_ii"]["status"], "reused")
            self.assertEqual(len(data["top_candidates"]), 1)
            self.assertIn("MHC-II Prediction", (root / "out/test_clinical_report.md").read_text())
            summary = (root / "out/test_mrna_design_summary.md").read_text()
            self.assertIn("CD4 helper (experimental)", summary)
            self.assertIn("AKFVAAWTLKAAA", summary)


if __name__ == "__main__":
    unittest.main()