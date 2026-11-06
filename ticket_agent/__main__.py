"""Run one ticket from the terminal, with no server or database."""
import argparse
import json
from . import Store, SupportAgent


def make_agent(demo=False):
    store = Store()
    # Replace these sample answers with your approved support policies.
    # Demo ratings are synthetic and used only when --demo is explicitly selected.
    store.add_faq('How can I request a refund?',
                  'Contact the merchant with your transaction reference to request a refund.',
                  'refund', ratings=[5] * 12 if demo else None)
    store.add_faq('How can I reset my password?',
                  'Use the Forgot password option on the login page.',
                  'account', ratings=[5] * 12 if demo else None)
    return SupportAgent(store)


def main():
    parser = argparse.ArgumentParser(description='In-memory ticket categorisation MVP')
    parser.add_argument('--text', help='Ticket text; prompts when omitted')
    parser.add_argument('--amount', help='Amount involved, in INR')
    parser.add_argument('--demo', action='store_true', help='Use explicitly synthetic FAQ ratings')
    args = parser.parse_args()
    try:
        text = args.text if args.text is not None else input('Enter ticket: ')
        agent = make_agent(args.demo)
        result = agent.handle({'text': text, 'amount': args.amount})
    except (ValueError, EOFError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
