"""Tests for the requirement catalogue.

A requirement is the crew's entire input, and its shape determines whether the
run succeeds. The property that matters: a requirement must state hard,
checkable rules. "Make it user-friendly" produces a crew that argues with
itself; "prevent withdrawing below zero" produces a test that either passes or
does not.
"""

from __future__ import annotations

import pytest

from engineering_crew.requirements import CATALOGUE, DEFAULT

#: Words that signal a rule a test engineer can actually assert on.
CONSTRAINT_WORDS = ("prevent", "reject", "should not", "must not", "no more than", "only")


def test_the_default_is_in_the_catalogue() -> None:
    assert DEFAULT in CATALOGUE


@pytest.mark.parametrize("name", sorted(CATALOGUE))
def test_every_requirement_is_substantial(name: str) -> None:
    text = CATALOGUE[name].strip()
    assert len(text) > 300, f"{name} is too thin to design from"
    assert len(text.splitlines()) >= 5, name


@pytest.mark.parametrize("name", sorted(CATALOGUE))
def test_every_requirement_states_checkable_constraints(name: str) -> None:
    """Without hard rules there is nothing for the test engineer to verify."""
    text = CATALOGUE[name].lower()
    assert any(word in text for word in CONSTRAINT_WORDS), f"{name} has no assertable constraint"


@pytest.mark.parametrize("name", sorted(CATALOGUE))
def test_no_requirement_carries_a_stray_placeholder(name: str) -> None:
    """A `{}` in the requirement text would be interpolated by CrewAI and blow up."""
    text = CATALOGUE[name]
    assert "{" not in text and "}" not in text, name


def test_requirements_are_distinct_domains() -> None:
    """Three genuinely different problems, so a good run is not a memorised one."""
    assert len({text.strip() for text in CATALOGUE.values()}) == len(CATALOGUE)
