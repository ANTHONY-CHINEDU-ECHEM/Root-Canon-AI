"""Scope and prompt injection controls.

Scope: the assistant answers questions relevant to dental practice, including
the medical history issues that change dental management. Clearly unrelated
requests are declined politely without spending an LLM call.

Injection: retrieved documents are untrusted data. Any chunk containing text
that tries to instruct the model is dropped before it reaches the prompt.
"""

from __future__ import annotations

import re

from backend.app.domain import RetrievedChunk

_DENTAL_SIGNALS = re.compile(
    r"\b(dent|tooth|teeth|molar|incisor|canine|premolar|caries|decay|gum|gingiv|periodon|pulp|endodon|root canal|"
    r"extract|implant|crown|bridge|denture|veneer|filling|restor|amalgam|composite|enamel|dentine|occlus|"
    r"orthodon|brace|aligner|abscess|toothache|oral|mouth|jaw|tmj|tmd|saliva|xerostomia|ulcer|lichen|candid|"
    r"fluorid|toothpaste|floss|mouthwash|chlorhexidine|anaesthe|anesthe|lidocaine|articaine|mepivacaine|"
    r"prilocaine|adrenaline|epinephrine|amoxicillin|penicillin|metronidazole|clindamycin|ibuprofen|paracetamol|"
    r"analges|antibiot|anticoag|warfarin|apixaban|rivaroxaban|dabigatran|edoxaban|bisphosphonate|denosumab|"
    r"mronj|endocarditis|prophyla|sedation|midazolam|bleed|haemostat|socket|suture|radiograph|x-ray|cbct|"
    r"bpe|scale|polish|hygien|sealant|varnish|recall|nice|sdcep|bnf|gdc|fgdp|anaphyla|seizure|hypoglyc|"
    r"angina|faint|syncope|choking|pregnan|breastfeed|child|paediatric)", re.IGNORECASE)

_INJECTION = re.compile(
    r"(ignore (all |any )?(previous|prior|above) (instructions|prompts)|disregard (the )?(system|previous)|"
    r"you are now|new instructions:|system prompt|developer mode|act as (an? )?(unrestricted|jailbroken)|"
    r"<\s*/?\s*(system|instructions?)\s*>)", re.IGNORECASE)

OUT_OF_SCOPE_MESSAGE = (
    "Root Canon AI is a clinical decision support assistant for UK dental practice, so I can only help with "
    "dental clinical questions and the medical issues that affect dental care. Please rephrase your question "
    "in a dental context."
)


def in_scope(question: str, history: list[str] | None = None) -> bool:
    if _DENTAL_SIGNALS.search(question):
        return True
    # Follow up questions ("what about in children?") inherit scope from the conversation.
    return bool(history) and any(_DENTAL_SIGNALS.search(turn) for turn in history[-4:])


def strip_injected(chunks: list[RetrievedChunk]) -> tuple[list[RetrievedChunk], int]:
    clean = [c for c in chunks if not _INJECTION.search(c.chunk.text)]
    return clean, len(chunks) - len(clean)
