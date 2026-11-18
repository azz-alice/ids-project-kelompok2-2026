from __future__ import annotations

import sys
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(PACKAGE))

from ids_pretrained.schema import FEATURE_NAMES, FeatureValidationError, normalize_feature_row


class FeatureSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.row = {name: 1.0 for name in FEATURE_NAMES}

    def test_canonical_order_is_fixed(self) -> None:
        reversed_row = dict(reversed(list(self.row.items())))
        ordered = normalize_feature_row(reversed_row)
        self.assertEqual(len(ordered), 20)
        self.assertEqual(ordered, [1.0] * 20)

    def test_snake_case_aliases_are_accepted(self) -> None:
        aliases = {
            "bwd_pkt_len_std": 1,
            "bwd_pkt_len_mean": 2,
            "pkt_len_std": 3,
            "pkt_len_var": 4,
            "bwd_pkt_len_max": 5,
            "subflow_bwd_byts": 6,
            "bwd_seg_size_avg": 7,
            "pkt_len_mean": 8,
            "pkt_size_avg": 9,
            "pkt_len_max": 10,
            "totlen_bwd_pkts": 11,
            "fwd_iat_std": 12,
            "tot_fwd_pkts": 13,
            "tot_bwd_pkts": 14,
            "bwd_pkts_s": 15,
            "idle_min": 16,
            "fwd_iat_mean": 17,
            "subflow_fwd_pkts": 18,
            "totlen_fwd_pkts": 19,
            "fwd_iat_max": 20,
        }
        ordered = normalize_feature_row(aliases)
        self.assertEqual(ordered, [float(value) for value in range(1, 21)])

    def test_missing_feature_is_rejected(self) -> None:
        row = dict(self.row)
        row.pop(FEATURE_NAMES[0])
        with self.assertRaises(FeatureValidationError):
            normalize_feature_row(row)

    def test_non_finite_value_is_rejected(self) -> None:
        row = dict(self.row)
        row[FEATURE_NAMES[0]] = float("nan")
        with self.assertRaises(FeatureValidationError):
            normalize_feature_row(row)

    def test_negative_value_is_rejected(self) -> None:
        row = dict(self.row)
        row[FEATURE_NAMES[0]] = -1
        with self.assertRaises(FeatureValidationError):
            normalize_feature_row(row)


if __name__ == "__main__":
    unittest.main()
