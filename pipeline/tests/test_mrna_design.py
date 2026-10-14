import json
import tempfile
import unittest
from pathlib import Path

from pipeline.modules import mrna_design as mrna


class MrnaDesignTests(unittest.TestCase):
    def translate(self, dna):
        codon_to_aa = {codon: aa for aa, choices in mrna.CANINE_CODON_TABLE.items()
                       for codon, frequency in choices}
        return "".join(codon_to_aa[dna[index:index + 3]] for index in range(0, len(dna), 3))

    def test_gc_adjustment_preserves_translation(self):
        protein = "MKQLGVVNAAYAGGFAAYKLVVVGAGGV*"
        dna = mrna.back_translate(protein)
        self.assertEqual(self.translate(dna), protein)
        self.assertTrue(0.40 <= mrna.gc_content(dna) <= 0.60)
        self.assertEqual(dna, mrna.back_translate(protein))

    def test_met_is_not_duplicated(self):
        for peptides, expected in [(["MKQLGVVNA", "AGGF"], "MKQLGVVNAAAYAGGF*"),
                                   (["KQLGVVNA"], "MKQLGVVNA*"), (["MMK"], "MMK*")]:
            cds = mrna.build_construct(peptides)[len(mrna.KOZAK):]
            self.assertTrue(cds.startswith("ATG"))
            self.assertEqual(self.translate(cds), expected)

    def test_sequence_constrained_gc_and_invalid_input(self):
        self.assertEqual(mrna.back_translate("WWWW"), "TGG" * 4)
        for peptides in [[], [""], ["AX"], ["A*"]]:
            with self.assertRaises(ValueError):
                mrna.build_construct(peptides)
        with self.assertRaises(ValueError):
            mrna.back_translate("A", target_lower=0.8, target_upper=0.2)

    def test_regions_and_optional_helper(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "candidates.json"
            source.write_text(json.dumps({"case_id": "test", "top_candidates": [
                {"peptide": "MKQLGVVNA", "gene": "TEST"}]}))
            for helper in [None, mrna.PADRE]:
                result = mrna.design_mrna(str(source), directory, cd4_helper=helper)
                design = result["design_data"]
                self.assertEqual(len(mrna.HBB_3UTR), 134)
                self.assertEqual(design["polya_len"], 100)
                self.assertEqual(design["mrna_seq"][design["cds_start"]:design["cds_end"]], design["cds_seq"])
                self.assertEqual(design["mrna_seq"][design["cds_end"]:-100], mrna.HBB_3UTR)
                self.assertTrue(design["mrna_seq"].endswith("A" * 100))
                self.assertEqual(design["n_epitopes"], 1 if helper is None else 2)
                self.assertEqual(design["cd4_helper"], helper)
                summary = Path(result["summary_path"]).read_text()
                self.assertIn("poly-A (100 nt)", summary)
                self.assertIn("0-based, half-open", summary)

    def test_synthesis_spec_matches_design_and_handles_percentile_only(self):
        from pipeline.modules.synthesis_spec import generate_synthesis_spec

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "candidates.json"
            source.write_text(json.dumps({"case_id": "test", "top_candidates": [
                {"peptide": "MKQLGVVNA", "gene": "TEST", "ic50_nm": None}]}))
            result = mrna.design_mrna(str(source), directory, cd4_helper=mrna.PADRE)
            design = result["design_data"]
            spec = generate_synthesis_spec(design, str(source))
            self.assertIn("within 40–60% target", spec)
            self.assertIn("Kozak (6 nt)", spec)
            self.assertIn(f"CDS ({design['cds_len']} nt, includes initiation ATG and stop", spec)
            self.assertIn("poly-A (100 nt)", spec)
            self.assertIn("CD4 helper (experimental)", spec)
            self.assertIn("Not available (no IC50)", spec)


if __name__ == "__main__":
    unittest.main()