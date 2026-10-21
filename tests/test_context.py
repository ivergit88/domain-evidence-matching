import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from matcher import check_phrase, rank_candidates, load_cards


class ContextRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cards = load_cards(ROOT / 'cards.json')
        cls.core = cls.cards['bank_core_integration']

    def test_shared_negation_in_russian_and_english_list_is_not_confirmed(self):
        phrases = [
            'Не работал с CRM и интеграцией банковского ядра',
            'Did not work with CRM and bank core integration',
        ]
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(check_phrase(phrase, self.core)['status'],
                              ('review', 'contradicted'))

    def test_negated_list_cannot_satisfy_required_experience(self):
        row = {'id': 1, 'domains': ['Не работал с CRM и интеграцией банковского ядра']}
        request = [{'card': 'bank_core_integration', 'required': True}]
        result = rank_candidates([row], request, self.cards)[0]
        self.assertFalse(result['eligible'])
        self.assertNotEqual(result['checks'][0]['status'], 'confirmed')

    def test_bankruptcy_context_never_confirms_finance_or_bank_core_cards(self):
        phrases = [
            'Интеграция ядра системы банкротства',
            'integration of bankruptcy system core',
        ]
        for card_id in ('fintech', 'banking', 'bank_core_integration'):
            for phrase in phrases:
                with self.subTest(card=card_id, phrase=phrase):
                    self.assertNotEqual(
                        check_phrase(phrase, self.cards[card_id])['status'],
                        'confirmed',
                    )

    def test_real_bank_context_and_integrations_still_confirm(self):
        phrases = [
            'банк: интеграция ядра',
            'интеграция ядра банка',
            'интеграция банковского ядра',
            'bank core integration',
            'integration of the banking core',
        ]
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertEqual(check_phrase(phrase, self.core)['status'], 'confirmed')

    def test_crm_and_positive_bank_core_action_can_share_a_list(self):
        phrase = 'Работал с CRM и интегрировал банковское ядро'
        self.assertEqual(check_phrase(phrase, self.core)['status'], 'confirmed')

    def test_bank_core_action_is_not_stitched_to_bank_context_from_other_clause(self):
        phrase = 'В банке сопровождал ядро и интегрировал CRM'
        self.assertNotEqual(check_phrase(phrase, self.core)['status'], 'confirmed')

    def test_independent_positive_after_negated_sentence_still_confirms(self):
        phrase = 'Не работал с CRM. Интегрировал банковское ядро.'
        self.assertEqual(check_phrase(phrase, self.core)['status'], 'confirmed')

    def test_not_only_constructions_are_not_treated_as_negation(self):
        phrases = [
            'Не только интеграция банковского ядра, но и CRM',
            'Not only bank core integration, but also CRM',
        ]
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertEqual(check_phrase(phrase, self.core)['status'], 'confirmed')


if __name__ == '__main__':
    unittest.main()
