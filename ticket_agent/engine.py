"""Explainable offline baseline. Scores are heuristics, not calibrated probabilities."""
import math
import re
from collections import Counter
from decimal import Decimal, InvalidOperation

CATEGORIES = {
    'refund': ('refund', 'reimbursement', 'return my money'),
    'payment_failed': ('payment failed', 'declined', 'debited but', 'charged but', 'unsuccessful', 'payment failure'),
    'settlement': ('settlement', 'payout', 'bank transfer', 'merchant balance'),
    'dispute': ('dispute', 'chargeback', 'unauthorized', 'fraud', 'stolen', 'hacked'),
    'integration': ('api', 'webhook', 'sdk', 'integration', 'signature', 'checkout'),
    'account': ('login', 'password', 'kyc', 'verification', 'account locked'),
    'general': (),
}
TEAMS = {'refund': 'Payments Operations', 'payment_failed': 'Payments Operations',
         'settlement': 'Settlement Specialists', 'dispute': 'Risk and Disputes',
         'integration': 'Developer Support', 'account': 'Account Support', 'general': 'Support Triage'}
STOP = set('a an the is are was were i my me you your to of for and in on it has have how can do please with'.split())
SYNONYMS = {'reimbursement': 'refund', 'reimburse': 'refund', 'refunds': 'refund',
            'declined': 'failed', 'unsuccessful': 'failed', 'payout': 'settlement',
            'charged': 'debited', 'money': 'payment', 'payments': 'payment',
            'authentication': 'login'}


def tokens(text):
    return [SYNONYMS.get(t, t) for t in re.findall(r'[a-z0-9]+', text.lower()) if t not in STOP]


def score(value, confidence, evidence):
    return {'value': value, 'confidence': round(max(0, min(1, confidence)), 3), 'evidence': evidence}


def similarity(query, document, corpus):
    # Corpus-weighted cosine plus query coverage keeps unrelated FAQ words from dominating.
    q, d = Counter(tokens(query)), Counter(tokens(document))
    def weight(term):
        return 1 + math.log((len(corpus) + 1) / (1 + sum(term in tokens(x) for x in corpus)))
    qv = {t: n * weight(t) for t, n in q.items()}
    dv = {t: n * weight(t) for t, n in d.items()}
    denominator = math.sqrt(sum(v*v for v in qv.values()) * sum(v*v for v in dv.values()))
    return sum(v * dv.get(t, 0) for t, v in qv.items()) / denominator if denominator else 0


class SupportAgent:
    def __init__(self, store, min_feedback=5):
        if type(min_feedback) is not int or min_feedback < 1:
            raise ValueError('min_feedback must be a positive integer')
        self.store = store
        self.min_feedback = min_feedback

    def handle(self, ticket):
        if not isinstance(ticket, dict):
            raise ValueError('Ticket must be an object')
        text = ticket.get('text')
        if not isinstance(text, str) or not text.strip() or len(text) > 20000:
            raise ValueError('text must contain 1–20000 characters')
        currency = ticket.get('currency', 'INR')
        if currency != 'INR':
            raise ValueError('Only INR amounts are supported; convert explicitly before submission')
        raw_amount = ticket.get('amount')
        try:
            amount = Decimal(str(raw_amount)) if raw_amount is not None else None
        except InvalidOperation:
            raise ValueError('amount must be a finite non-negative number') from None
        if amount is not None and (not amount.is_finite() or amount < 0):
            raise ValueError('amount must be a finite non-negative number')
        lower = text.lower()
        matches = {key: [p for p in phrases if re.search(r'\b' + re.escape(p) + r'\b', lower)]
                   for key, phrases in CATEGORIES.items()}
        ordered = sorted(matches, key=lambda key: len(matches[key]), reverse=True)
        category = ordered[0] if matches[ordered[0]] else 'general'
        ambiguous = bool(matches[ordered[1]])
        cat_conf = (0.68 if ambiguous else min(.95, .8 + .05 * len(matches[category]))) if category != 'general' else .3
        categorisation = score(category, cat_conf, matches[category] or ['No supported intent detected'])
        negative = [p for p in ('angry', 'terrible', 'frustrated', 'unacceptable', 'furious', 'worst', 'scam', 'not happy') if p in lower]
        positive = [p for p in ('thank you', 'great', 'happy', 'excellent') if p in lower and 'not ' + p not in lower]
        sentiment = score('negative' if negative else 'positive' if positive else 'neutral',
                          .9 if negative else .75 if positive else .6, negative or positive or ['No strong emotional signals'])
        security = bool(matches['dispute'])
        urgent = any(p in lower for p in ('urgent', 'asap', 'immediately', 'outage', 'all transactions', 'legal action'))
        # Unstructured amounts need manual confirmation, even when a currency symbol is present.
        unverified_amount = raw_amount is None and bool(re.search(r'₹|\b(?:inr|rs\.?|rupees|amount|lakh|crore)\b|\d', lower))
        high_amount = amount is not None and amount >= 50000
        medium_amount = amount is not None and amount >= 10000
        severity = 'critical' if security or (urgent and high_amount) else 'high' if high_amount or urgent else 'medium' if negative or medium_amount or unverified_amount else 'low'
        severity_result = score(severity, .95 if security or amount is not None else .65,
            [f'Explicit amount: {amount} INR' if amount is not None else 'Amount unspecified',
             f'Security signals: {security}', f'Urgency signals: {urgent}', f'Negative sentiment: {bool(negative)}'])
        faqs = self.store.faqs()
        corpus = [f['question'] for f in faqs]
        candidates = sorted([(similarity(text, f['question'], corpus), f) for f in faqs if f['category'] == category],
                            key=lambda item: item[0], reverse=True)
        best, faq = candidates[0] if candidates else (0, None)
        margin = best - candidates[1][0] if len(candidates) > 1 else best
        count = faq['feedback_count'] if faq else 0
        satisfaction = faq['satisfaction'] if faq else None
        # Wilson lower bound penalises small samples and does not invent feedback for new FAQs.
        if count:
            z = 1.96
            lower_bound = (satisfaction + z*z/(2*count) - z * math.sqrt(satisfaction*(1-satisfaction)/count + z*z/(4*count*count))) / (1 + z*z/count)
        else:
            lower_bound = 0
        faq_result = {'faq_id': faq['id'] if faq else None, 'confidence': round(best, 3),
                      'match_margin': round(margin, 3), 'feedback_count': count,
                      'satisfaction': satisfaction, 'satisfaction_confidence': round(lower_bound, 3)}
        reasons = []
        if cat_conf < .8 or ambiguous: reasons.append('Uncertain or multiple ticket categories')
        if severity != 'low': reasons.append('Ticket severity requires human review')
        if sentiment['value'] == 'negative': reasons.append('Negative customer sentiment')
        if unverified_amount: reasons.append('Amount in ticket text requires confirmation')
        if best < .82 or margin < .15: reasons.append('FAQ match is weak or ambiguous')
        if count < self.min_feedback or satisfaction is None or satisfaction < .9 or lower_bound < .65:
            reasons.append('Insufficient evidence of FAQ customer satisfaction')
        confidence = min(cat_conf, sentiment['confidence'], severity_result['confidence'], best, lower_bound)
        action = 'escalate' if reasons else 'automated_response'
        team = 'Risk and Disputes' if security else TEAMS[category]
        complexity = 'complex' if security or ambiguous or severity in ('high', 'critical') else 'standard' if severity == 'medium' else 'simple'
        hours = {'simple': (1, 8), 'standard': (4, 24), 'complex': (8, 72)}[complexity]
        result = {'categorisation': categorisation, 'sentiment': sentiment, 'severity': severity_result,
            'faq_match': faq_result,
            'complexity': score(complexity, .75, ['Derived from severity, security and category ambiguity']),
            'routing': score(team, cat_conf if not security else .95, ['Mapped to required support expertise']),
            'resolution_estimate': {'min_hours': hours[0], 'max_hours': hours[1], 'confidence': .4,
                                    'basis': 'Heuristic estimate; no historical resolution data'},
            'department': team if action == 'escalate' else None,
            'decision': {'action': action, 'confidence': round(confidence, 3),
                         'reasons': reasons or ['Strong FAQ match, low risk and reliable positive feedback']},
            'response': faq['answer'] if action == 'automated_response' else None,
            'draft_response': None if action == 'automated_response' else
                f'Thank you for reporting this issue. Your ticket needs review by our {team} team. '
                'Please share the relevant transaction reference through the secure support channel. '
                'Do not share passwords, OTPs or full card details.'}
        result['ticket_id'] = self.store.save(ticket, result)
        return result
