from app.core.graph import Graph, build_graph
from app.core.limits import Limits
from app.core.parsers.markdown import parse_markdown
from app.core.parsers.openapi import parse_openapi


def graph_of(files: dict[str, str]) -> Graph:
    limits = Limits()
    results = []
    for name, text in sorted(files.items()):
        if name.endswith((".yaml", ".yml", ".json")):
            results.append(parse_openapi(name, text, limits))
        else:
            results.append(parse_markdown(name, text, limits))
    return build_graph(results)
