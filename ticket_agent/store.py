"""In-memory MVP storage. All data is discarded when the program exits."""
from copy import deepcopy


class Store:
    def __init__(self):
        self._faqs = {}
        self._decisions = {}
        self._feedback = {}

    def add_faq(self, question, answer, category, ratings=None):
        """Optionally supply existing customer ratings (1–5) for this FAQ."""
        from .engine import CATEGORIES
        if not all(isinstance(x, str) and x.strip() for x in (question, answer, category)):
            raise ValueError('question, answer and category must be non-empty strings')
        if category not in CATEGORIES:
            raise ValueError('Unknown category')
        ratings = list(ratings) if ratings is not None else []
        for rating in ratings:
            self._validate_rating(rating)
        faq_id = len(self._faqs) + 1
        self._faqs[faq_id] = {'id': faq_id, 'question': question.strip(),
                              'answer': answer.strip(), 'category': category, 'ratings': ratings}
        return faq_id

    @staticmethod
    def _validate_rating(rating):
        if type(rating) is not int or not 1 <= rating <= 5:
            raise ValueError('rating must be an integer from 1 to 5')

    def faqs(self):
        results = []
        for faq in self._faqs.values():
            ratings = faq['ratings'] + [rating for faq_id, rating in self._feedback.values()
                                        if faq_id == faq['id']]
            results.append({key: deepcopy(value) for key, value in faq.items() if key != 'ratings'} |
                           {'feedback_count': len(ratings),
                            'satisfaction': sum(r >= 4 for r in ratings) / len(ratings) if ratings else None})
        return results

    def save(self, ticket, result):
        ticket_id = len(self._decisions) + 1
        self._decisions[ticket_id] = {'ticket': deepcopy(ticket), 'result': deepcopy(result)}
        return ticket_id

    def _result(self, ticket_id):
        if type(ticket_id) is not int or ticket_id not in self._decisions:
            raise ValueError('Unknown ticket ID')
        return self._decisions[ticket_id]['result']

    def feedback(self, decision_id, rating):
        self._validate_rating(rating)
        result = self._result(decision_id)
        faq_id = result['faq_match']['faq_id']
        if faq_id is None or not (result['decision']['action'] == 'automated_response'
                                  or result.get('human_approved')):
            raise ValueError('Only delivered FAQ responses can receive FAQ feedback')
        self._feedback[decision_id] = (faq_id, rating)

    def approve(self, decision_id):
        """A reviewer accepts a suggested FAQ; the original classification stays intact."""
        result = self._result(decision_id)
        faq = self._faqs.get(result['faq_match']['faq_id'])
        if faq is None:
            raise ValueError('No suggested FAQ to approve')
        result['human_approved'] = True
        result['response'] = faq['answer']
        return {'ticket_id': decision_id, **deepcopy(result)}
