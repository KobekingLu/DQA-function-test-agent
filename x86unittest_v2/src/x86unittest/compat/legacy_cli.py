from __future__ import annotations


def translate_legacy_args(args: list[str]) -> list[str]:
    if not args:
        return []
    command = args[0]
    if command == "-first":
        return ["doctor", "--profile", "fwa6083"]
    if command in {"-all", "-BAT"}:
        return ["run", "--profile", "fwa6083", "--output", "output/v2_runs"]
    if command == "-summary":
        return ["plan", "--profile", "fwa6083"]
    return []
