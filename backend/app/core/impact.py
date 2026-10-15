from collections import defaultdict
from math import prod

from app.core.models import Change, Classification, Edge, Impact, Label


def find_impacts(
    change: Change,
    edges_a: list[Edge],
    edges_b: list[Edge],
    max_depth: int = 3,
    max_expansions: int = 20_000,
) -> list[Impact]:
    merged: dict[tuple[str, str, str], Edge] = {}
    for e in [*edges_a, *edges_b]:
        merged[(e.source_key, e.target_key, e.relation)] = e
    incoming: dict[str, list[Edge]] = defaultdict(list)
    for e in merged.values():
        incoming[e.target_key].append(e)

    best: dict[str, tuple[tuple, tuple[Edge, ...]]] = {}
    stack: list[tuple[str, tuple[Edge, ...], frozenset[str]]] = [
        (change.key, (), frozenset({change.key}))
    ]
    expansions = 0
    while stack:
        node, path, seen = stack.pop()
        if len(path) >= max_depth:
            continue
        for e in incoming.get(node, []):
            if e.source_key in seen:
                continue
            expansions += 1
            if expansions > max_expansions:
                stack.clear()
                break
            new_path = path + (e,)
            score = _score(new_path)
            if e.source_key not in best or score > best[e.source_key][0]:
                best[e.source_key] = (score, new_path)
            stack.append((e.source_key, new_path, seen | {e.source_key}))

    impacts = [_impact(change, key, path) for key, (_, path) in best.items()]
    impacts.sort(key=lambda i: (i.certainty is not Label.CONFIRMED, -i.confidence, i.impacted_key))
    return impacts


def _score(path: tuple[Edge, ...]) -> tuple:
    confirmed = all(e.label is Label.CONFIRMED for e in path)
    return (confirmed, prod(e.confidence for e in path), -len(path))


def _impact(change: Change, impacted_key: str, path: tuple[Edge, ...]) -> Impact:
    certainty = (
        Label.CONFIRMED if all(e.label is Label.CONFIRMED for e in path) else Label.INFERRED
    )
    hops = " -> ".join(f"{e.source_key} {e.relation} {e.target_key}" for e in reversed(path))
    return Impact(
        change_key=change.key,
        impacted_key=impacted_key,
        certainty=certainty,
        confidence=round(prod(e.confidence for e in path), 4),
        path=list(path),
        confirmed_breaking=(
            change.classification is Classification.BREAKING and certainty is Label.CONFIRMED
        ),
        summary=f"[{certainty.value}] {impacted_key} depends on {change.key} via: {hops}",
    )
