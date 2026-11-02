"""Retained failure witnesses; semantic expectations are not judge results."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.summaries.advisory_review import (
    ReviewError,
    assess_review,
    compatible_review,
    review_receipt,
)
from app.summaries.factual_contract import (
    FactualPlanError,
    render_factual_plan,
    require_contextual_plan,
)
from app.summaries.provider_contract import decode_plan

CORPUS = json.loads(
    (Path(__file__).parent / "fixtures/digest_acceptance_corpus.json").read_text()
)


def frozen(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def test_retained_raw_witnesses_match_their_recorded_hashes():
    names = {
        "raw_duplicate_proposal": "proposal-completion.txt",
        "raw_singleton_proposal": "prior-proposal-completion.txt",
        "raw_singleton_review": "prior-review-completion.txt",
    }
    for key, name in names.items():
        assert (
            hashlib.sha256(CORPUS[key].encode()).hexdigest()
            == CORPUS["origin"]["files_sha256"][name]
        )
    assert len(CORPUS["content"]["factual_basis"]["sources"]) == 19
    assert (
        sum(
            len(source["passages"])
            for source in CORPUS["content"]["factual_basis"]["sources"]
        )
        == 65
    )


def test_actual_duplicate_story_is_rejected_without_repair_or_input_mutation():
    content = deepcopy(CORPUS["content"])
    plan = decode_plan(CORPUS["raw_duplicate_proposal"])
    before = frozen([content, plan])
    assert plan["items"][1] == {"index": 0, "source_ref": 9, "passage_index": 0}
    assert plan["items"][2] == {"index": 0, "source_ref": 9, "passage_index": 1}
    with pytest.raises(FactualPlanError, match="Duplicate or unknown story"):
        render_factual_plan(content, plan)
    assert frozen([content, plan]) == before


def test_actual_singleton_plan_remains_historical_but_cannot_be_fresh():
    content = deepcopy(CORPUS["content"])
    plan = decode_plan(CORPUS["raw_singleton_proposal"])
    before = frozen([content, plan])
    assert render_factual_plan(content, plan)["headline"]
    with pytest.raises(FactualPlanError, match="prose is invalid"):
        require_contextual_plan(plan)
    assert frozen([content, plan]) == before


def test_actual_singleton_review_cannot_recover_a_previously_passed_receipt():
    packet = deepcopy(CORPUS["review_controls"])
    raw = CORPUS["raw_singleton_review"]
    parsed = decode_plan(raw)
    assert len(parsed["assessments"]) == 202
    assert all(len(entry["reason"].strip()) == 1 for entry in parsed["assessments"])
    receipt = review_receipt(packet, status="passed", raw=raw)
    before = frozen([packet, receipt])
    with pytest.raises(ReviewError, match="explanation is invalid"):
        assess_review(raw, packet)
    assert compatible_review(receipt, packet) is False
    assert frozen([packet, receipt]) == before


@pytest.mark.parametrize("case", CORPUS["semantic_cases"], ids=lambda case: case["id"])
def test_semantic_witness_is_reachable_but_not_a_provider_acceptance(case):
    content = deepcopy(CORPUS["content"])
    original = decode_plan(CORPUS["raw_duplicate_proposal"])
    before = frozen([content, original, case])
    # Explicit synthetic isolation, not deduplication of the rejected original:
    # omit ALL optional item overrides so prose reaches its structural boundary.
    synthetic = deepcopy(original)
    synthetic["items"] = []
    assert render_factual_plan(content, synthetic)["headline"]
    require_contextual_plan(synthetic)
    text = original
    for key in case["path"]:
        text = text[key]
    assert text == case["literal_model_text"]
    for witness in case["evidence"]:
        assert (
            witness["text"]
            == content["factual_basis"]["sources"][witness["source_ref"]]["passages"][
                witness["passage_index"]
            ]
        )
    assert case["expectation"] in {"accept", "reject"}
    assert "passed" not in case  # No fabricated semantic-review verdict.
    assert frozen([content, original, case]) == before


def test_missing_passage_witness_is_distinct_from_legal_typed_selectors():
    case = next(
        case
        for case in CORPUS["semantic_cases"]
        if case["id"] == "nonexistent_textual_passage"
    )
    assert "pasaje 5" in case["literal_model_text"]
    assert len(CORPUS["content"]["factual_basis"]["sources"][14]["passages"]) == 5
    assert CORPUS["semantic_cases"][-1]["expectation"] == "accept"
    assert CORPUS["semantic_cases"][-1]["id"] == "legitimate_conditional_consequence"
