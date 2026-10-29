"""Seed historical receiver fixtures without accepting fresh free-text proposals.

The public source-only builder supplies the original, pre-editorial namespace.
Only this test fixture replays archived prose through the tolerant receiver;
no production flag, provider adapter or acceptance rule is changed.
"""

import copy
from unittest.mock import patch

from sqlalchemy import select

from app.models import DailySummaryRevision, queries
from app.summaries import builder
from app.summaries.digest import apply_brief, apply_narrative, render_plain_text


def historical_summary(session, *, client_id, day, payload):
    """Persist synthetic archival prose using real merge/projection/export helpers.

    Capture before ordering, never feed an already compiled tail back into the
    receiver. The bootstrap's synthetic revision is replaced, not advertised as
    an accepted current-generation receipt. A callable payload receives frozen
    original-index content, not a provider prompt.
    """
    captured = []
    original_facts = []
    order = builder.apply_impact_order
    factual_basis = builder.build_factual_basis

    def capture_facts(content, mentions, **kwargs):
        original_facts.append(copy.deepcopy(content["noticias"]))
        return factual_basis(content, mentions, **kwargs)

    def capture(content):
        captured.append(copy.deepcopy(content))
        order(content)

    def unavailable(_prompt):
        raise RuntimeError("Historical fixture bootstrap: no provider execution")

    with (
        patch.object(builder, "apply_impact_order", side_effect=capture),
        patch.object(builder, "build_factual_basis", side_effect=capture_facts),
    ):
        row = builder.build_daily_summary(
            session, client_id=client_id, day=day, generate=unavailable
        )
    assert len(captured) == len(original_facts) == 1
    content = captured[0]
    # Historical receivers start from the original facts, not the current
    # renderer's source-fallback advisory placeholders.
    content["noticias"] = original_facts[0]
    content.pop("generation", None)
    content.pop("factual_basis", None)
    value = payload(content) if callable(payload) else payload
    assert apply_narrative(content, value) == []
    narrative = value.get("headline", row.narrative)
    content["headline"] = narrative
    content["tarjetas"] = builder.build_tarjetas(content["noticias"], content=content)
    for bucket in builder.BRIEF_BUCKETS:
        content["brief"][bucket] = []
    apply_brief(content, value)
    content["brief"]["headline"] = narrative
    builder.apply_impact_order(content)
    builder.compile_tail_cards(content)
    content["plain_text"] = render_plain_text(content, narrative)
    row = queries.upsert_daily_summary(
        session,
        client_id=client_id,
        day=day,
        content=content,
        narrative=narrative,
        mode="llm",
    )
    revision = session.scalars(
        select(DailySummaryRevision)
        .where(
            DailySummaryRevision.client_id == client_id,
            DailySummaryRevision.summary_date == day,
        )
        .order_by(DailySummaryRevision.seq.desc())
    ).first()
    assert revision is not None
    revision.narrative = narrative
    revision.mode = "llm"
    session.commit()
    session.refresh(row)
    return row
