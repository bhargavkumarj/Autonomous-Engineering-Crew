"""Tests for the declarative crew configuration.

CrewAI's YAML config is its greatest strength and its sharpest edge. A task that
names an agent which does not exist, a `context` entry pointing at a task that
was renamed, or a `{placeholder}` with no matching input — all of these fail at
*runtime*, minutes into a paid run, after several agents have already worked.

These tests catch every one of them in a tenth of a second, and they need
neither CrewAI nor an API key: they read the YAML the same way CrewAI will.
"""

from __future__ import annotations

import string
from pathlib import Path

import pytest
import yaml

CONFIG_DIR = Path(__file__).resolve().parents[1] / "src" / "engineering_crew" / "config"

#: The inputs the CLI passes to kickoff(). Every placeholder in the task YAML has
#: to be one of these or the run dies on an interpolation error.
KICKOFF_INPUTS = {"requirements"}


@pytest.fixture(scope="module")
def agents() -> dict:
    return yaml.safe_load((CONFIG_DIR / "agents.yaml").read_text())


@pytest.fixture(scope="module")
def tasks() -> dict:
    return yaml.safe_load((CONFIG_DIR / "tasks.yaml").read_text())


def placeholders(text: str) -> set[str]:
    """The `{name}` fields in a template string."""
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


# --------------------------------------------------------------------- agents


def test_the_crew_is_the_four_expected_roles(agents: dict) -> None:
    assert set(agents) == {"engineering_lead", "backend_engineer", "frontend_engineer", "test_engineer"}


def test_every_agent_has_a_role_goal_backstory_and_model(agents: dict) -> None:
    for name, spec in agents.items():
        assert {"role", "goal", "backstory", "llm"} <= spec.keys(), name
        assert all(str(spec[field]).strip() for field in ("role", "goal", "backstory", "llm")), name


def test_the_lead_gets_the_strong_model_and_the_implementers_do_not(agents: dict) -> None:
    """A bad design wastes three downstream agents' work; a bad implementation is
    caught by the test engineer. That asymmetry is why the models differ."""
    lead = agents["engineering_lead"]["llm"]
    implementers = {
        agents[name]["llm"] for name in ("backend_engineer", "frontend_engineer", "test_engineer")
    }
    assert lead not in implementers
    assert len(implementers) == 1, "the three implementers should share one cheaper model"


def test_the_stdlib_only_constraint_is_stated_to_the_agents_that_need_it(agents: dict) -> None:
    """The sandbox has only gradio installed, so backend and test code must be
    stdlib. Saying so in the goal is what stops an agent importing pytest."""
    for name in ("backend_engineer", "test_engineer"):
        goal = agents[name]["goal"].lower()
        assert "standard library" in goal or "stdlib" in goal, name


# ---------------------------------------------------------------------- tasks


def test_the_pipeline_is_the_four_expected_tasks(tasks: dict) -> None:
    assert set(tasks) == {"design_task", "code_task", "frontend_task", "test_task"}


def test_every_task_names_an_agent_that_exists(tasks: dict, agents: dict) -> None:
    """The classic CrewAI failure: rename an agent, forget a task that names it."""
    for name, spec in tasks.items():
        assert "agent" in spec, name
        assert spec["agent"] in agents, f"{name} names unknown agent {spec['agent']!r}"


def test_every_task_has_a_description_and_expected_output(tasks: dict) -> None:
    for name, spec in tasks.items():
        assert spec.get("description", "").strip(), name
        assert spec.get("expected_output", "").strip(), name


def test_every_context_reference_points_at_a_real_task(tasks: dict) -> None:
    for name, spec in tasks.items():
        for dependency in spec.get("context", []):
            assert dependency in tasks, f"{name} depends on unknown task {dependency!r}"


def test_no_task_depends_on_itself_or_on_a_later_task(tasks: dict) -> None:
    """The crew is sequential and runs in declaration order, so a dependency on a
    task that has not run yet would silently pass empty context."""
    order = list(tasks)
    for position, name in enumerate(order):
        for dependency in tasks[name].get("context", []):
            assert order.index(dependency) < position, f"{name} depends on later task {dependency}"


def test_every_placeholder_is_supplied_at_kickoff(tasks: dict) -> None:
    for name, spec in tasks.items():
        for field in ("description", "expected_output"):
            unknown = placeholders(spec.get(field, "")) - KICKOFF_INPUTS
            assert not unknown, f"{name}.{field} uses unsupplied placeholder(s): {unknown}"


def test_the_requirement_reaches_the_agents_that_need_it(tasks: dict) -> None:
    """Design, backend and frontend all work from the original requirement. The
    test engineer works from the code, so it deliberately does not."""
    for name in ("design_task", "code_task", "frontend_task"):
        assert "requirements" in placeholders(tasks[name]["description"]), name


def test_written_output_stays_inside_the_sandbox(tasks: dict) -> None:
    """An output_file escaping the sandbox would let agent output land in the repo."""
    for name, spec in tasks.items():
        output = spec.get("output_file")
        if output:
            assert output.startswith("sandbox/"), f"{name} writes outside the sandbox: {output}"
            assert ".." not in output, name


def test_the_test_task_is_told_to_keep_going_until_the_tests_pass(tasks: dict) -> None:
    """This one instruction is what turns the test engineer into a self-correcting
    loop with a real oracle rather than a one-shot test writer."""
    description = tasks["test_task"]["description"].lower()
    assert "until all unit tests pass" in description or "until they pass" in description


def test_the_validation_script_is_told_not_to_launch(tasks: dict) -> None:
    """Calling .launch() in a sandbox script blocks until the execution timeout,
    burning five minutes and reporting a failure that is not one."""
    assert "must NOT call `.launch()`" in tasks["frontend_task"]["description"]
