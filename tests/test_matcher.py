import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from matcher import check_phrase, check_candidate, rank_candidates, load_cards
from data import load_candidates


class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cards = load_cards(ROOT / 'cards.json')
        cls.core = cls.cards['bank_core_integration']

    def test_action_object_and_context_must_occur_together(self):
        result = check_phrase('интеграция банковского ядра', self.core)
        self.assertEqual(result['status'], 'confirmed')
        self.assertEqual(result['missing'], [])

    def test_broad_banking_is_not_core_integration(self):
        for text in ['банковский сектор', 'банковские интеграции', 'интеграция банковских систем']:
            with self.subTest(text=text):
                self.assertEqual(check_phrase(text, self.core)['status'], 'review')

    def test_no_fact_stitching_between_projects(self):
        units = [{'text': 'интеграция CRM', 'project_id': 'A'},
                 {'text': 'ядро банковской системы', 'project_id': 'B'}]
        self.assertNotEqual(check_candidate(units, self.core)['status'], 'confirmed')

    def test_negated_experience_is_not_positive(self):
        result = check_phrase('Интеграцией банковского ядра не занимался', self.core)
        self.assertEqual(result['status'], 'contradicted')

    def test_conflicting_claims_require_review(self):
        result = check_candidate(['интеграция банковского ядра',
                                  'нет опыта интеграции банковского ядра'], self.core)
        self.assertEqual(result['status'], 'review')

    def test_abs_requires_banking_context(self):
        self.assertNotEqual(check_phrase('интеграция ABS автомобиля', self.core)['status'], 'confirmed')
        self.assertEqual(check_phrase('интеграция АБС банка', self.core)['status'], 'confirmed')

    def test_system_mention_does_not_invent_integration(self):
        self.assertEqual(check_phrase('тестирование АБС банка', self.core)['status'], 'review')

    def test_not_only_is_not_negation(self):
        self.assertEqual(check_phrase('Не только интеграция банковского ядра, но и CRM', self.core)['status'], 'confirmed')

    def test_unrelated_negation_does_not_cancel_positive_fact(self):
        result = check_phrase('Есть опыт интеграции банковского ядра, проблем нет', self.core)
        self.assertEqual(result['status'], 'confirmed')

    def test_action_cannot_be_borrowed_from_another_clause(self):
        text = 'В банке сопровождал ядро, интеграцию делал с CRM'
        self.assertEqual(check_phrase(text, self.core)['status'], 'review')

    def test_unknown_negation_needs_review(self):
        text = 'Никогда не выполнял интеграцию банковского ядра'
        self.assertNotEqual(check_phrase(text, self.core)['status'], 'confirmed')

    def test_unknown_is_not_forced_into_a_known_domain(self):
        self.assertEqual(check_phrase('онлайн обучение музыке', self.core)['status'], 'unknown')

    def test_high_similarity_cannot_confirm_missing_facts(self):
        rows = [{'id': 79, 'domains': ['интеграция банковского ядра']},
                {'id': 6, 'domains': ['банковские интеграции']}]
        request = [{'card': 'bank_core_integration', 'required': True}]
        ranked = rank_candidates(rows, request, self.cards, {79: .1, 6: .99})
        self.assertEqual([r['id'] for r in ranked], [79, 6])
        self.assertTrue(ranked[0]['eligible'])
        self.assertFalse(ranked[1]['eligible'])

    def test_optional_requirement_does_not_exclude_candidate(self):
        request = [{'card': 'fintech', 'required': True},
                   {'card': 'bank_core_integration', 'required': False}]
        result = rank_candidates([{'id': 6, 'domains': ['финтех']}], request, self.cards)[0]
        self.assertTrue(result['eligible'])
        self.assertEqual(result['desired_confirmed'], 0)

    def test_duplicates_do_not_increase_confirmations(self):
        request = [{'card': 'fintech', 'required': True}]
        a = rank_candidates([{'id': 1, 'domains': ['финтех']}], request, self.cards)[0]
        b = rank_candidates([{'id': 1, 'domains': ['финтех'] * 3}], request, self.cards)[0]
        self.assertEqual(a['required_confirmed'], b['required_confirmed'])

    def test_original_sql_example(self):
        rows, audit = load_candidates(ROOT / 'data/domains.sql')
        self.assertEqual(len(rows), 117)
        self.assertEqual(audit['repaired_rows'], 117)
        request = [{'card': 'fintech', 'required': True},
                   {'card': 'bank_core_integration', 'required': False}]
        ranked = rank_candidates(rows, request, self.cards)
        self.assertEqual(ranked[0]['id'], 79)
        by_id = {r['id']: r for r in ranked}
        self.assertEqual(by_id[6]['checks'][1]['status'], 'review')

    def test_request_validation(self):
        for request in [[], [{'card': 'missing'}], [{'card': 'fintech', 'required': 'false'}],
                        [{'card': 'fintech'}]]:
            with self.assertRaises(ValueError):
                rank_candidates([], request, self.cards)


if __name__ == '__main__':
    unittest.main()
