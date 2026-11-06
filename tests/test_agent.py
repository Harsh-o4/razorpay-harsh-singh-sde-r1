import unittest
from ticket_agent import Store, SupportAgent


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.agent = SupportAgent(self.store)
        self.question = 'How can I request a refund?'
        self.store.add_faq(self.question, 'Open the transaction and select Request refund.', 'refund')

    def train(self):
        for _ in range(12):
            result = self.agent.handle({'text': self.question})
            if result['decision']['action'] == 'escalate':
                self.store.approve(result['ticket_id'])
            self.store.feedback(result['ticket_id'], 5)

    def test_cold_start_then_automation(self):
        initial = self.agent.handle({'text': self.question})
        self.assertEqual(initial['decision']['action'], 'escalate')
        self.assertIsNone(initial['response'])
        self.train()
        result = self.agent.handle({'text': self.question})
        self.assertEqual(result['decision']['action'], 'automated_response')
        self.assertIn('Request refund', result['response'])
        for stage in ('categorisation', 'sentiment', 'severity', 'complexity', 'routing', 'resolution_estimate', 'decision', 'faq_match'):
            self.assertTrue(0 <= result[stage]['confidence'] <= 1)

    def test_risk_gates(self):
        self.train()
        for ticket in ({'text': self.question, 'amount': 100000},
                       {'text': self.question + ' I am furious'},
                       {'text': 'Unauthorized payment fraud'},
                       {'text': self.question + ' INR 50000'},
                       {'text': 'Something is wrong'},
                       {'text': 'Refund and settlement problem'}):
            with self.subTest(ticket=ticket):
                result = self.agent.handle(ticket)
                self.assertEqual(result['decision']['action'], 'escalate')
                self.assertIsNone(result['response'])
        fraud = self.agent.handle({'text': 'Unauthorized payment fraud'})
        self.assertEqual(fraud['routing']['value'], 'Risk and Disputes')
        self.assertEqual(fraud['severity']['value'], 'critical')

    def test_feedback_integrity(self):
        result = self.agent.handle({'text': self.question})
        with self.assertRaises(ValueError):
            self.store.feedback(result['ticket_id'], 5)
        self.store.approve(result['ticket_id'])
        self.store.feedback(result['ticket_id'], 5)
        self.store.feedback(result['ticket_id'], 1)
        self.assertEqual(self.store.faqs()[0]['feedback_count'], 1)
        self.assertEqual(self.store.faqs()[0]['satisfaction'], 0)

    def test_validation(self):
        for ticket in ({}, {'text': ' '}, {'text': 'refund', 'amount': 'NaN'},
                       {'text': 'refund', 'amount': -1}, {'text': 'refund', 'currency': 'USD'}):
            with self.assertRaises(ValueError):
                self.agent.handle(ticket)

    def test_in_memory_isolation_and_copying(self):
        other = Store()
        self.assertEqual(other.faqs(), [])
        faqs = self.store.faqs()
        faqs[0]['answer'] = 'modified'
        self.assertNotEqual(self.store.faqs()[0]['answer'], 'modified')

    def test_two_outcomes_and_departments(self):
        self.train()
        automatic = self.agent.handle({'text': self.question})
        self.assertEqual(automatic['decision']['action'], 'automated_response')
        self.assertIsNone(automatic['department'])
        for text, department in [('API webhook signature error', 'Developer Support'),
                                 ('Settlement missing', 'Settlement Specialists'),
                                 ('Account locked', 'Account Support'),
                                 ('Unauthorized payment', 'Risk and Disputes'),
                                 ('Unknown issue', 'Support Triage')]:
            result = self.agent.handle({'text': text})
            self.assertEqual(result['decision']['action'], 'escalate')
            self.assertEqual(result['department'], department)

    def test_existing_faq_ratings(self):
        self.store.add_faq('How can I reset my password?', 'Use Forgot password.',
                           'account', ratings=[5] * 12)
        result = self.agent.handle({'text': 'How can I reset my password?'})
        self.assertEqual(result['decision']['action'], 'automated_response')
        with self.assertRaises(ValueError):
            self.store.add_faq('Question', 'Answer', 'account', ratings=[6])


if __name__ == '__main__':
    unittest.main()
