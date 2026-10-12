"""
Keep user-facing text out of the code.

Everything a user reads has to come from the translations (en.json), so it can be translated
and so core's rules hold. These tests read the integration's source and fail on text written
in the code, and on translation keys the code uses that en.json doesn't have.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

INTEGRATION = Path(__file__).parent.parent / "custom_components" / "homeconnect_ws"
EN = json.loads((INTEGRATION / "translations" / "en.json").read_text(encoding="utf-8"))

# Errors Home Assistant shows to the user; each takes translation_domain/translation_key.
USER_ERRORS = {
    "HomeAssistantError",
    "ServiceValidationError",
    "ConfigEntryError",
    "ConfigEntryNotReady",
    "ConfigEntryAuthFailed",
    "UpdateFailed",
}


def _source_files() -> list[Path]:
    return sorted(INTEGRATION.rglob("*.py"))


def _trees() -> list[tuple[Path, ast.AST]]:
    return [(path, ast.parse(path.read_text(encoding="utf-8"))) for path in _source_files()]


def _where(path: Path, node: ast.AST) -> str:
    return f"{path.relative_to(INTEGRATION)}:{getattr(node, 'lineno', '?')}"


def _name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    return next((kw.value for kw in call.keywords if kw.arg == name), None)


def _literals(node: ast.expr | None) -> list[str] | None:
    """Return the string values an argument can have, or None when it isn't literal."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.IfExp):
        body, orelse = _literals(node.body), _literals(node.orelse)
        if body is not None and orelse is not None:
            return body + orelse
    return None


def _calls(name: str) -> list[tuple[Path, ast.Call]]:
    return [
        (path, node)
        for path, tree in _trees()
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _name(node.func) == name
    ]


def _translated(*keys: str) -> Any:
    node: Any = EN
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def test_user_errors_are_translated() -> None:
    """Errors shown to the user carry a translation_key that en.json has, and no text."""
    problems = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call)):
                continue
            call = node.exc
            if _name(call.func) not in USER_ERRORS:
                continue
            if call.args:
                problems.append(f"{_where(path, call)}: message text instead of translation_key")
                continue
            key_arg = _keyword(call, "translation_key")
            if key_arg is None:
                problems.append(f"{_where(path, call)}: no translation_key")
                continue
            # A key passed in from elsewhere (a helper's argument) can't be checked here.
            keys = _literals(key_arg) or []
            problems.extend(
                f"{_where(path, call)}: exceptions.{key} missing from en.json"
                for key in keys
                if _translated("exceptions", key, "message") is None
            )
    assert problems == []


def _in_a_flow(section: str, key: str) -> bool:
    return any(_translated(flow, section, key) for flow in ("config", "options"))


def test_abort_reasons_are_translated() -> None:
    """Every abort reason the flows use exists in en.json."""
    problems = [
        f"{_where(path, call)}: abort reason {key} missing from en.json"
        for path, call in _calls("async_abort")
        for key in _literals(_keyword(call, "reason")) or []
        if not _in_a_flow("abort", key)
    ]
    assert problems == []


def test_steps_and_menus_are_translated() -> None:
    """Every form and menu step, and every menu option, exists in en.json."""
    problems = [
        f"{_where(path, call)}: step {key} missing from en.json"
        for name in ("async_show_form", "async_show_menu")
        for path, call in _calls(name)
        for key in _literals(_keyword(call, "step_id")) or []
        if not _in_a_flow("step", key)
    ]
    for path, call in _calls("async_show_menu"):
        step = (_literals(_keyword(call, "step_id")) or [None])[0]
        options = _keyword(call, "menu_options")
        if step is None or not isinstance(options, ast.List):
            continue
        problems.extend(
            f"{_where(path, call)}: menu option {key[0]} missing from en.json"
            for option in options.elts
            if (key := _literals(option))
            and _translated("config", "step", step, "menu_options", key[0]) is None
        )
    assert problems == []


def test_form_errors_are_translated() -> None:
    """Every errors["base"] value the flows set exists in en.json."""
    problems = [
        f"{_where(path, node)}: error {key} missing from en.json"
        for path, tree in _trees()
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and isinstance(target := node.targets[0], ast.Subscript)
        and _literals(target.slice) == ["base"]
        for key in _literals(node.value) or []
        if _translated("config", "error", key) is None
    ]
    assert problems == []


@pytest.mark.parametrize(
    ("call", "argument", "why"),
    [
        ("SelectOptionDict", "label", "selector labels go in selector.<key>.options"),
        (
            "HCSensorEntityDescription",
            "native_unit_of_measurement",
            "custom units go in the entity's unit_of_measurement",
        ),
        ("HCNumberEntityDescription", "native_unit_of_measurement", "same as sensors"),
    ],
)
def test_no_text_in_the_code(call: str, argument: str, why: str) -> None:
    """Labels and units written as text in the code instead of the translations."""
    problems = [
        f"{_where(path, node)}: {call}({argument}='{_literals(value)[0]}'), {why}"
        for path, node in _calls(call)
        if (value := _keyword(node, argument)) is not None and _literals(value) is not None
    ]
    assert problems == []


def test_no_persistent_notifications() -> None:
    """Notifications built from text in the code can't be translated; use the flow's dialog."""
    problems = [
        _where(path, node)
        for path, tree in _trees()
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and node.value == "persistent_notification"
    ]
    assert problems == []
