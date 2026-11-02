"""Compliant synthetic selectors for tests of the current generation protocol.

This is not a legacy-prose translator or an application acceptance bypass.
Selections are explicit; source indexes come from each original story scope.
"""

import copy
import json


def advisory_completion(prompt, selections=(), **options):
    """Explicit synthetic contextual plan; not proof of advisory quality."""
    packet = json.loads(prompt)
    plan = json.loads(plan_completion(prompt, selections, **options))
    selectors = {entry["index"]: entry for entry in plan["items"]}
    for story in packet["stories"]:
        index = story["index"]
        if index not in selectors:
            for choice in story["source_choices"]:
                if choice["passage_indices"]:
                    selectors[index] = {
                        "index": index,
                        "source_ref": choice["source_ref"],
                        "passage_index": choice["passage_indices"][0],
                    }
                    break

    def analysis(index):
        return {
            "premises": [copy.deepcopy(selectors[index])],
            "interpretation": "El asunto documentado puede abrir un espacio de interlocución institucional.",
            "consequence": "Si hay continuidad documentada, podría ampliarse la coordinación.",
            "attention": "Observar si se publican nuevas propuestas vinculadas al asunto.",
            "conditions": "No se presuponen acuerdos, respaldo público ni responsabilidades no documentadas.",
            "relevance": "La pertinencia depende de la relación documentada con el perfil monitoreado.",
        }

    if plan["headline_index"] is not None:
        plan["headline_analysis"] = analysis(plan["headline_index"])
    for pick in plan["seleccion"]:
        pick["analysis"] = analysis(pick["index"])
    return json.dumps(plan, ensure_ascii=False)


def review_completion(prompt):
    """A fake positive judge tests wiring, never actual semantic correctness."""
    packet = json.loads(prompt)
    return json.dumps(
        {
            "input_fingerprint": packet["input_fingerprint"],
            "passed": True,
            "checks": {key: True for key in packet["required_checks"]},
            "assessments": [
                {
                    "path": path,
                    "passed": True,
                    "reason": "Evaluación sintética del mecanismo.",
                }
                for path in packet["scope"]
            ],
        },
        ensure_ascii=False,
    )


def reviewed_factory(proposal):
    """Explicit injection for BOTH phases; physical request accounting stays zero."""

    def factory(effective, *, phase, budget, system_prompt, response_schema):
        return proposal if phase == "proposal" else review_completion

    return factory


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
