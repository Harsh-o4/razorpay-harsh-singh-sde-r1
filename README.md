# Ticket categorisation MVP

A plain Python program using in-memory dictionaries and lists. Requires Python 3.10+; no packages, database, API keys or server setup. FAQs, feedback and tickets disappear when the process exits.

## Run

```bash
python3 -m ticket_agent
python3 -m ticket_agent --text "Unauthorized payment from my account" --amount 75000
```

To demonstrate an automated response using **synthetic sample ratings**:

```bash
python3 -m ticket_agent --demo --text "How can I request a refund?"
```

Without `--demo`, the sample FAQs have no customer feedback and require human review. Sample answers should be replaced with your approved policies.

## Use in Python

```python
from ticket_agent import Store, SupportAgent

store = Store()
store.add_faq(
    question="How can I request a refund?",
    answer="Contact the merchant with your transaction reference.",
    category="refund",
    # Example only: replace with actual existing customer ratings.
    ratings=[5] * 12,
)
agent = SupportAgent(store)

result = agent.handle({"text": "How can I request a refund?", "amount": 500})
print(result["decision"]["action"])  # automated_response or escalate
print(result["department"])         # Department on escalation; otherwise None
print(result["response"])           # Automated FAQ answer; otherwise None
print(result["decision"]["confidence"])

store.feedback(result["ticket_id"], 5)
```

Reuse the same `store` and `agent` objects to process multiple tickets in memory. `Store.approve(ticket_id)` allows a human reviewer to accept a suggested FAQ before collecting feedback; it preserves the ticket's original automated/escalated classification. Only record feedback after the answer is actually delivered. A repeated rating for a ticket replaces its previous rating.

## Outcomes

There are exactly two ticket decisions:

- `automated_response`: return a relevant FAQ answer when matching, customer satisfaction and risk checks pass.
- `escalate`: include a department, reasons and a draft acknowledgement for human review.

| Ticket subject | Escalation department |
| --- | --- |
| Refunds or failed payments | Payments Operations |
| Settlements or payouts | Settlement Specialists |
| Fraud, unauthorised transactions or disputes | Risk and Disputes |
| API, SDK or webhook problems | Developer Support |
| Login, password or KYC issues | Account Support |
| Unknown issues | Support Triage |

Category, sentiment, severity, FAQ matching, complexity, routing, resolution estimates and the final decision include confidence scores. These are heuristic scores, not calibrated probabilities. The `categorisation` field describes the ticket's subject; `decision.action` is its two-way classification.

## Reply policy

Automation requires an unambiguous category with confidence >= 0.8, low severity, no negative sentiment, FAQ similarity >= 0.82, and a match margin >= 0.15. The FAQ must also have at least five ratings, satisfaction >= 90%, and a 95% Wilson lower bound >= 0.65 (usually requiring more than five ratings).

Security signals, urgency, negative sentiment, high amounts and uncertain matches cause escalation. Amounts >= INR 10,000 raise severity to medium; >= INR 50,000 to high. Currency defaults to INR; other currencies are rejected. Amounts mentioned only in free text require confirmation.

The analyser uses local intent rules, synonym normalisation and weighted text similarity. It has limited semantic and negation handling, and does not support robust multilingual analysis. Resolution ranges are rough estimates without historical training data. Responses and department assignments are returned as data; no messages or tickets are sent externally.

## Tests

```bash
python3 -m unittest discover -s tests -v
```
