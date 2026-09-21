"""
Deterministic validation rules.

WHY THIS FILE EXISTS SEPARATELY FROM THE AGENT
------------------------------------------------------------------
The agent (an LLM) is good at reading messy documents and pulling
structure out of them. It is NOT the right thing to enforce rules.

Rules must be deterministic: the same input must produce the same
output every single time, and you must be able to point at the line
of code that produced a given decision. A regulator asking "why was
this client flagged?" needs an answer better than "the model felt
strongly about it."

So the division of labour is:
    LLM   -> "what does this document say?"          (extraction)
    CODE  -> "does that satisfy our requirements?"   (validation)

This pattern -- probabilistic extraction wrapped in deterministic
checks -- is how essentially all serious compliance AI is built.
"""

from datetime import date, datetime

# ---------------------------------------------------------------------------
# Policy constants. In a real deployment these live in config, owned by
# the compliance team, version-controlled and approved -- not buried in
# code where an engineer can quietly change them.
# ---------------------------------------------------------------------------

UBO_THRESHOLD_PCT = 25.0          # standard beneficial-ownership threshold
ID_MIN_VALIDITY_DAYS = 90         # reject IDs expiring within this window

# Illustrative only. Real screening uses maintained lists (FATF, EU, OFAC).
HIGHER_RISK_JURISDICTIONS = {
    "cayman islands", "british virgin islands", "panama", "seychelles",
    "belize", "cyprus", "marshall islands",
}

REQUIRED_FOR_INDIVIDUAL = ["identity_document", "proof_of_address"]

# Deterministic first-pass PEP indicators. A keyword hit is NOT a PEP
# determination -- it routes the case to enhanced due diligence, where
# a human decides.
PEP_INDICATORS = [
    "state", "government", "ministry", "minister", "parliament",
    "sovereign", "public official", "ambassador", "central bank",
    "state-owned", "national", "municipal",
]


def _parse_date(value):
    """Try common date formats. Returns a date, or None if unparseable."""
    if not value:
        return None
    if isinstance(value, date):
        return value
    formats = ["%Y-%m-%d", "%d/%m/%Y", "%m/%Y", "%d %b %Y", "%d %B %Y", "%Y"]
    for fmt in formats:
        try:
            return datetime.strptime(str(value).strip(), fmt).date()
        except ValueError:
            continue
    return None


def check_id_validity(individuals, today=None):
    """Identity documents must exist and not be expiring imminently."""
    today = today or date.today()
    findings = []

    for person in individuals:
        name = person.get("full_name", "UNKNOWN")
        doc_no = person.get("id_document_number")
        expiry_raw = person.get("id_expiry")

        if not doc_no:
            findings.append({
                "rule": "ID_MISSING",
                "severity": "high",
                "subject": name,
                "detail": "No identity document number captured.",
            })
            continue

        expiry = _parse_date(expiry_raw)
        if expiry is None:
            findings.append({
                "rule": "ID_EXPIRY_UNREADABLE",
                "severity": "medium",
                "subject": name,
                "detail": f"Could not parse expiry date: {expiry_raw!r}",
            })
            continue

        days_left = (expiry - today).days
        if days_left < 0:
            findings.append({
                "rule": "ID_EXPIRED",
                "severity": "high",
                "subject": name,
                "detail": f"Identity document expired on {expiry}.",
            })
        elif days_left < ID_MIN_VALIDITY_DAYS:
            findings.append({
                "rule": "ID_EXPIRING_SOON",
                "severity": "medium",
                "subject": name,
                "detail": f"Expires {expiry} ({days_left} days).",
            })

    return findings


def check_ubo_coverage(ownership):
    """
    Every holding at or above the threshold must resolve to a named
    natural person. Nominee arrangements must disclose the beneficiary.
    """
    findings = []
    total_identified = 0.0

    for holding in ownership:
        owner = holding.get("owner_name", "UNKNOWN")
        pct = holding.get("percentage") or 0.0
        is_nominee = bool(holding.get("is_nominee"))
        beneficial_owner = holding.get("beneficial_owner_name")

        if is_nominee and not beneficial_owner:
            findings.append({
                "rule": "NOMINEE_WITHOUT_UBO",
                "severity": "high",
                "subject": owner,
                "detail": (
                    f"{owner} holds {pct}% as nominee but no underlying "
                    "beneficial owner was identified."
                ),
            })
        elif pct >= UBO_THRESHOLD_PCT:
            total_identified += pct

        if is_nominee and beneficial_owner:
            total_identified += pct

    if not ownership:
        findings.append({
            "rule": "OWNERSHIP_NOT_ESTABLISHED",
            "severity": "high",
            "subject": "entity",
            "detail": "No ownership structure was captured from the documents.",
        })

    return findings


def check_required_documents(individuals):
    """Each individual needs the standard document set."""
    findings = []
    for person in individuals:
        name = person.get("full_name", "UNKNOWN")
        provided = set(person.get("documents_provided") or [])
        for required in REQUIRED_FOR_INDIVIDUAL:
            if required not in provided:
                findings.append({
                    "rule": "DOCUMENT_MISSING",
                    "severity": "high",
                    "subject": name,
                    "detail": f"Missing required document: {required}.",
                })
    return findings


def check_jurisdiction_risk(entity, individuals):
    """Flag higher-risk jurisdictions for enhanced due diligence."""
    findings = []

    juris = (entity.get("jurisdiction") or "").strip().lower()
    if juris in HIGHER_RISK_JURISDICTIONS:
        findings.append({
            "rule": "HIGHER_RISK_JURISDICTION",
            "severity": "medium",
            "subject": entity.get("legal_name", "entity"),
            "detail": (
                f"Entity is registered in {entity.get('jurisdiction')}, "
                "which is on the enhanced-scrutiny list."
            ),
        })

    for person in individuals:
        addr = (person.get("address") or "").lower()
        for risky in HIGHER_RISK_JURISDICTIONS:
            if risky in addr:
                findings.append({
                    "rule": "HIGHER_RISK_JURISDICTION",
                    "severity": "medium",
                    "subject": person.get("full_name", "UNKNOWN"),
                    "detail": f"Address is in {risky.title()}.",
                })
    return findings


def check_pep_indicators(individuals):
    """
    Keyword screen against role/background text. A hit routes to
    enhanced due diligence -- it does not declare anyone a PEP.
    """
    findings = []
    for person in individuals:
        haystack = " ".join([
            str(person.get("role") or ""),
            str(person.get("background") or ""),
        ]).lower()

        hits = [kw for kw in PEP_INDICATORS if kw in haystack]
        if hits:
            findings.append({
                "rule": "POSSIBLE_PEP_EXPOSURE",
                "severity": "high",
                "subject": person.get("full_name", "UNKNOWN"),
                "detail": (
                    f"Background text matched PEP indicator(s): "
                    f"{', '.join(sorted(set(hits)))}. Requires human PEP "
                    "determination and enhanced due diligence."
                ),
            })
    return findings


def check_source_of_funds(entity, individuals):
    """Vague source-of-funds statements are a classic weak point."""
    findings = []
    vague_markers = [
        "family money", "overseas", "various", "savings", "personal funds",
        "approx", "some ", "and other",
    ]

    for person in individuals:
        sow = (person.get("source_of_wealth") or "").lower()
        if not sow:
            findings.append({
                "rule": "SOURCE_OF_WEALTH_MISSING",
                "severity": "high",
                "subject": person.get("full_name", "UNKNOWN"),
                "detail": "No source of wealth captured.",
            })
            continue
        vague = [m for m in vague_markers if m in sow]
        if vague:
            findings.append({
                "rule": "SOURCE_OF_WEALTH_VAGUE",
                "severity": "medium",
                "subject": person.get("full_name", "UNKNOWN"),
                "detail": (
                    "Statement contains unverifiable language "
                    f"({', '.join(vague)}). Documentary corroboration required."
                ),
            })

    sof = (entity.get("source_of_funds") or "").lower()
    if sof:
        vague = [m for m in vague_markers if m in sof]
        if vague:
            findings.append({
                "rule": "SOURCE_OF_FUNDS_VAGUE",
                "severity": "medium",
                "subject": entity.get("legal_name", "entity"),
                "detail": (
                    "Entity source-of-funds statement is unverifiable "
                    f"({', '.join(vague)})."
                ),
            })

    return findings


def run_all_checks(case, today=None):
    """Run every rule and return the combined findings."""
    entity = case.get("entity") or {}
    individuals = case.get("individuals") or []
    ownership = case.get("ownership") or []

    findings = []
    findings += check_id_validity(individuals, today=today)
    findings += check_ubo_coverage(ownership)
    findings += check_required_documents(individuals)
    findings += check_jurisdiction_risk(entity, individuals)
    findings += check_pep_indicators(individuals)
    findings += check_source_of_funds(entity, individuals)
    return findings


def determine_outcome(findings):
    """
    Map findings to a routing decision.

    Note what this does NOT do: approve anybody. The only outcomes are
    about WHERE the file goes next. A human makes the actual decision.
    """
    severities = [f["severity"] for f in findings]

    if "high" in severities:
        return {
            "routing": "ENHANCED_DUE_DILIGENCE",
            "rationale": (
                f"{severities.count('high')} high-severity finding(s) require "
                "senior compliance review before onboarding can proceed."
            ),
            "blocking": True,
        }
    if "medium" in severities:
        return {
            "routing": "STANDARD_REVIEW_WITH_CONDITIONS",
            "rationale": (
                f"{severities.count('medium')} medium-severity finding(s) to be "
                "cleared by the analyst; no blocking issues identified."
            ),
            "blocking": False,
        }
    return {
        "routing": "STANDARD_REVIEW",
        "rationale": "No automated findings raised. Analyst review still required.",
        "blocking": False,
    }
