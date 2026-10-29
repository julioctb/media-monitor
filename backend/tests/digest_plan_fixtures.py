"""Compliant synthetic selectors for tests of the current generation protocol.

This is not a legacy-prose translator or an application acceptance bypass.
Selections are explicit; source indexes come from each original story scope.
"""

import json


def plan_completion(
    prompt,
    selections=(),
    *,
    headline_index=0,
    item_indexes=None,
    frame="visibility",
    action="verify_record",
):
    packet = json.loads(prompt)
    stories = {story["index"]: story for story in packet["stories"]}
    sources = {source["source_ref"]: source for source in packet["sources"]}
    picks = []
    for index, category in selections:
        if type(index) is not int or index not in stories:
            raise ValueError("Synthetic selection must name an original story index")
        picks.append(
            {"index": index, "categoria": category, "frame": frame, "action": action}
        )
    items = []
    for index in stories if item_indexes is None else item_indexes:
        if type(index) is not int or index not in stories:
            raise ValueError("Synthetic passage must name an original story index")
        available = [
            ref for ref in stories[index]["source_refs"] if sources[ref]["passages"]
        ]
        if available:
            items.append(
                {"index": index, "source_ref": available[0], "passage_index": 0}
            )
    if not stories:
        headline_index = None
    elif headline_index is not None and (
        type(headline_index) is not int or headline_index not in stories
    ):
        raise ValueError("Synthetic headline must name an original story index")
    return json.dumps(
        {
            "basis_fingerprint": packet["basis_fingerprint"],
            "headline_index": headline_index,
            "headline_frame": frame,
            "items": items,
            "seleccion": picks,
        },
        ensure_ascii=False,
    )
