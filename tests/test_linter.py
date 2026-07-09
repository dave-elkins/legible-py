from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap

from legible.linter.rules import LinterConfig, lint_file, lint_source

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
CLEAN = os.path.join(FIXTURES, "clean_concept.py")
BAD = os.path.join(FIXTURES, "bad_concept.py")
ROOT = os.path.join(os.path.dirname(__file__), "..")


def _rules(violations):
    return [v.rule for v in violations]


def _lint(source, **kwargs):
    config = LinterConfig(**kwargs) if kwargs else None
    return lint_source(textwrap.dedent(source), config=config)


class TestFixtures:

    def test_clean_concept_has_no_violations(self):
        v = lint_file(CLEAN)
        assert v == [], f"Expected no violations, got: {v}"

    def test_bad_concept_has_violations(self):
        v = lint_file(BAD)
        assert len(v) > 0

    def test_bad_concept_triggers_r001(self):
        v = lint_file(BAD)
        assert "R001" in _rules(v)

    def test_bad_concept_triggers_r002(self):
        v = lint_file(BAD)
        assert "R002" in _rules(v)

    def test_bad_concept_triggers_r003(self):
        v = lint_file(BAD)
        assert "R003" in _rules(v)

    def test_bad_concept_triggers_r004(self):
        v = lint_file(BAD)
        assert "R004" in _rules(v)

    def test_bad_concept_triggers_r005(self):
        v = lint_file(BAD)
        assert "R005" in _rules(v)


class TestR001:

    def test_import_concept_package(self):
        v = _lint("import concepts.order\n")
        assert any(v.rule == "R001" for v in v)

    def test_from_concept_package(self):
        v = _lint("from concepts.user import User\n")
        assert any(v.rule == "R001" for v in v)

    def test_stdlib_import_not_flagged(self):
        v = _lint("import uuid\nimport asyncio\nfrom dataclasses import dataclass\n")
        assert not any(v.rule == "R001" for v in v)

    def test_custom_concept_package(self):
        v = _lint(
            "import myapp.concepts.order\n",
            concept_package="myapp.concepts",
        )
        assert any(v.rule == "R001" for v in v)

    def test_partial_match_not_flagged(self):
        v = _lint("import conceptual.model\n")
        assert not any(v.rule == "R001" for v in v)

    def test_violation_contains_line_number(self):
        source = "import uuid\nfrom concepts.pet import Pet\n"
        v = _lint(source)
        r001 = [x for x in v if x.rule == "R001"]
        assert r001[0].line == 2


class TestR002:

    def test_annotation_with_imported_concept_type(self):
        source = """
            from concepts.user import UserRecord
            from dataclasses import dataclass

            @dataclass
            class PetState:
                owner: UserRecord
        """
        v = _lint(source)
        assert any(x.rule == "R002" for x in v)

    def test_optional_annotation_flagged(self):
        source = """
            from concepts.user import UserRecord
            from typing import Optional
            from dataclasses import dataclass

            @dataclass
            class PetState:
                owner: Optional[UserRecord]
        """
        v = _lint(source)
        assert any(x.rule == "R002" for x in v)

    def test_str_annotation_not_flagged(self):
        source = """
            from dataclasses import dataclass

            @dataclass
            class PetState:
                owner_id: str
                name: str
        """
        v = _lint(source)
        assert not any(x.rule == "R002" for x in v)

    def test_no_concept_imports_means_no_r002(self):
        source = """
            from dataclasses import dataclass

            @dataclass
            class PetState:
                owner: dict
        """
        v = _lint(source)
        assert not any(x.rule == "R002" for x in v)


class TestR003:

    def test_async_fn_no_return(self):
        v = _lint("async def act(inputs: dict):\n    pass\n")
        assert any(x.rule == "R003" for x in v)

    def test_async_fn_explicit_none_annotation(self):
        v = _lint("async def act(inputs: dict) -> None:\n    pass\n")
        assert any(x.rule == "R003" for x in v)

    def test_async_fn_with_return_not_flagged(self):
        v = _lint('async def act(inputs: dict) -> dict:\n    return {"ok": True}\n')
        assert not any(x.rule == "R003" for x in v)

    def test_sync_fn_void_not_flagged(self):
        v = _lint("def helper(bindings: dict):\n    pass\n")
        assert not any(x.rule == "R003" for x in v)

    def test_r003_message_mentions_function_name(self):
        v = _lint("async def my_action(inputs: dict):\n    pass\n")
        r003 = [x for x in v if x.rule == "R003"]
        assert "my_action" in r003[0].message


class TestR004:

    def test_single_key_return_no_mutation(self):
        source = """
            async def get_name(inputs: dict) -> dict:
                return {"name": inputs["name"]}
        """
        v = _lint(source)
        assert any(x.rule == "R004" for x in v)

    def test_multi_key_return_not_flagged(self):
        source = """
            async def create(inputs: dict) -> dict:
                return {"id": "x", "name": inputs["name"]}
        """
        v = _lint(source)
        assert not any(x.rule == "R004" for x in v)

    def test_mutation_suppresses_r004(self):
        source = """
            _state = {}
            async def create(inputs: dict) -> dict:
                _state["key"] = inputs["name"]
                return {"id": "x"}
        """
        v = _lint(source)
        assert not any(x.rule == "R004" for x in v)

    def test_r004_is_warning_not_error(self):
        source = """
            async def get_name(inputs: dict) -> dict:
                return {"name": inputs["name"]}
        """
        v = _lint(source)
        r004 = [x for x in v if x.rule == "R004"]
        assert len(r004) == 1
        assert r004[0].rule == "R004"


class TestR005:

    def test_mutation_method_call(self):
        source = """
            cache = []
            def expand(bindings: dict) -> list:
                cache.append(bindings)
                return [bindings]
        """
        v = _lint(source)
        assert any(x.rule == "R005" for x in v)

    def test_each_mutation_method_flagged(self):
        methods = ["append", "extend", "update", "pop", "clear",
                   "add", "discard", "remove", "insert"]
        for method in methods:
            source = f"""
                state = {{}}
                def expand(b):
                    state.{method}(b)
                    return [b]
            """
            v = _lint(source)
            assert any(x.rule == "R005" for x in v), (
                f".{method}() should trigger R005"
            )

    def test_subscript_assign_to_nonlocal(self):
        source = """
            registry = {}
            def expand(bindings: dict) -> list:
                registry["last"] = bindings
                return [bindings]
        """
        v = _lint(source)
        assert any(x.rule == "R005" for x in v)

    def test_local_subscript_assign_not_flagged(self):
        source = """
            def expand(bindings: dict) -> list:
                result = {}
                result["key"] = bindings["val"]
                return [result]
        """
        v = _lint(source)
        assert not any(x.rule == "R005" for x in v)

    def test_nested_async_await(self):
        source = """
            def expand(bindings: dict) -> list:
                async def _fetch():
                    await some_coroutine()
                return [bindings]
        """
        v = _lint(source)
        assert any(x.rule == "R005" for x in v)

    def test_pure_where_not_flagged(self):
        source = """
            def expand(bindings: dict) -> list:
                result = {**bindings, "extra": True}
                return [result]
        """
        v = _lint(source)
        assert not any(x.rule == "R005" for x in v)

    def test_async_fn_not_checked_by_r005(self):
        source = """
            cache = []
            async def act(inputs: dict) -> dict:
                cache.append(inputs)
                return {"ok": True}
        """
        v = _lint(source)
        assert not any(x.rule == "R005" for x in v)


class TestConfig:

    def test_skip_r004_suppresses_getter_warning(self):
        source = """
            async def get_name(inputs: dict) -> dict:
                return {"name": inputs["name"]}
        """
        v = _lint(source, skip_rules={"R004"})
        assert not any(x.rule == "R004" for x in v)

    def test_skip_multiple_rules(self):
        source = """
            import concepts.order
            async def act(inputs: dict):
                pass
        """
        v = _lint(source, skip_rules={"R001", "R003"})
        assert not any(x.rule in {"R001", "R003"} for x in v)

    def test_custom_concept_package_isolates_detection(self):
        source = "import concepts.order\n"
        v_default = _lint(source)
        assert any(x.rule == "R001" for x in v_default)
        v_custom = _lint(source, concept_package="myapp")
        assert not any(x.rule == "R001" for x in v_custom)

    def test_syntax_error_returns_single_violation(self):
        v = lint_source("def broken(\n", filename="broken.py")
        assert len(v) == 1
        assert v[0].rule == "SYNTAX"


class TestViolationFormat:

    def test_format_no_colour_contains_rule_and_message(self):
        v = _lint("import concepts.order\n")
        r001 = [x for x in v if x.rule == "R001"][0]
        text = r001.format(use_colour=False)
        assert "R001" in text
        assert "no-cross-concept-import" in text
        assert r001.message in text
        assert r001.suggestion in text

    def test_format_no_colour_no_ansi(self):
        v = _lint("import concepts.order\n")
        text = v[0].format(use_colour=False)
        assert "\033[" not in text

    def test_to_dict_json_serialisable(self):
        v = _lint("import concepts.order\n")
        d = v[0].to_dict()
        json.dumps(d)
        assert d["rule"] == "R001"
        assert "line" in d

    def test_violations_sorted_by_line(self):
        source = """
            import concepts.order
            import uuid

            async def act(inputs: dict):
                pass
        """
        v = _lint(source)
        lines = [x.line for x in v]
        assert lines == sorted(lines)


class TestCLI:

    def _run(self, *args):
        env = os.environ.copy()
        env["PYTHONPATH"] = os.path.join(ROOT, "src")

        return subprocess.run(
            [sys.executable, "-c", f"""
import sys
sys.path.insert(0, {os.path.join(ROOT, 'src')!r})
from legible.linter.cli import main
sys.argv = ['conceptlint'] + {list(args)!r}
try:
    main()
except SystemExit:
    pass
"""],
            capture_output=True, text=True,
            cwd=ROOT,
        )

    def test_clean_file_exits_zero(self):
        r = self._run(CLEAN, "--no-colour")
        assert "No violations" in r.stdout

    def test_bad_file_reports_violations(self):
        r = self._run(BAD, "--no-colour")
        assert "R001" in r.stdout or "R003" in r.stdout
