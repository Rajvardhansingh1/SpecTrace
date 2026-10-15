from dataclasses import dataclass


@dataclass(frozen=True)
class Limits:
    max_files: int = 200
    max_file_bytes: int = 1_000_000
    max_total_bytes: int = 5_000_000
    max_entities: int = 20_000
    max_yaml_nodes: int = 200_000
    max_yaml_depth: int = 50
