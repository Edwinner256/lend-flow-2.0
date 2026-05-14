"""
AI Service for LendFlow

Provides intelligent features:
  1. Credit Risk Scoring   — assess client risk (rule-based + optional OpenAI)
  2. Portfolio Insights    — AI-generated dashboard summaries
  3. Client Analysis       — per-client AI profile summary
  4. FAQ Chatbot           — simple question answering for client portal

All features work out-of-the-box with rule-based logic.
Set OPENAI_API_KEY in .env for enhanced AI (GPT) responses.
"""

import os
import json
import random
from datetime import datetime, timedelta


# ──────────────────────────────────────────────
#  UTILITY
# ──────────────────────────────────────────────

def _get_openai_client():
    """Return OpenAI client if API key is configured, else None."""
    key = os.environ.get('OPENAI_API_KEY', '').strip()
    if not key:
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=key)
    except ImportError:
        return None


def _call_gpt(system_prompt, user_prompt, max_tokens=500):
    """Call GPT-3.5-turbo if available.  Returns None on failure."""
    client = _get_openai_client()
    if not client:
        return None
    try:
        r = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
            temperature=0.3,
        )
        return r.choices[0].message.content.strip()
    except Exception:
        return None


# ══════════════════════════════════════════════
#  1. CREDIT RISK SCORING
# ══════════════════════════════════════════════

def assess_credit_risk(client_data, repayment_history=None):
    """
    Evaluate a client's creditworthiness.

    Parameters
    ----------
    client_data : dict
        Keys: monthly_income, credit_score, employer, active_loans,
              total_borrowed, late_payments, mpesa_number, bank_name, etc.
    repayment_history : list of dict, optional
        Each entry: {amount, date, on_time (bool), ...}

    Returns
    -------
    dict with keys: score (0-100), rating, factors [], recommendation, source
    """
    if _get_openai_client():
        result = _gpt_risk_assessment(client_data, repayment_history)
        if result:
            return result

    return _rule_risk_assessment(client_data, repayment_history)


def _rule_risk_assessment(client_data, repayment_history=None):
    """Transparent rule-based scoring engine."""
    score = 55  # neutral starting point
    factors = []

    # ── Income ──
    income = float(client_data.get('monthly_income', 0) or 0)
    if income >= 100000:
        score += 12
        factors.append("High monthly income (≥ UGX 100k)")
    elif income >= 50000:
        score += 6
        factors.append("Moderate monthly income")
    elif income >= 20000:
        score -= 5
        factors.append("Low monthly income (< UGX 50k)")
    elif income > 0:
        score -= 10
        factors.append("Very low monthly income")

    # ── Credit score ──
    cs = int(client_data.get('credit_score', 0) or 0)
    if cs >= 750:
        score += 18
        factors.append("Excellent credit score (≥750)")
    elif cs >= 650:
        score += 10
        factors.append("Good credit score")
    elif cs >= 500:
        score -= 5
        factors.append("Fair credit score (500-649)")
    elif cs > 0:
        score -= 15
        factors.append("Poor credit score")

    # ── Active loans ──
    active = int(client_data.get('active_loans', 0) or 0)
    if active == 0:
        score += 8
        factors.append("No active loans — untapped credit")
    elif active == 1:
        score += 3
        factors.append("1 active loan — manageable")
    elif active >= 3:
        score -= 15
        factors.append(f"{active} active loans — high exposure")
    else:
        score -= 5
        factors.append(f"{active} active loans")

    # ── Late payments ──
    late = int(client_data.get('late_payments', 0) or 0)
    if late == 0:
        score += 10
        factors.append("No late payments")
    elif late <= 2:
        score -= 5
        factors.append(f"{late} late payment(s) on record")
    else:
        score -= 18
        factors.append(f"{late} late payments — concerning pattern")

    # ── Employment stability ──
    employer = (client_data.get('employer', '') or '').strip().lower()
    if employer and employer not in ('', 'self employed', 'none', 'n/a'):
        score += 5
        factors.append("Formally employed")
    elif employer == 'self employed':
        score += 2
        factors.append("Self-employed (neutral)")

    # ── Bank account (financial inclusion) ──
    bank = (client_data.get('bank_name', '') or '').strip()
    if bank:
        score += 3
        factors.append("Has bank account")

    # ── Repayment history detail ──
    if repayment_history:
        total = len(repayment_history)
        if total > 0:
            on_time = sum(1 for r in repayment_history if r.get('on_time', True))
            pct = (on_time / total) * 100
            if pct >= 95:
                score += 5
                factors.append("Excellent repayment history (≥95% on time)")
            elif pct >= 80:
                score += 2
                factors.append("Good repayment history")
            else:
                score -= 10
                factors.append(f"Poor repayment history ({pct:.0f}% on time)")

    # Normalise
    score = max(0, min(100, score))

    # ── Rating & recommendation ──
    if score >= 80:
        rating = "Low Risk"
        rec = "Approve — client poses minimal risk"
    elif score >= 65:
        rating = "Low-Moderate Risk"
        rec = "Approve with standard terms"
    elif score >= 50:
        rating = "Moderate Risk"
        rec = "Consider lower amount or shorter term"
    elif score >= 30:
        rating = "High Risk"
        rec = "Request guarantor or collateral"
    else:
        rating = "Very High Risk"
        rec = "Decline — risk exceeds threshold"

    return {
        'score': score,
        'rating': rating,
        'factors': factors,
        'recommendation': rec,
        'source': 'ai (rule engine)',
    }


def _gpt_risk_assessment(client_data, repayment_history=None):
    """Use OpenAI GPT for a natural-language credit assessment."""
    prompt = (
        "You are a credit risk analyst. Assess this client and return a JSON "
        "object with exactly these keys: score (0-100 integer), rating (one of "
        "Low Risk, Low-Moderate Risk, Moderate Risk, High Risk, Very High Risk), "
        "factors (list of 3-5 bullet-point reasons), recommendation "
        "(a short sentence).\n\n"
        f"Client data: {json.dumps(client_data, default=str)}\n"
    )
    if repayment_history:
        prompt += f"Repayment history: {json.dumps(repayment_history, default=str)}\n"
    prompt += "\nReturn ONLY valid JSON."

    text = _call_gpt(
        "You are a credit risk analyst. Output only valid JSON.",
        prompt,
        max_tokens=600,
    )
    if not text:
        return None
    try:
        data = json.loads(text)
        data['source'] = 'ai (OpenAI GPT)'
        return data
    except (json.JSONDecodeError, KeyError):
        return None


# ══════════════════════════════════════════════
#  2. PORTFOLIO INSIGHTS
# ══════════════════════════════════════════════

def generate_portfolio_insights(stats):
    """
    Generate natural-language insights about the loan portfolio.

    Parameters
    ----------
    stats : dict
        Typical keys: total_clients, total_loans, total_disbursed,
        total_collected, outstanding, overdue, pending_loans, active_loans,
        paid_loans, defaulted_loans, total_fines, etc.

    Returns
    -------
    list of dict, each with {icon, title, description, type (positive|warning|neutral)}
    """
    if _get_openai_client():
        result = _gpt_portfolio_insights(stats)
        if result:
            return result

    return _rule_portfolio_insights(stats)


def _rule_portfolio_insights(stats):
    """Generate insights from rules."""
    insights = []

    total = float(stats.get('total_disbursed', 0) or 0)
    collected = float(stats.get('total_collected', 0) or 0)
    outstanding = float(stats.get('outstanding', 0) or 0)
    overdue = float(stats.get('overdue', 0) or 0)
    active = int(stats.get('active_loans', 0) or 0)
    paid = int(stats.get('paid_loans', 0) or 0)
    defaulted = int(stats.get('defaulted_loans', 0) or 0)
    pending = int(stats.get('pending_loans', 0) or 0)
    fines = float(stats.get('total_fines', 0) or 0)
    clients = int(stats.get('total_clients', 0) or 0)

    # ── Collection rate ──
    if total > 0:
        rate = (collected / total) * 100
        if rate >= 70:
            insights.append({
                'icon': 'bi-graph-up-arrow',
                'title': 'Healthy Collection Rate',
                'description': f"{rate:.1f}% of disbursed funds have been recovered ({collected:,.0f} / {total:,.0f} UGX).",
                'type': 'positive',
            })
        elif rate >= 40:
            insights.append({
                'icon': 'bi-graph-up',
                'title': 'Moderate Collection Rate',
                'description': f"{rate:.1f}% collection rate. Review overdue accounts for improvement opportunities.",
                'type': 'neutral',
            })
        else:
            insights.append({
                'icon': 'bi-graph-down',
                'title': 'Low Collection Rate',
                'description': f"Only {rate:.1f}% collected. Consider sending reminders and reviewing credit policies.",
                'type': 'warning',
            })

    # ── Overdue exposure ──
    if total > 0 and overdue > 0:
        overdue_pct = (overdue / total) * 100
        if overdue_pct > 30:
            insights.append({
                'icon': 'bi-exclamation-triangle',
                'title': 'High Overdue Exposure',
                'description': f"{overdue_pct:.1f}% of total portfolio is overdue ({overdue:,.0f} UGX). Immediate attention needed.",
                'type': 'warning',
            })
        elif overdue_pct > 10:
            insights.append({
                'icon': 'bi-exclamation-circle',
                'title': 'Moderate Overdue Exposure',
                'description': f"{overdue_pct:.1f}% of portfolio is overdue ({overdue:,.0f} UGX). Schedule follow-ups.",
                'type': 'neutral',
            })
        else:
            insights.append({
                'icon': 'bi-check-circle',
                'title': 'Low Overdue Exposure',
                'description': f"Only {overdue_pct:.1f}% overdue — portfolio is well-managed.",
                'type': 'positive',
            })

    # ── Default rate ──
    total_loans = active + paid + defaulted + pending
    if total_loans > 0:
        default_rate = (defaulted / total_loans) * 100
        if default_rate > 15:
            insights.append({
                'icon': 'bi-shield-exclamation',
                'title': 'Elevated Default Rate',
                'description': f"{default_rate:.1f}% of loans are defaulted ({defaulted} of {total_loans}). Review credit screening.",
                'type': 'warning',
            })
        elif default_rate > 5:
            insights.append({
                'icon': 'bi-shield-check',
                'title': 'Manageable Default Rate',
                'description': f"{default_rate:.1f}% default rate ({defaulted} loans). Within acceptable range.",
                'type': 'neutral',
            })
        elif defaulted == 0:
            insights.append({
                'icon': 'bi-trophy',
                'title': 'Zero Defaults',
                'description': 'No defaults recorded. Excellent portfolio quality.',
                'type': 'positive',
            })

    # ── Pending approvals ──
    if pending > 0:
        insights.append({
            'icon': 'bi-clock',
            'title': f'{pending} Loan(s) Pending Approval',
            'description': f'{pending} loan application(s) awaiting review. Average response time affects client satisfaction.',
            'type': 'neutral',
        })

    # ── Fine revenue ──
    if fines > 0:
        insights.append({
            'icon': 'bi-cash-stack',
            'title': 'Fine Revenue Generated',
            'description': f'{fines:,.0f} UGX collected in fines. While this adds revenue, reducing defaults should be the priority.',
            'type': 'neutral',
        })

    # ── Average loan size ──
    if total_loans > 0 and total > 0:
        avg = total / total_loans
        insights.append({
            'icon': 'bi-calculator',
            'title': 'Average Loan Size',
            'description': f'{avg:,.0f} UGX per loan. {"Larger loans suggest trust in client base." if avg > 50000 else "Smaller loans suggest micro-lending focus."}',
            'type': 'neutral',
        })

    # ── Client engagement ──
    if clients > 0 and active > 0:
        ratio = active / clients
        insights.append({
            'icon': 'bi-people',
            'title': 'Client Engagement',
            'description': f'Average of {ratio:.1f} active loan(s) per client. { "Healthy engagement." if ratio >= 0.5 else "Opportunity to cross-sell."}',
            'type': 'neutral',
        })

    # Limit to top 6
    return insights[:6]


def _gpt_portfolio_insights(stats):
    """Use OpenAI GPT for portfolio insights."""
    prompt = (
        "You are a financial analyst. Generate 4-6 brief portfolio insights "
        "from this data. Return a JSON array of objects with keys: icon "
        "(Bootstrap icon name like bi-graph-up), title (short), description "
        "(1 sentence), type (positive|warning|neutral).\n\n"
        f"Data: {json.dumps(stats, default=str)}"
    )
    text = _call_gpt(
        "You are a financial analyst. Output only valid JSON.", prompt, max_tokens=800
    )
    if not text:
        return None
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass
    return None


# ══════════════════════════════════════════════
#  3. CLIENT ANALYSIS
# ══════════════════════════════════════════════

def analyze_client(client_data, loans, repayments):
    """
    Generate an AI analysis of a client's overall financial profile.

    Returns a dict with: summary, strengths [], concerns [], suggestions []
    """
    if _get_openai_client():
        result = _gpt_client_analysis(client_data, loans, repayments)
        if result:
            return result

    return _rule_client_analysis(client_data, loans, repayments)


def _rule_client_analysis(client_data, loans, repayments):
    """Rule-based client analysis."""
    strengths = []
    concerns = []
    suggestions = []

    income = float(client_data.get('monthly_income', 0) or 0)
    cs = int(client_data.get('credit_score', 0) or 0)
    active_loans = len([l for l in loans if l.get('status') == 'active'])
    paid_loans = len([l for l in loans if l.get('status') == 'paid'])
    late_count = sum(
        1 for r in repayments if not r.get('on_time', True)
    ) if repayments else 0
    total_borrowed = sum(float(l.get('principal', 0) or 0) for l in loans)
    total_paid = sum(float(r.get('amount', 0) or 0) for r in repayments)

    # Strengths
    if paid_loans > 0:
        strengths.append(f"Successfully completed {paid_loans} loan(s)")
    if cs >= 650:
        strengths.append(f"Good credit score ({cs})")
    if income >= 50000:
        strengths.append(f"Stable income source ({income:,.0f} UGX/mo)")
    if late_count == 0 and len(repayments) > 0:
        strengths.append("Perfect repayment record — no late payments")
    if client_data.get('bank_name'):
        strengths.append("Banked client (financial inclusion)")

    # Concerns
    if active_loans >= 3:
        concerns.append(f"Has {active_loans} active loans — high leverage")
    if cs < 500 and cs > 0:
        concerns.append(f"Low credit score ({cs})")
    if late_count > 2:
        concerns.append(f"{late_count} late payments on record")
    if income < 20000 and income > 0:
        concerns.append(f"Low income ({income:,.0f} UGX/mo) limits borrowing capacity")
    if not client_data.get('employer'):
        concerns.append("No employer information on file")

    # Suggestions
    if active_loans == 0:
        suggestions.append("Eligible for a new loan — consider offering a starter loan")
    elif active_loans < 3:
        suggestions.append("Could qualify for additional credit")
    if late_count > 0:
        suggestions.append("Set up automatic payment reminders to reduce late payments")
    if not client_data.get('next_of_kin'):
        suggestions.append("Request next-of-kin details for emergency contact")
    if not client_data.get('bank_name') and income > 0:
        suggestions.append("Encourage opening a bank account for better financial tracking")
    if not client_data.get('mpesa_number'):
        suggestions.append("Collect mobile money number for faster disbursements")

    # Summary
    summary = (
        f"Client has {'no loan history' if len(loans) == 0 else f'{len(loans)} loan(s) on record'}. "
        f"{'Good repayment behaviour.' if late_count <= 1 and len(repayments) > 0 else 'Needs improvement in repayment consistency.' if late_count > 2 else 'Repayment history is being established.'}"
    )

    return {
        'summary': summary,
        'strengths': strengths,
        'concerns': concerns,
        'suggestions': suggestions,
        'source': 'ai (rule engine)',
    }


def _gpt_client_analysis(client_data, loans, repayments):
    """Use OpenAI GPT for client analysis."""
    prompt = (
        "You are a relationship manager. Analyze this client's profile and "
        "return a JSON object with keys: summary (1-2 sentences), strengths "
        "(list), concerns (list), suggestions (list).\n\n"
        f"Profile: {json.dumps(client_data, default=str)}\n"
        f"Loans: {json.dumps(loans, default=str)}\n"
        f"Repayments: {json.dumps(repayments, default=str)}"
    )
    text = _call_gpt(
        "You are a financial relationship manager. Output only valid JSON.",
        prompt,
        max_tokens=700,
    )
    if not text:
        return None
    try:
        data = json.loads(text)
        data['source'] = 'ai (OpenAI GPT)'
        return data
    except (json.JSONDecodeError, KeyError):
        return None


# ══════════════════════════════════════════════
#  4. FAQ CHATBOT (for client view-only portal)
# ══════════════════════════════════════════════

def get_faq_response(question, loan_data=None):
    """
    Answer a client's question about their loan.

    Parameters
    ----------
    question : str
    loan_data : dict, optional — current loan info for personalised answers

    Returns
    -------
    str — answer text
    """
    q = question.lower().strip()

    # ── Balance / remaining ──
    if any(w in q for w in ['balance', 'remaining', 'how much', 'owe', 'pay']):
        if loan_data:
            bal = float(loan_data.get('balance', 0) or 0)
            return (
                f"Your current outstanding balance is **UGX {bal:,.0f}**. "
                f"This includes the remaining principal and any accrued interest. "
                f"You can make payments at any branch or via mobile money."
            )
        return "Your balance can be viewed on your loan dashboard."

    # ── Next payment / due date ──
    if any(w in q for w in ['next payment', 'due date', 'when', 'installment', 'pay next']):
        if loan_data:
            nxt = loan_data.get('next_payment_date', 'N/A')
            amount = loan_data.get('installment_amount')
            if nxt and nxt != 'N/A':
                resp = f"Your next payment is due on **{nxt}**."
                if amount:
                    resp += f" The installment amount is **UGX {float(amount):,.0f}**."
                return resp
        return "Your payment schedule is shown in the schedule table on your loan page."

    # ── Interest rate ──
    if any(w in q for w in ['interest', 'rate', 'percentage']):
        if loan_data:
            rate = loan_data.get('interest_rate', 'N/A')
            itype = loan_data.get('interest_type', 'flat')
            return (
                f"Your loan has an interest rate of **{rate}%** ({itype} balance). "
                f"This means interest is calculated on the {'original' if itype == 'flat' else 'reducing'} principal amount."
            )
        return "Your interest rate is shown in the loan details section."

    # ── Loan status ──
    if any(w in q for w in ['status', 'approved', 'pending', 'active']):
        if loan_data:
            st = loan_data.get('status', 'unknown')
            return f"Your loan status is: **{st.title()}**."
        return "Your loan status is displayed at the top of your loan page."

    # ── Fine ──
    if any(w in q for w in ['fine', 'penalty', 'late', 'overdue']):
        if loan_data:
            fine = float(loan_data.get('fine_amount', 0) or 0)
            if fine > 0:
                return (
                    f"You currently have a fine of **UGX {fine:,.0f}**. "
                    f"Fines accrue at 0.07% per day on overdue amounts. "
                    f"Clear your overdue payment to stop further fines."
                )
            return "You have no active fines. Continue making timely payments to avoid penalties."
        return "Fine details are shown in your loan information section."

    # ── Payment methods ──
    if any(w in q for w in ['how to pay', 'payment method', 'pay', 'mobile money',
                             'mtn', 'airtel', 'cash', 'bank transfer', 'cheque']):
        return (
            "We accept the following payment methods:\n"
            "• **Cash** — at any branch\n"
            "• **MTN Mobile Money**\n"
            "• **Airtel Money**\n"
            "• **Bank Transfer**\n"
            "• **Cheque**\n\n"
            "Please include your loan number as the payment reference."
        )

    # ── Loan number ──
    if any(w in q for w in ['loan number', 'loan id', 'reference']):
        if loan_data:
            return f"Your loan number is **{loan_data.get('loan_number', 'N/A')}**. Use this in all communications."
        return "Your loan number is shown at the top of your loan page."

    # ── Contact / human ──
    if any(w in q for w in ['contact', 'call', 'speak', 'agent', 'human', 'person']):
        return (
            "To speak with a loan officer, please call **+256 700 000 001** "
            "or visit any branch during business hours (Mon-Fri, 8AM-5PM)."
        )

    # ── Greetings ──
    if any(w in q for w in ['hello', 'hi', 'hey', 'good morning', 'good evening']):
        name = loan_data.get('client_name', '') if loan_data else ''
        greeting = f"Hello{', ' + name if name else ''}! "
        return (
            greeting + "I'm your Vaulta assistant. I can help with questions about "
            "your loan balance, payments, interest rate, fines, and more. "
            "What would you like to know?"
        )

    # ── Default fallback ──
    return (
        "I'm not sure I understand. Here are some things you can ask me:\n"
        "• \"What's my balance?\"\n"
        "• \"When is my next payment?\"\n"
        "• \"What's my interest rate?\"\n"
        "• \"Do I have any fines?\"\n"
        "• \"How can I make a payment?\"\n"
        "• \"What's my loan status?\""
    )


# ══════════════════════════════════════════════
#  GET ALL AI DATA FOR DASHBOARD
# ══════════════════════════════════════════════

def get_dashboard_ai_data(stats):
    """Return all AI data for the dashboard in one call."""
    insights = generate_portfolio_insights(stats)
    return {
        'insights': insights,
        'ai_enabled': _get_openai_client() is not None,
    }
