"""Stateless scan explanations. Input contains only fixed intents and aggregate counts."""

from typing import Annotated, Literal

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

Intent = Literal["summary", "missing", "attention", "open"]
Outcome = Literal[
    "stored",
    "duplicate",
    "already_stored",
    "needs_review",
    "awaiting_approval",
    "rejected",
    "failed",
    "eligible",
    "already_seen",
    "downloading",
    "scanning",
    "extracting",
]


class ScanFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: Intent
    counts: dict[Outcome, Annotated[int, Field(ge=0)]] | None
    completed: bool
    document_review: bool = False
    size_blocked: bool = False


service = FastAPI(title="CertVault scan explanations")


@service.post("/explain")
def explain(facts: ScanFacts):
    counts = facts.counts
    if not facts.completed:
        return {
            "answer": "This scan has not completed. Check its status in Activity before interpreting the results."
        }
    if counts is None:
        return {"answer": "This historical scan has no recorded outcome counts."}
    summary = ", ".join(f"{n} {k.replace('_', ' ')}" for k, n in counts.items() if n)
    evidence = ""
    if facts.document_review:
        evidence += (
            " At least one document needs inspection because processing or OCR could not finish."
        )
    if facts.size_blocked:
        evidence += " At least one candidate exceeded the storage limit and could not be imported."
    if facts.intent == "missing":
        return {
            "answer": (
                f"The scan recorded {summary}. "
                if summary
                else "The scan recorded no matching items. "
            )
            + evidence.strip()
            + " Its results cannot identify an email that never matched. Check the connected mailbox and scan dates, then check the attachment or issuer link in the original email."
        }
    if facts.intent == "attention":
        return {
            "answer": f"{counts.get('awaiting_approval', 0)} awaiting approval and {counts.get('needs_review', 0)} needing review in this scan. Activity shows available reasons and actions for individual items."
            + evidence
        }
    if facts.intent == "open":
        return {
            "answer": "Choose a saved file below or open My vault to find a badge reference."
            if counts.get("stored")
            else "This scan recorded no newly saved items. Earlier imports are available in My vault."
        }
    return {
        "answer": f"This scan recorded {summary}."
        if summary
        else "This scan recorded no matching items."
    }
