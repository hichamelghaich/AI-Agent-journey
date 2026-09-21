"""
04-kyc-intake: a KYC onboarding intake agent.

WHAT IT DOES
------------------------------------------------------------------
Takes a messy onboarding document bundle (scanned pages, emailed
forms, RM notes) and produces:

  1. a structured case file (JSON)
  2. a human-readable review memo
  3. an audit trail of every extraction and where it came from

WHAT IT DELIBERATELY DOES NOT DO
------------------------------------------------------------------
Approve or reject anyone. It prepares the file and routes it. A
human compliance officer makes every decision. This is not a
limitation we're apologising for -- it is the design requirement.

ARCHITECTURE
------------------------------------------------------------------
    document text
         |
         v
    [ LLM agent ]  extracts structured facts via tools,
         |         citing a source page for every one
         v
    case file (dict)
         |
         v
    [ validation.py ]  deterministic rules -> findings
         |
         v
    routing decision + memo + audit log

Run it:
    py -m pip install -r requirements.txt
    copy .env.example .env      (then paste your key in)
    py kyc_agent.py sample_documents/client_001_packet.txt
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
import anthropic

import validation

load_dotenv()

client = anthropic.Anthropic()
MODEL = "claude-sonnet-5"   # extraction accuracy matters more than cost here


# ---------------------------------------------------------------------------
# THE CASE FILE
#
# The agent fills this in by calling tools. Starting it empty and letting
# tools populate it means we always know exactly which tool call produced
# which field -- that is the audit trail.
# ---------------------------------------------------------------------------

def new_case(source_file: str) -> dict:
    return {
        "case_reference": f"KYC-{datetime.now():%Y%m%d-%H%M%S}",
        "source_file": source_file,
        "extracted_at": datetime.now().isoformat(timespec="seconds"),
        "entity": {},
        "individuals": [],
        "ownership": [],
        "analyst_observations": [],
        "missing_items": [],
        "audit_trail": [],
    }


def _audit(case: dict, action: str, detail: dict, source: str):
    """Every write to the case file is logged with its source."""
    case["audit_trail"].append({
        "sequence": len(case["audit_trail"]) + 1,
        "action": action,
        "source_reference": source,
        "data": detail,
    })


# ---------------------------------------------------------------------------
# TOOLS
#
# Note that every tool requires a `source_reference`. The agent cannot
# record a fact without saying where it read it. That constraint is
# enforced by the schema -- it's in the "required" list, so the API
# will not let the model omit it.
# ---------------------------------------------------------------------------

def record_entity(case, legal_name, jurisdiction, source_reference,
                  registration_number=None, entity_type=None,
                  formation_date=None, registered_address=None,
                  business_description=None, source_of_funds=None):
    case["entity"] = {
        "legal_name": legal_name,
        "jurisdiction": jurisdiction,
        "registration_number": registration_number,
        "entity_type": entity_type,
        "formation_date": formation_date,
        "registered_address": registered_address,
        "business_description": business_description,
        "source_of_funds": source_of_funds,
    }
    _audit(case, "record_entity", case["entity"], source_reference)
    return f"Recorded entity: {legal_name}"


def record_individual(case, full_name, role, source_reference,
                      date_of_birth=None, nationality=None,
                      id_document_type=None, id_document_number=None,
                      id_expiry=None, address=None, background=None,
                      source_of_wealth=None, documents_provided=None):
    person = {
        "full_name": full_name,
        "role": role,
        "date_of_birth": date_of_birth,
        "nationality": nationality,
        "id_document_type": id_document_type,
        "id_document_number": id_document_number,
        "id_expiry": id_expiry,
        "address": address,
        "background": background,
        "source_of_wealth": source_of_wealth,
        "documents_provided": documents_provided or [],
    }
    case["individuals"].append(person)
    _audit(case, "record_individual", person, source_reference)
    return f"Recorded individual: {full_name} ({role})"


def record_ownership(case, owner_name, percentage, source_reference,
                     is_nominee=False, beneficial_owner_name=None,
                     beneficial_owner_details=None):
    holding = {
        "owner_name": owner_name,
        "percentage": percentage,
        "is_nominee": is_nominee,
        "beneficial_owner_name": beneficial_owner_name,
        "beneficial_owner_details": beneficial_owner_details,
    }
    case["ownership"].append(holding)
    _audit(case, "record_ownership", holding, source_reference)
    return f"Recorded holding: {owner_name} {percentage}%"


def note_observation(case, observation, why_it_matters, source_reference):
    """
    For things a rule can't catch -- context, inconsistencies, things
    that read oddly. Explicitly labelled as the model's observation so
    nobody mistakes it for a determination.
    """
    item = {
        "observation": observation,
        "why_it_matters": why_it_matters,
        "raised_by": "automated_extraction",
    }
    case["analyst_observations"].append(item)
    _audit(case, "note_observation", item, source_reference)
    return "Observation noted for analyst attention."


def note_missing(case, item, why_required, source_reference="not present in bundle"):
    entry = {"item": item, "why_required": why_required}
    case["missing_items"].append(entry)
    _audit(case, "note_missing", entry, source_reference)
    return f"Noted missing item: {item}"


TOOL_SCHEMAS = [
    {
        "name": "record_entity",
        "description": (
            "Record the corporate entity being onboarded. Call once. "
            "If a field is not stated in the documents, omit it rather "
            "than guessing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "legal_name": {"type": "string"},
                "jurisdiction": {"type": "string", "description": "Country or territory of registration"},
                "registration_number": {"type": "string"},
                "entity_type": {"type": "string", "description": "e.g. private limited company, limited partnership"},
                "formation_date": {"type": "string"},
                "registered_address": {"type": "string"},
                "business_description": {"type": "string"},
                "source_of_funds": {"type": "string", "description": "Verbatim or close paraphrase of any stated source of funds"},
                "source_reference": {"type": "string", "description": "Where in the bundle this came from, e.g. 'Page 1, Certificate of Incorporation'"},
            },
            "required": ["legal_name", "jurisdiction", "source_reference"],
        },
    },
    {
        "name": "record_individual",
        "description": (
            "Record a natural person connected to the entity: director, "
            "signatory, shareholder, or beneficial owner. Call once per "
            "person. Include any stated background or career history in "
            "'background' -- it is screened for PEP exposure."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "full_name": {"type": "string"},
                "role": {"type": "string", "description": "e.g. director, authorised signatory, beneficial owner"},
                "date_of_birth": {"type": "string"},
                "nationality": {"type": "string"},
                "id_document_type": {"type": "string", "description": "e.g. passport, national ID"},
                "id_document_number": {"type": "string"},
                "id_expiry": {"type": "string", "description": "Expiry date as written, e.g. '09 FEB 2031' or '12/2029'"},
                "address": {"type": "string", "description": "Residential address if given"},
                "background": {"type": "string", "description": "Any stated career history, prior roles, or political/state connections"},
                "source_of_wealth": {"type": "string"},
                "documents_provided": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Which of these are actually present: identity_document, proof_of_address",
                },
                "source_reference": {"type": "string"},
            },
            "required": ["full_name", "role", "source_reference"],
        },
    },
    {
        "name": "record_ownership",
        "description": (
            "Record a shareholding or ownership interest. If shares are "
            "held by a nominee, set is_nominee true and record the "
            "underlying beneficiary if disclosed anywhere in the bundle."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "owner_name": {"type": "string"},
                "percentage": {"type": "number"},
                "is_nominee": {"type": "boolean"},
                "beneficial_owner_name": {"type": "string"},
                "beneficial_owner_details": {"type": "string", "description": "DOB, residence, anything else disclosed"},
                "source_reference": {"type": "string"},
            },
            "required": ["owner_name", "percentage", "source_reference"],
        },
    },
    {
        "name": "note_observation",
        "description": (
            "Raise something an analyst should look at that structured "
            "fields don't capture: inconsistencies between documents, "
            "unusual structures, commercial pressure, gaps in a narrative. "
            "Do not draw conclusions about whether the client is acceptable."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "observation": {"type": "string"},
                "why_it_matters": {"type": "string"},
                "source_reference": {"type": "string"},
            },
            "required": ["observation", "why_it_matters", "source_reference"],
        },
    },
    {
        "name": "note_missing",
        "description": "Record a document or data point that should be present but is not.",
        "input_schema": {
            "type": "object",
            "properties": {
                "item": {"type": "string"},
                "why_required": {"type": "string"},
                "source_reference": {"type": "string"},
            },
            "required": ["item", "why_required"],
        },
    },
]


SYSTEM_PROMPT = """You are a KYC analyst assistant performing document intake.

Your job is EXTRACTION and OBSERVATION only. You do not decide whether a
client is acceptable, whether to approve onboarding, or whether anyone is
actually a politically exposed person. A human compliance officer makes
every such decision. Your output is the file they will review.

Rules:

1. Record only what the documents state. If something is not stated, omit
   the field or use note_missing. Never infer a passport number, a date,
   or an address that is not written down.

2. Every tool call requires a source_reference. Be specific: cite the page
   or section you read it from.

3. Capture stated background and career history in the 'background' field,
   especially any government, state, or public-sector roles. This text is
   screened automatically downstream.

4. Look for what is NOT there. Missing proof of address, undisclosed
   beneficial owners behind nominees, vague source-of-wealth statements,
   unexplained gaps. Use note_missing and note_observation for these.

5. Use note_observation for inconsistencies between documents, unusual
   ownership structures, or contextual pressure (e.g. a rushed deadline).
   Describe what you observed and why an analyst should care. Do not
   characterise the client.

Work through the bundle systematically, then stop. Do not write a summary
in prose -- the tool calls are the output."""


TOOL_FUNCTIONS = {
    "record_entity": record_entity,
    "record_individual": record_individual,
    "record_ownership": record_ownership,
    "note_observation": note_observation,
    "note_missing": note_missing,
}


def extract_case(document_text: str, source_file: str, verbose=True) -> dict:
    """Run the extraction agent over one document bundle."""
    case = new_case(source_file)

    messages = [{
        "role": "user",
        "content": (
            "Perform KYC document intake on the following bundle. "
            "Extract everything using the tools provided.\n\n"
            f"--- BEGIN BUNDLE ---\n{document_text}\n--- END BUNDLE ---"
        ),
    }]

    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            break

        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            func = TOOL_FUNCTIONS[block.name]
            if verbose:
                subject = (
                    block.input.get("legal_name")
                    or block.input.get("full_name")
                    or block.input.get("owner_name")
                    or block.input.get("item")
                    or block.input.get("observation", "")[:50]
                )
                print(f"  [{block.name}] {subject}")
            outcome = func(case, **block.input)
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": outcome,
            })

        messages.append({"role": "user", "content": results})

    return case


# ---------------------------------------------------------------------------
# REPORTING
# ---------------------------------------------------------------------------

def build_memo(case: dict, findings: list, outcome: dict) -> str:
    entity = case.get("entity", {})
    lines = []
    add = lines.append

    add("=" * 68)
    add("KYC INTAKE REVIEW MEMORANDUM")
    add("=" * 68)
    add(f"Case reference : {case['case_reference']}")
    add(f"Source bundle  : {case['source_file']}")
    add(f"Prepared       : {case['extracted_at']}")
    add("")
    add("PREPARED BY AUTOMATED INTAKE. NOT A COMPLIANCE DECISION.")
    add("All findings require review and sign-off by a compliance officer.")
    add("")

    add("-" * 68)
    add("SUBJECT ENTITY")
    add("-" * 68)
    add(f"Legal name     : {entity.get('legal_name', 'NOT ESTABLISHED')}")
    add(f"Jurisdiction   : {entity.get('jurisdiction', '-')}")
    add(f"Registration   : {entity.get('registration_number', '-')}")
    add(f"Type           : {entity.get('entity_type', '-')}")
    add(f"Formed         : {entity.get('formation_date', '-')}")
    add(f"Business       : {entity.get('business_description', '-')}")
    add("")

    add("-" * 68)
    add(f"CONNECTED INDIVIDUALS ({len(case['individuals'])})")
    add("-" * 68)
    for person in case["individuals"]:
        add(f"  {person['full_name']}  --  {person.get('role', '-')}")
        add(f"      DOB {person.get('date_of_birth', '-')} | "
            f"{person.get('nationality', '-')}")
        add(f"      ID: {person.get('id_document_type', '-')} "
            f"{person.get('id_document_number', '-')} "
            f"(expires {person.get('id_expiry', '-')})")
        if person.get("background"):
            add(f"      Background: {person['background']}")
        add("")

    add("-" * 68)
    add(f"OWNERSHIP ({len(case['ownership'])} holdings)")
    add("-" * 68)
    for holding in case["ownership"]:
        marker = " [NOMINEE]" if holding.get("is_nominee") else ""
        add(f"  {holding['owner_name']}: {holding['percentage']}%{marker}")
        if holding.get("beneficial_owner_name"):
            add(f"      -> beneficial owner: {holding['beneficial_owner_name']}")
            if holding.get("beneficial_owner_details"):
                add(f"         {holding['beneficial_owner_details']}")
    add("")

    add("-" * 68)
    add(f"AUTOMATED FINDINGS ({len(findings)})")
    add("-" * 68)
    if not findings:
        add("  None raised.")
    for f in sorted(findings, key=lambda x: x["severity"] != "high"):
        add(f"  [{f['severity'].upper():6}] {f['rule']}")
        add(f"           subject: {f['subject']}")
        add(f"           {f['detail']}")
        add("")

    if case["missing_items"]:
        add("-" * 68)
        add("OUTSTANDING ITEMS")
        add("-" * 68)
        for item in case["missing_items"]:
            add(f"  - {item['item']}")
            add(f"      {item['why_required']}")
        add("")

    if case["analyst_observations"]:
        add("-" * 68)
        add("OBSERVATIONS FOR ANALYST ATTENTION")
        add("-" * 68)
        for obs in case["analyst_observations"]:
            add(f"  - {obs['observation']}")
            add(f"      Why it matters: {obs['why_it_matters']}")
        add("")

    add("=" * 68)
    add(f"ROUTING: {outcome['routing']}")
    add("=" * 68)
    add(outcome["rationale"])
    add("")
    add(f"Audit trail: {len(case['audit_trail'])} recorded extractions, "
        "each with source reference (see JSON case file).")

    return "\n".join(lines)


def process(path: str):
    source = Path(path)
    if not source.exists():
        print(f"File not found: {path}")
        return

    print(f"\nReading {source.name} ...")
    text = source.read_text(encoding="utf-8")

    print("Extracting:")
    case = extract_case(text, source.name)

    print("\nRunning deterministic validation ...")
    findings = validation.run_all_checks(case)
    outcome = validation.determine_outcome(findings)
    case["findings"] = findings
    case["routing"] = outcome

    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)
    stem = f"{case['case_reference']}_{source.stem}"

    json_path = out_dir / f"{stem}.json"
    json_path.write_text(json.dumps(case, indent=2), encoding="utf-8")

    memo = build_memo(case, findings, outcome)
    memo_path = out_dir / f"{stem}_memo.txt"
    memo_path.write_text(memo, encoding="utf-8")

    print("\n" + memo)
    print(f"\nWritten: {json_path}")
    print(f"Written: {memo_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: py kyc_agent.py <document file>")
        print("Example: py kyc_agent.py sample_documents/client_001_packet.txt")
        raise SystemExit(1)
    process(sys.argv[1])
