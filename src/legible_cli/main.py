from __future__ import annotations

import sys

import typer

app = typer.Typer(
    name="lgbl",
    help="LegiblePy developer toolchain — linter, trace reader, and utilities.",
)


@app.callback()
def callback() -> None:
    pass


@app.command()
def lint(
    files: list[str] = typer.Argument(..., help="Python files to lint."),
    concept_package: str = typer.Option(
        "concepts", "--concept-package", "-p",
        help="Dotted module prefix for concept imports.",
    ),
    skip: list[str] = typer.Option(
        [], "--skip", "-s",
        help="Rule IDs to skip, e.g. R004.",
    ),
    format: str = typer.Option(
        "text", "--format", "-f",
        help="Output format (text or json).",
    ),
    strict: bool = typer.Option(
        False, "--strict",
        help="Exit 1 for warnings (R004) as well as errors.",
    ),
    no_colour: bool = typer.Option(
        False, "--no-colour", "-n",
        help="Disable ANSI colour in text output.",
    ),
) -> None:
    from legible.linter.cli import main as linter_main

    sys.argv = ["conceptlint"] + list(files)
    if concept_package != "concepts":
        sys.argv.extend(["--concept-package", concept_package])
    for r in skip:
        sys.argv.extend(["--skip", r])
    if format != "text":
        sys.argv.extend(["--format", format])
    if strict:
        sys.argv.append("--strict")
    if no_colour:
        sys.argv.append("--no-colour")
    linter_main()


@app.command()
def trace(
    flow_token: str = typer.Argument(
        None, help="Flow token to inspect (prefix matching supported).",
    ),
    db: str = typer.Option(
        "legible.db", "--db", "-d",
        help="Path to the SQLite database.",
    ),
    format: str = typer.Option(
        "tree", "--format", "-f",
        help="Output format (tree or json).",
    ),
    no_colour: bool = typer.Option(
        False, "--no-colour", "-n",
        help="Disable ANSI colour in tree output.",
    ),
    list_flows: bool = typer.Option(
        False, "--list", "-l",
        help="List all recorded flows in the database.",
    ),
) -> None:
    from legible.trace.cli import main as trace_main

    sys.argv = ["trace"]
    if list_flows:
        sys.argv.append("--list")
    if flow_token:
        sys.argv.append(flow_token)
    if db != "legible.db":
        sys.argv.extend(["--db", db])
    if format != "tree":
        sys.argv.extend(["--format", format])
    if no_colour:
        sys.argv.append("--no-colour")
    trace_main()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
