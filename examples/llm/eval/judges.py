"""Failure-mode judges for Intent evaluation (issue #96, step 3a).

Three independent yes/no judges ask whether a candidate Intent exhibits one
failure mode for a question, with only a prompt-scoped ontology subset in view:

- ``wrong_relation``: a traverse step uses a relationship or direction that
  does not connect the classes the question asks about.
- ``missing_filter``: the question pins a specific instance value but the
  Intent has no matching ``filter[]`` entry.
- ``over_broad_scope``: the Intent stops at a broader class than the entity the
  question asks for (or omits the traverse needed to reach it).

Judges are scored one mode at a time on purpose: a single "is this query
right?" judge confuses failure modes and cannot be compared against a
field-level label. Output is always::

    {"mode": "...", "answer": "yes" | "no" | "unknown", "rationale"?: "..."}

``unknown`` covers unparseable / out-of-vocabulary judge output and explicit
abstention. It is excluded from precision / recall and reported as ``unknown``.

This module is offline and side-effect free. Prompt build and response parse
are pure; callers supply a responder. Dry runs replay the committed fixture
table (``fixtures/failure_mode_judges.json``); live runs pass an
OpenAI-compatible / LiteLLM backend. There is no network call here.

Scope: step 3a is measurement only. No gate, threshold, F-beta, Brier score,
confidence surface, or product wiring lives here (steps 3b / 3c).
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Callable, Mapping

from .field_match import entity_set, filter_set, intent_field_match
from .gold import GoldCase, make_silent_wrong_intent

MODES: tuple[str, ...] = ("wrong_relation", "missing_filter", "over_broad_scope")
ANSWERS: tuple[str, ...] = ("yes", "no", "unknown")

FIXTURE_SCHEMA_VERSION = "1.0"
FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "failure_mode_judges.json"
)

MODE_INSTRUCTIONS: dict[str, str] = {
    "wrong_relation": (
        "Answer yes when a traverse step uses a relationship or direction that "
        "cannot connect the classes the QUESTION asks about, according to the "
        "ONTOLOGY SUBSET. Answer no when every traverse step is consistent with "
        "the question and the ontology."
    ),
    "missing_filter": (
        "Answer yes when the QUESTION names a specific instance value (SKU, "
        "lot_id, line name, status, code, and so on) and the INTENT has no "
        "filter[] entry pinning that value. Answer no when every named value is "
        "filtered, or when the question names no specific value."
    ),
    "over_broad_scope": (
        "Answer yes when the INTENT stops at a class broader than the entity the "
        "QUESTION asks for (for example it returns products when suppliers are "
        "asked for), or omits a traverse step needed to reach the asked entity. "
        "Answer no when the Intent reaches the asked entity."
    ),
}

SYSTEM_PROMPT = """\
You are a strict, independent evaluation judge for a graph query Intent.

Judge exactly ONE failure mode. Use only the QUESTION, the INTENT, and the
ONTOLOGY SUBSET supplied below. Do not assume facts outside them, and do not
reward the Intent for looking plausible in general.

Failure mode: {mode}
Definition: {instruction}

Reply with one JSON object and nothing else:
{{"answer": "yes" | "no" | "unknown", "rationale": "<one short sentence>"}}
"""

# A judge response is either a JSON object or raw assistant text.
JudgeResponder = Callable[[str, list[dict[str, str]]], str | dict[str, Any]]

# Variant id -> label rule (see ``derive_mode_labels``).
VARIANTS: tuple[str, ...] = (
    "gold",
    "silent_wrong",
    "swap_relation",
    "drop_filter",
    "drop_traverse",
)


def _require_mode(mode: str) -> str:
    if mode not in MODES:
        raise ValueError(f"unknown judge mode: {mode!r} (choose from {MODES})")
    return mode


def _ontology_names(items: Any) -> list[str]:
    names: list[str] = []
    for item in items or []:
        if isinstance(item, Mapping) and item.get("name"):
            names.append(str(item["name"]))
    return sorted(set(names))


def format_ontology_subset(ontology: dict[str, Any] | None) -> str:
    """Compact, deterministic ontology view for the judge prompt."""
    ontology = ontology or {}
    classes = _ontology_names(ontology.get("classes"))
    lines = ["Classes: " + (", ".join(classes) if classes else "(none)")]

    relationships = [
        r
        for r in ontology.get("relationships") or []
        if isinstance(r, Mapping) and r.get("name")
    ]
    lines.append("Relationships:")
    if relationships:
        for rel in sorted(relationships, key=lambda r: str(r.get("name") or "")):
            frm = rel.get("from_class") or "?"
            to = rel.get("to_class") or "?"
            direction = rel.get("direction") or "?"
            lines.append(f"  {rel.get('name')}: {frm} -> {to} ({direction})")
    else:
        lines.append("  (none)")

    by_class: dict[str, set[str]] = {}
    for prop in ontology.get("properties") or []:
        if not isinstance(prop, Mapping):
            continue
        owner = prop.get("owner_class")
        name = prop.get("name")
        if owner and name:
            by_class.setdefault(str(owner), set()).add(str(name))
    lines.append("Properties:")
    if by_class:
        for owner in sorted(by_class):
            lines.append(f"  {owner}: {', '.join(sorted(by_class[owner]))}")
    else:
        lines.append("  (none)")
    return "\n".join(lines)


def build_judge_messages(
    mode: str,
    question: str,
    intent: dict[str, Any],
    ontology_subset: dict[str, Any] | None,
) -> list[dict[str, str]]:
    """Build the system + user messages for one judge and one Intent."""
    _require_mode(mode)
    system = SYSTEM_PROMPT.format(mode=mode, instruction=MODE_INSTRUCTIONS[mode])
    user = (
        "QUESTION:\n"
        f"{question}\n\n"
        "INTENT:\n"
        f"{json.dumps(intent, indent=2, sort_keys=True, ensure_ascii=False)}\n\n"
        "ONTOLOGY SUBSET:\n"
        f"{format_ontology_subset(ontology_subset)}\n"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _unknown(mode: str, rationale: str) -> dict[str, Any]:
    return {"mode": mode, "answer": "unknown", "rationale": rationale}


def parse_judge_response(mode: str, raw: str | dict[str, Any] | None) -> dict[str, Any]:
    """Parse one judge response; malformed output becomes ``answer="unknown"``.

    Never raises for malformed model output — a judge that cannot answer is an
    abstention, not a harness crash. Unknown *modes* still raise (programmer
    error).
    """
    _require_mode(mode)

    if isinstance(raw, Mapping):
        payload: Any = dict(raw)
    elif isinstance(raw, str):
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            return _unknown(
                mode,
                f"unparseable judge output: {exc.msg} at position {exc.pos}",
            )
    else:
        return _unknown(
            mode, f"judge output is not text or an object: {type(raw).__name__}"
        )

    if not isinstance(payload, Mapping):
        return _unknown(
            mode, f"judge output is not a JSON object: {type(payload).__name__}"
        )

    raw_answer = payload.get("answer")
    answer = str(raw_answer).strip().lower() if raw_answer is not None else ""
    if answer not in ANSWERS:
        return _unknown(mode, f"invalid judge answer: {raw_answer!r}")

    result: dict[str, Any] = {"mode": mode, "answer": answer}
    rationale = payload.get("rationale")
    if rationale is not None and str(rationale).strip():
        result["rationale"] = str(rationale).strip()
    return result


def run_judge(
    mode: str,
    question: str,
    intent: dict[str, Any],
    ontology_subset: dict[str, Any] | None,
    responder: JudgeResponder,
) -> dict[str, Any]:
    """Build the prompt, ask ``responder``, and parse the answer."""
    messages = build_judge_messages(mode, question, intent, ontology_subset)
    raw = responder(mode, messages)
    return parse_judge_response(mode, raw)


class FixtureResponder:
    """Offline responder replaying committed fixture answers.

    Answers are keyed by ``(variant, mode)`` and deliberately do not inspect the
    prompt: this exercises prompt build -> parse -> aggregation without a model
    and without pretending to measure judge quality.
    """

    def __init__(
        self,
        answers: Mapping[tuple[str, str], Any],
        variant: str = "gold",
    ) -> None:
        self._answers = answers
        self._variant = variant

    def for_variant(self, variant: str) -> "FixtureResponder":
        return FixtureResponder(self._answers, variant)

    def __call__(self, mode: str, messages: list[dict[str, str]]) -> Any:
        del messages
        answer = self._answers.get((self._variant, mode))
        if answer is None:
            return {
                "mode": mode,
                "answer": "unknown",
                "rationale": (
                    f"no fixture answer for variant={self._variant!r} mode={mode!r}"
                ),
            }
        return answer


def fixture_path() -> Path:
    return FIXTURE_PATH


def load_fixture_answers(path: Path | None = None) -> dict[tuple[str, str], Any]:
    """Load ``{variant: {mode: response}}`` fixture answers."""
    source = path or FIXTURE_PATH
    data = json.loads(source.read_text(encoding="utf-8"))
    if data.get("schema_version") != FIXTURE_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported fixture schema_version in {source}: "
            f"{data.get('schema_version')!r}"
        )
    answers: dict[tuple[str, str], Any] = {}
    for variant, by_mode in (data.get("answers") or {}).items():
        for mode, response in by_mode.items():
            _require_mode(mode)
            answers[(str(variant), str(mode))] = response
    return answers


def derive_mode_labels(
    gold: dict[str, Any], pred: dict[str, Any]
) -> dict[str, bool]:
    """Deterministic failure-mode labels from the field-match scorer.

    The rules keep the three modes independent:

    - ``wrong_relation``: every gold class is still present but the resolved
      traverse set differs (a swapped relationship, not a dropped step).
    - ``missing_filter``: a gold filter on the same (owner, property, operator)
      is absent. A same-slot filter with a different value is a wrong value, not
      a missing filter, so it is deliberately not a positive here.
    - ``over_broad_scope``: at least one gold class is absent, i.e. the Intent
      stops before reaching the asked entity.
    """
    score = intent_field_match(pred, gold)
    gold_entities = entity_set(gold)
    entities_complete = gold_entities <= entity_set(pred)
    gold_filter_keys = {entry[:3] for entry in filter_set(gold)}
    pred_filter_keys = {entry[:3] for entry in filter_set(pred)}
    return {
        "wrong_relation": bool(
            entities_complete and score["field_f1"]["relations"] < 1.0
        ),
        "missing_filter": bool(gold_filter_keys - pred_filter_keys),
        "over_broad_scope": not entities_complete,
    }


def _first_property(
    ontology: dict[str, Any], class_name: str, preferred: str = "name"
) -> str:
    names = sorted(
        {
            str(p["name"])
            for p in ontology.get("properties") or []
            if isinstance(p, Mapping)
            and p.get("name")
            and str(p.get("owner_class")) == class_name
        }
    )
    if preferred in names:
        return preferred
    return names[0] if names else preferred


def swap_relation_intent(
    intent: dict[str, Any], ontology: dict[str, Any]
) -> dict[str, Any] | None:
    """Replace the first traverse relationship with another ontology relation.

    Prefers a relationship joining the same endpoint classes; otherwise falls
    back to any other relationship. Class set stays fixed, so the result is a
    clean ``wrong_relation`` positive rather than a scope change.
    """
    wrong = copy.deepcopy(intent)
    traverse = wrong.get("traverse") or []
    if not traverse:
        return None
    step = traverse[0]
    current = str(step.get("relationship") or "")
    start_class = str((wrong.get("start") or {}).get("class") or "")
    to_class = str((step.get("to") or {}).get("class") or "")

    relationships = [
        r
        for r in ontology.get("relationships") or []
        if isinstance(r, Mapping) and r.get("name")
    ]
    same_pair = [
        r
        for r in relationships
        if str(r.get("from_class")) == start_class
        and str(r.get("to_class")) == to_class
        and str(r.get("name")) != current
    ]
    other = [r for r in relationships if str(r.get("name")) != current]
    candidates = same_pair or other
    if not candidates:
        return None

    replacement = candidates[0]
    step["relationship"] = str(replacement["name"])
    if replacement.get("direction"):
        step["direction"] = str(replacement["direction"])
    return wrong


def drop_filter_intent(intent: dict[str, Any]) -> dict[str, Any] | None:
    """Remove all filters: a clean ``missing_filter`` positive."""
    if not intent.get("filter"):
        return None
    wrong = copy.deepcopy(intent)
    wrong["filter"] = []
    return wrong


def drop_traverse_intent(
    intent: dict[str, Any], ontology: dict[str, Any]
) -> dict[str, Any] | None:
    """Drop the last traverse step: a clean ``over_broad_scope`` positive.

    Returns / filters that pointed at the removed node are rewritten to the
    remaining start node, mirroring how an under-traversing model would answer
    the broader question it actually solved.
    """
    wrong = copy.deepcopy(intent)
    traverse = wrong.get("traverse") or []
    if not traverse:
        return None
    traverse.pop()

    start = wrong.get("start") or {}
    start_alias = str(start.get("alias") or "")
    start_class = str(start.get("class") or "")
    kept_aliases = {start_alias} | {
        str((step.get("to") or {}).get("alias") or "") for step in traverse
    }
    fallback_property = _first_property(ontology, start_class)

    for entry in wrong.get("return") or []:
        if str(entry.get("alias")) not in kept_aliases:
            entry["alias"] = start_alias
            entry["property"] = fallback_property
            entry.pop("aggregate", None)

    wrong["filter"] = [
        entry
        for entry in wrong.get("filter") or []
        if str(entry.get("alias")) in kept_aliases
    ]
    return wrong


def build_variants(
    case: GoldCase, ontology: dict[str, Any]
) -> list[tuple[str, dict[str, Any]]]:
    """Gold plus deterministic field-swap / field-drop variants for one case."""
    variants: list[tuple[str, dict[str, Any]]] = [("gold", copy.deepcopy(case.intent))]
    silent = (
        make_silent_wrong_intent(case.intent, case.corrupt_target)
        if case.corrupt_target
        else None
    )
    if silent is not None:
        variants.append(("silent_wrong", silent))
    swapped = swap_relation_intent(case.intent, ontology)
    if swapped is not None:
        variants.append(("swap_relation", swapped))
    dropped_filter = drop_filter_intent(case.intent)
    if dropped_filter is not None:
        variants.append(("drop_filter", dropped_filter))
    dropped_traverse = drop_traverse_intent(case.intent, ontology)
    if dropped_traverse is not None:
        variants.append(("drop_traverse", dropped_traverse))
    return variants


def score_judge_items(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Precision / recall per mode over ``{mode, expected, answer}`` items.

    ``expected`` is a yes/no string derived from field match. ``unknown``
    answers abstain and are excluded from precision / recall, but counted in
    ``n`` / ``n_unknown`` so abstention does not flatter the judge. Precision
    is ``None`` when the judge never predicted yes; recall is ``None`` when the
    slice has no positives (e.g. the all-negative ``gold`` variant).
    """
    scores: dict[str, dict[str, Any]] = {}
    for mode in MODES:
        tp = fp = fn = tn = unknown = 0
        for item in items:
            if item.get("mode") != mode:
                continue
            answer = str(item.get("answer") or "")
            expected_yes = item.get("expected") == "yes"
            if answer == "unknown":
                unknown += 1
                continue
            predicted_yes = answer == "yes"
            if expected_yes and predicted_yes:
                tp += 1
            elif expected_yes and not predicted_yes:
                fn += 1
            elif not expected_yes and predicted_yes:
                fp += 1
            else:
                tn += 1

        precision = round(tp / (tp + fp), 4) if tp + fp else None
        recall = round(tp / (tp + fn), 4) if tp + fn else None
        f1 = (
            round(2 * precision * recall / (precision + recall), 4)
            if precision is not None and recall is not None and precision + recall
            else None
        )
        scores[mode] = {
            "n": tp + fp + fn + tn + unknown,
            "n_answered": tp + fp + fn + tn,
            "n_unknown": unknown,
            "support_yes": tp + fn,
            "support_no": fp + tn,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }
    return scores
