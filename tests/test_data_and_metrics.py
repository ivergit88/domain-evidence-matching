import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from data import normalize, decode_list, load_candidates
from experiment import ndcg


class DataAndMetricsTests(unittest.TestCase):
    def test_normalization(self):
        self.assertEqual(normalize(' ПЛАТЁЖНЫЙ\u2011ШЛЮЗ '), 'платежный-шлюз')

    def test_decode_known_export_problem(self):
        raw = '"{' + json.dumps(['финтех', 'биллинг'], ensure_ascii=False)[1:-1].replace('"', '\\"') + ']}'
        values, repaired = decode_list(raw)
        self.assertEqual(values, ['финтех', 'биллинг'])
        self.assertTrue(repaired)
        with self.assertRaises(ValueError):
            decode_list('сломанный текст')

    def test_extra_sql_is_rejected(self):
        header = 'INSERT INTO "avtopodbor"."resumes_domains" ("id", "business_domains") VALUES '
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'data.sql'
            path.write_text(header + "('1', '[\"финтех\"]'); SELECT 1;", encoding='utf-8')
            with self.assertRaises(ValueError):
                load_candidates(path)

    def test_metric_has_known_perfect_and_reversed_results(self):
        labels = {1: 2, 2: 1, 3: 0}
        self.assertEqual(ndcg([1, 2, 3], labels), 1)
        self.assertLess(ndcg([3, 2, 1], labels), 1)
        with self.assertRaises(ValueError):
            ndcg([1, 1, 2], labels)

    def test_fixture_only_uses_real_ids(self):
        rows, _ = load_candidates(ROOT/'data/domains.sql')
        by_id = {r['id']: r['domains'] for r in rows}
        fixture = json.loads((ROOT/'checks.json').read_text(encoding='utf-8'))
        for case in fixture['cases']:
            for judgment in case['judgments']:
                self.assertIn(judgment['candidate_id'], by_id)
                self.assertIn(judgment['grade'], (0, 1, 2))


if __name__ == '__main__':
    unittest.main()
