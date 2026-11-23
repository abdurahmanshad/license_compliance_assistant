# Software Licence Compliance Assistant

A GPT-assisted Streamlit app for software asset and licence compliance teams.

## Problem statement
Organisations buy software under many licence models (named user, concurrent, per processor) and under contracts with audit and true-up clauses. Compliance teams must (1) spot over-deployment, expired and wasted licences before a vendor audit does, and (2) find the terms that matter in long agreements. Today this is manual spreadsheet and contract reading work, which is slow and error-prone.

## What the app does
1. **Inventory check**: upload a CSV of purchased vs installed seats and expiry dates. Python flags Expired, Over-deployed, Expiring soon, Under-used and Compliant, and estimates true-up exposure and potential savings. GPT then writes a ranked risk report with owners and actions.
2. **Agreement terms**: GPT extracts scope, term and renewal, fees, restrictions, audit rights, over-use penalties, termination and assignment as JSON, each with a short quote as evidence, plus risk flags.
3. **Ask the agreement**: question answering grounded in the agreement text with clause citations, and "Not stated in the agreement." when the text is silent.

Without an API key the app runs in offline demo mode (template report and keyword clause search), so it can be shown anywhere.

## Design choices (prompt design and safeguards)
- **Code calculates, GPT explains.** All counts and dollar figures come from `compliance.py`; the prompt forbids the model from inventing or recalculating numbers.
- **Fixed output structure.** The report prompt specifies sections, ranking order and owners, so output is consistent.
- **Structured extraction.** `response_format=json_object`, a named key list, "Not stated" for gaps and verbatim evidence quotes (max 25 words) make answers checkable.
- **Grounded Q&A.** Answer only from the text, cite clause numbers, refuse when absent.
- **Prompt-injection hygiene.** Agreement text is marked as data and instructions inside it are ignored.
- **Low temperature (0.2)** for repeatable output; the app retries without it for models that only allow the default.
- **No legal advice.** Prompts and UI say Legal should confirm contract interpretation.

## Run it
```bash
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...        # optional; or paste it in the sidebar
streamlit run app.py
```

## Files
`app.py` UI · `compliance.py` rules and maths · `llm.py` prompts and API calls · `sample_licenses.csv` · `sample_agreement.txt` (fictional)

## Limitations
Sample data and agreement are synthetic. Seat-based rules do not model processor-core or virtualisation licensing in detail. LLM extraction can miss or misread clauses, so evidence quotes should be checked by a person.

## Resume bullet
Built a GPT-powered licence compliance assistant (Python, Streamlit, OpenAI API) that flags over-deployed, expired and unused software, estimates true-up exposure, extracts audit and termination terms from agreements with evidence quotes, and answers clause-grounded questions.
