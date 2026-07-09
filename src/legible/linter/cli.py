from __future__ import annotations

import argparse
import json
import os
import sys

from .rules import LinterConfig, Violation, lint_file

_WARNING_RULES = {"R004"}


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="conceptlint",
        description="Static analysis for LegiblePy concept modules.",
    )
    parser.add_argument(
        "files",
        nargs="+",
        metavar="FILE",
        help="Python files to lint.",
    )
    parser.add_argument(
        "--concept-package",
        default="concepts",
        metavar="PKG",
        dest="concept_package",
        help="Dotted module prefix for concept imports (default: 'concepts').",
    )
    parser.add_argument(
        "--skip",
        nargs="+",
        default=[],
        metavar="RULE",
        help="Rule IDs to skip, e.g. --skip R004.",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        dest="fmt",
        help="Output format (default: text).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 for warnings (R004) as well as errors.",
    )
    parser.add_argument(
        "--no-colour",
        action="store_true",
        help="Disable ANSI colour in text output.",
    )

    args = parser.parse_args()

    config = LinterConfig(
        concept_package=args.concept_package,
        skip_rules=set(r.upper() for r in args.skip),
    )

    all_violations: list[Violation] = []
    missing: list[str] = []

    for path in args.files:
        if not os.path.isfile(path):
            missing.append(path)
            continue
        all_violations.extend(lint_file(path, config=config))

    if missing:
        for p in missing:
            print(f"conceptlint: file not found: {p}", file=sys.stderr)
        sys.exit(2)

    if args.fmt == "json":
        print(json.dumps(
            [v.to_dict() for v in all_violations],
            indent=2,
        ))
    else:
        use_colour = not args.no_colour and sys.stdout.isatty()
        if all_violations:
            for v in all_violations:
                print(v.format(use_colour=use_colour))
                print()
        else:
            msg = f"\u2713 No violations found in {len(args.files)} file(s)."
            if use_colour:
                msg = f"\033[32m{msg}\033[0m"
            print(msg)

    errors = [v for v in all_violations if v.rule not in _WARNING_RULES]
    warnings = [v for v in all_violations if v.rule in _WARNING_RULES]

    if errors:
        sys.exit(1)
    if warnings and args.strict:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
