from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import List, Optional, Set


@dataclass
class Violation:
    rule: str
    name: str
    filename: str
    line: int
    col: int
    message: str
    suggestion: str

    def format(self, use_colour: bool = True) -> str:
        loc = f"{self.filename}:{self.line}:{self.col}"
        rule_tag = f"[{self.rule} {self.name}]"
        if use_colour:
            loc = f"\033[36m{loc}\033[0m"
            rule_tag = f"\033[33m{rule_tag}\033[0m"
        lines = [
            f"{loc}  {rule_tag}",
            f"  {self.message}",
            f"  \u2192 {self.suggestion}",
        ]
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "rule": self.rule,
            "name": self.name,
            "filename": self.filename,
            "line": self.line,
            "col": self.col,
            "message": self.message,
            "suggestion": self.suggestion,
        }


@dataclass
class LinterConfig:
    concept_package: str = "concepts"
    mutation_methods: Set[str] = field(default_factory=lambda: {
        "append", "extend", "insert", "remove", "pop", "clear",
        "update", "add", "discard", "setdefault", "setattr",
    })
    skip_rules: Set[str] = field(default_factory=set)


def _is_concept_import(node: ast.stmt, prefix: str) -> bool:
    if isinstance(node, ast.Import):
        return any(
            alias.name == prefix or alias.name.startswith(prefix + ".")
            for alias in node.names
        )
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        return module == prefix or module.startswith(prefix + ".")
    return False


def _imported_concept_names(tree: ast.Module, prefix: str) -> Set[str]:
    names: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == prefix or module.startswith(prefix + "."):
                for alias in node.names:
                    names.add(alias.asname or alias.name)
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == prefix or alias.name.startswith(prefix + "."):
                    names.add(alias.asname or alias.name.split(".")[-1])
    return names


def _has_state_mutation(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for node in ast.walk(func):
        if node is func:
            continue
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, (ast.Subscript, ast.Attribute)):
                    return True
        if isinstance(node, ast.AugAssign):
            return True
        if isinstance(node, ast.AnnAssign) and node.value is not None:
            if isinstance(node.target, ast.Attribute):
                return True
    return False


def _return_key_count(func: ast.AsyncFunctionDef) -> Optional[int]:
    for node in ast.walk(func):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
            return len(node.value.keys)
    return None


def _contains_nested_await(func: ast.FunctionDef) -> bool:
    for node in ast.walk(func):
        if node is func:
            continue
        if isinstance(node, ast.AsyncFunctionDef):
            if any(isinstance(n, ast.Await) for n in ast.walk(node)):
                return True
    return False


def _contains_mutation_call(
    func: ast.FunctionDef, mutation_methods: Set[str]
) -> Optional[ast.Call]:
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in mutation_methods
            ):
                return node
    return None


def _contains_subscript_assign(func: ast.FunctionDef) -> bool:
    local_names: Set[str] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    local_names.add(target.id)

    for node in ast.walk(func):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Subscript):
                    if isinstance(target.value, ast.Name):
                        if target.value.id not in local_names:
                            return True
    return False


def check_r001(
    tree: ast.Module,
    source_lines: List[str],
    filename: str,
    config: LinterConfig,
) -> List[Violation]:
    violations = []
    prefix = config.concept_package
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if not _is_concept_import(node, prefix):
            continue
        if isinstance(node, ast.ImportFrom):
            ref = f"from {node.module} import ..."
        else:
            ref = f"import {node.names[0].name}"
        violations.append(Violation(
            rule="R001",
            name="no-cross-concept-import",
            filename=filename,
            line=node.lineno,
            col=node.col_offset + 1,
            message=f"Concept imports another concept package: `{ref}`",
            suggestion=(
                "Concepts must not depend on each other. "
                "Move coordination into a sync rule in the sync layer."
            ),
        ))
    return violations


def check_r002(
    tree: ast.Module,
    source_lines: List[str],
    filename: str,
    config: LinterConfig,
) -> List[Violation]:
    violations = []
    concept_names = _imported_concept_names(tree, config.concept_package)
    if not concept_names:
        return violations

    for node in ast.walk(tree):
        if not isinstance(node, ast.AnnAssign):
            continue
        ann = node.annotation
        if isinstance(ann, ast.Name) and ann.id in concept_names:
            violations.append(Violation(
                rule="R002",
                name="no-named-foreign-reference",
                filename=filename,
                line=node.lineno,
                col=node.col_offset + 1,
                message=(
                    f"State annotation uses a foreign concept type `{ann.id}`. "
                    "This couples concepts at the schema level."
                ),
                suggestion=(
                    f"Replace `{ann.id}` with `str` and store the referenced "
                    "entity's id as an uninterpreted atom (UUID string)."
                ),
            ))
        if isinstance(ann, ast.Subscript):
            inner = ann.slice
            if isinstance(inner, ast.Name) and inner.id in concept_names:
                violations.append(Violation(
                    rule="R002",
                    name="no-named-foreign-reference",
                    filename=filename,
                    line=node.lineno,
                    col=node.col_offset + 1,
                    message=(
                        f"State annotation wraps a foreign concept type `{inner.id}`. "
                        "This couples concepts at the schema level."
                    ),
                    suggestion=(
                        "Replace with `str` (UUID). "
                        "Use uninterpreted atoms for cross-concept references."
                    ),
                ))
    return violations


def check_r003(
    tree: ast.Module,
    source_lines: List[str],
    filename: str,
    config: LinterConfig,
) -> List[Violation]:
    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue

        if (
            node.returns is not None
            and isinstance(node.returns, ast.Constant)
            and node.returns.value is None
        ):
            violations.append(Violation(
                rule="R003",
                name="action-returns-void",
                filename=filename,
                line=node.lineno,
                col=node.col_offset + 1,
                message=f"Async action `{node.name}` is annotated `-> None`.",
                suggestion=(
                    "Actions must return a dict so the engine can match their "
                    "outputs in a `when` clause. Return at least `{}`."
                ),
            ))
            continue

        has_value_return = any(
            isinstance(n, ast.Return) and n.value is not None
            for n in ast.walk(node)
        )
        if not has_value_return:
            violations.append(Violation(
                rule="R003",
                name="action-returns-void",
                filename=filename,
                line=node.lineno,
                col=node.col_offset + 1,
                message=f"Async action `{node.name}` has no return statement.",
                suggestion=(
                    "Actions must return a dict. "
                    "The engine matches action outputs in `when` clauses; "
                    "a void action is invisible to the sync layer."
                ),
            ))
    return violations


def check_r004(
    tree: ast.Module,
    source_lines: List[str],
    filename: str,
    config: LinterConfig,
) -> List[Violation]:
    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        if _has_state_mutation(node):
            continue
        key_count = _return_key_count(node)
        if key_count is None or key_count != 1:
            continue
        violations.append(Violation(
            rule="R004",
            name="getter-smell",
            filename=filename,
            line=node.lineno,
            col=node.col_offset + 1,
            message=(
                f"Async action `{node.name}` returns a single value "
                "and has no apparent state mutation — looks like a getter."
            ),
            suggestion=(
                "Pure reads don't need to be actions. "
                "Consider moving this query into a sync rule's `where` clause, "
                "or confirm it represents a meaningful user-facing event."
            ),
        ))
    return violations


def check_r005(
    tree: ast.Module,
    source_lines: List[str],
    filename: str,
    config: LinterConfig,
) -> List[Violation]:
    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue

        if _contains_nested_await(node):
            violations.append(Violation(
                rule="R005",
                name="where-has-side-effects",
                filename=filename,
                line=node.lineno,
                col=node.col_offset + 1,
                message=(
                    f"`{node.name}` contains a nested async function with `await`. "
                    "A `where` clause must be a pure read."
                ),
                suggestion=(
                    "Move async operations into a concept action and react to "
                    "its completion in a `then` clause instead."
                ),
            ))
            continue

        bad_call = _contains_mutation_call(node, config.mutation_methods)
        if bad_call is not None:
            method = bad_call.func.attr
            violations.append(Violation(
                rule="R005",
                name="where-has-side-effects",
                filename=filename,
                line=bad_call.lineno,
                col=bad_call.col_offset + 1,
                message=(
                    f"`{node.name}` calls `.{method}()` — a known mutation method. "
                    "A `where` clause must be a pure read."
                ),
                suggestion=(
                    "Remove side effects from `where` clauses. "
                    "Use `then` to invoke actions that produce state changes."
                ),
            ))
            continue

        if _contains_subscript_assign(node):
            violations.append(Violation(
                rule="R005",
                name="where-has-side-effects",
                filename=filename,
                line=node.lineno,
                col=node.col_offset + 1,
                message=(
                    f"`{node.name}` assigns to a subscript of a non-local variable. "
                    "A `where` clause must not mutate external state."
                ),
                suggestion=(
                    "Only read and bind values in `where` clauses. "
                    "State mutations belong in concept actions."
                ),
            ))

    return violations


ALL_RULES = [check_r001, check_r002, check_r003, check_r004, check_r005]


def lint_source(
    source: str,
    filename: str = "<string>",
    config: Optional[LinterConfig] = None,
) -> List[Violation]:
    if config is None:
        config = LinterConfig()

    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as e:
        return [Violation(
            rule="SYNTAX",
            name="syntax-error",
            filename=filename,
            line=e.lineno or 0,
            col=e.offset or 0,
            message=f"Syntax error: {e.msg}",
            suggestion="Fix the syntax error before running the linter.",
        )]

    source_lines = source.splitlines()
    violations: List[Violation] = []

    for rule_fn in ALL_RULES:
        rule_id = rule_fn.__name__.replace("check_", "").upper()
        if rule_id in config.skip_rules:
            continue
        violations.extend(rule_fn(tree, source_lines, filename, config))

    violations.sort(key=lambda v: (v.line, v.col, v.rule))
    return violations


def lint_file(
    path: str,
    config: Optional[LinterConfig] = None,
) -> List[Violation]:
    with open(path, encoding="utf-8") as f:
        source = f.read()
    return lint_source(source, filename=path, config=config)
