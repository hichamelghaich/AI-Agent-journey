"""
Web interface for the KYC intake agent.

HOW THIS FILE IS STRUCTURED
------------------------------------------------------------------
It contains no business logic at all. Every piece of actual work --
extraction, validation, routing -- lives in kyc_agent.py and
validation.py, and this file only imports and calls them.

That separation is deliberate and worth copying. It means:

  * the agent can run from the terminal, from this UI, or from a
    scheduled job, without any of the logic being duplicated
  * you can test the logic without launching a browser
  * replacing this UI later changes nothing about how it works

A UI layer that contains business logic is one of the most common
and most expensive mistakes in application design.

Run it:
    py app.py
"""

from pathlib import Path

import gradio as gr

import kyc_agent
import validation

SAMPLES_DIR = Path("sample_documents")

# Severity -> colour, used to make findings scannable at a glance.
SEVERITY_COLOURS = {
    "high": "#b3261e",
    "medium": "#8a5a00",
    "low": "#3a5a40",
}

ROUTING_STYLES = {
    "ENHANCED_DUE_DILIGENCE": ("#b3261e", "Escalate to senior compliance"),
    "STANDARD_REVIEW_WITH_CONDITIONS": ("#8a5a00", "Analyst review, conditions to clear"),
    "STANDARD_REVIEW": ("#3a5a40", "Analyst review, no automated findings"),
}


def list_samples():
    if not SAMPLES_DIR.exists():
        return []
    return sorted(p.name for p in SAMPLES_DIR.glob("*.txt"))


def load_sample(name):
    """Put the chosen sample's text into the input box."""
    if not name:
        return ""
    path = SAMPLES_DIR / name
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def render_findings(findings):
    """Build an HTML block of findings, most severe first."""
    if not findings:
        return (
            "<div style='padding:16px;border-radius:8px;"
            "background:rgba(58,90,64,0.12);'>"
            "<strong>No automated findings.</strong><br>"
            "Analyst review is still required.</div>"
        )

    order = {"high": 0, "medium": 1, "low": 2}
    ordered = sorted(findings, key=lambda f: order.get(f["severity"], 3))

    parts = []
    for f in ordered:
        colour = SEVERITY_COLOURS.get(f["severity"], "#555")
        parts.append(f"""
        <div style="border-left:4px solid {colour};padding:10px 14px;
                    margin-bottom:10px;background:rgba(127,127,127,0.07);
                    border-radius:0 6px 6px 0;">
          <div style="font-size:11px;letter-spacing:.08em;text-transform:uppercase;
                      color:{colour};font-weight:700;">
            {f['severity']} &middot; {f['rule']}
          </div>
          <div style="font-weight:600;margin-top:4px;">{f['subject']}</div>
          <div style="margin-top:2px;opacity:.85;">{f['detail']}</div>
        </div>""")
    return "".join(parts)


def render_routing(outcome):
    colour, label = ROUTING_STYLES.get(outcome["routing"], ("#555", ""))
    return f"""
    <div style="border:2px solid {colour};border-radius:10px;padding:16px;">
      <div style="font-size:11px;letter-spacing:.1em;text-transform:uppercase;
                  opacity:.7;">Routing decision</div>
      <div style="font-size:20px;font-weight:700;color:{colour};margin:4px 0;">
        {outcome['routing'].replace('_', ' ')}
      </div>
      <div style="opacity:.85;">{label}</div>
      <div style="margin-top:10px;padding-top:10px;
                  border-top:1px solid rgba(127,127,127,.25);opacity:.8;">
        {outcome['rationale']}
      </div>
    </div>"""


def render_audit(case):
    """The audit trail, as a table. This is the compliance deliverable."""
    rows = []
    for entry in case["audit_trail"]:
        data = entry["data"]
        if isinstance(data, dict):
            summary = (
                data.get("legal_name") or data.get("full_name")
                or data.get("owner_name") or data.get("item")
                or data.get("observation") or ""
            )
        else:
            summary = str(data)
        rows.append([
            entry["sequence"],
            entry["action"],
            str(summary)[:70],
            entry["source_reference"],
        ])
    return rows


def analyse(document_text, progress=gr.Progress()):
    """
    The single callback wired to the button.

    Returns one value per output component, in the order they're listed
    in the .click() call below. Gradio matches them positionally.
    """
    if not document_text or not document_text.strip():
        empty = "<div style='opacity:.6;padding:12px;'>No document provided.</div>"
        return empty, empty, "", [], ""

    progress(0.15, desc="Reading bundle")
    case = kyc_agent.extract_case(document_text, "pasted_document", verbose=False)

    progress(0.75, desc="Applying policy rules")
    findings = validation.run_all_checks(case)
    outcome = validation.determine_outcome(findings)
    case["findings"] = findings
    case["routing"] = outcome

    progress(0.95, desc="Building memorandum")
    memo = kyc_agent.build_memo(case, findings, outcome)

    import json
    return (
        render_routing(outcome),
        render_findings(findings),
        memo,
        render_audit(case),
        json.dumps(case, indent=2),
    )


# ---------------------------------------------------------------------------
# LAYOUT
#
# gr.Blocks gives explicit control over arrangement, unlike ChatInterface
# which builds a fixed chat page. Rows sit side by side, Columns stack
# vertically, and `scale` sets their relative widths.
# ---------------------------------------------------------------------------

with gr.Blocks(title="KYC Intake") as demo:

    gr.Markdown(
        """
        # KYC Onboarding Intake
        Extracts structured client data from unstructured onboarding
        bundles, applies policy rules, and prepares a review file.
        """
    )

    gr.HTML(
        "<div style='border-left:4px solid #8a5a00;padding:10px 14px;"
        "background:rgba(138,90,0,.08);border-radius:0 6px 6px 0;"
        "margin-bottom:8px;'>"
        "<strong>Decision support only.</strong> This system does not "
        "approve or reject clients. Every case is routed to a compliance "
        "officer for review and sign-off."
        "</div>"
    )

    with gr.Row():
        # -------- left: input --------
        with gr.Column(scale=4):
            sample_picker = gr.Dropdown(
                choices=list_samples(),
                label="Load a sample bundle",
                value=None,
            )
            document_box = gr.Textbox(
                label="Onboarding bundle",
                placeholder="Paste document text here, or load a sample above.",
                lines=22,
                max_lines=22,
            )
            run_button = gr.Button("Run intake", variant="primary", size="lg")

        # -------- right: results --------
        with gr.Column(scale=6):
            routing_html = gr.HTML()

            with gr.Tabs():
                with gr.Tab("Findings"):
                    findings_html = gr.HTML()
                with gr.Tab("Memorandum"):
                    memo_box = gr.Textbox(label=None, lines=28, max_lines=28)
                with gr.Tab("Audit trail"):
                    gr.Markdown(
                        "Every extracted fact, with the source it was read "
                        "from. Produced automatically — the tool schemas "
                        "require a source reference on every call."
                    )
                    audit_table = gr.Dataframe(
                        headers=["#", "Action", "Subject", "Source"],
                        col_count=(4, "fixed"),
                        wrap=True,
                    )
                with gr.Tab("Case file (JSON)"):
                    gr.Markdown(
                        "Machine-readable output, for downstream systems."
                    )
                    json_box = gr.Code(language="json")

    # Wiring: which function runs, what feeds it, where results go.
    sample_picker.change(
        fn=load_sample,
        inputs=sample_picker,
        outputs=document_box,
    )

    run_button.click(
        fn=analyse,
        inputs=document_box,
        outputs=[routing_html, findings_html, memo_box, audit_table, json_box],
    )


if __name__ == "__main__":
    demo.launch(theme=gr.themes.Soft(), share=True)
