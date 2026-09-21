# 04 — KYC onboarding intake agent

Takes an unstructured client onboarding bundle — scanned certificates,
passport pages, emailed questionnaires, relationship-manager notes — and
produces a structured case file, a review memorandum, and a full audit
trail of where every extracted fact came from.

## Design principle

**The system does not make compliance decisions.** It extracts, validates,
flags, and routes. A compliance officer reviews and signs off on
everything. This is not a limitation being apologised for — an automated
system that approved or rejected clients would be unusable in a regulated
firm, and in most jurisdictions unlawful.

The routing outcomes are `STANDARD_REVIEW`,
`STANDARD_REVIEW_WITH_CONDITIONS`, and `ENHANCED_DUE_DILIGENCE`. None of
them is "approved."

## Architecture

```
document bundle
      |
      v
[ LLM extraction agent ]   reads messy text, calls tools to record
      |                    structured facts, cites a source for each
      v
 case file (dict)
      |
      v
[ deterministic validation ]   policy rules in plain Python
      |
      v
findings -> routing decision -> memo + JSON + audit trail
```

The split matters. The model handles *"what does this document say?"* —
which it is good at, and which rules handle badly. Plain Python handles
*"does that satisfy our requirements?"* — which must be reproducible and
auditable, and which a model handles badly.

Every tool schema makes `source_reference` a required field, so the model
cannot record a fact without stating where it read it. The audit trail is
a byproduct of that constraint rather than something bolted on afterwards.

## Checks implemented

Identity document presence, expiry, and imminent expiry. Beneficial
ownership coverage at the 25% threshold, including nominee arrangements
that fail to disclose the underlying beneficiary. Required document
checklist per individual. Higher-risk jurisdiction screening on both the
entity and individual addresses. A keyword first-pass for political
exposure — which routes to enhanced due diligence rather than declaring
anyone a PEP. Source of wealth and funds statements screened for
unverifiable language.

Thresholds and lists live at the top of `validation.py`. In a real
deployment they would be configuration owned and approved by the
compliance function, not constants in a source file.

## Run it

```bash
py -m pip install -r requirements.txt
copy .env.example .env      # then paste your key in
py kyc_agent.py sample_documents/client_001_packet.txt
py kyc_agent.py sample_documents/client_002_packet.txt
```

Output lands in `output/` as a JSON case file and a text memorandum.

## Sample cases

`client_001` is a UK holding company with a nominee shareholder concealing
a beneficial owner in Cyprus, two directors with incomplete documentation,
and a source-of-funds statement containing the phrase "some family money
from overseas."

`client_002` is a Cayman fund with a missing proof of address, a
signatory who sat on the board of a state investment vehicle, a
beneficial-ownership declaration that asserts no one crosses 25% without
evidence, and a relationship manager applying deadline pressure.

Both are synthetic. All names, numbers, and addresses are invented.
