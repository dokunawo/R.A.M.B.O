"""Tests for dev_agent.playbooks — selection + injection into the coding agent."""

import pytest

from dev_agent import playbooks as pb
from dev_agent.coding_agent import CodingAgent


def test_available_lists_the_three():
    avail = pb.available()
    assert "test-driven-development" in avail
    assert "systematic-debugging" in avail
    assert "verification-before-completion" in avail


def test_default_loads_all(monkeypatch):
    monkeypatch.delenv("RAMBO_DEV_PLAYBOOKS", raising=False)
    text = pb.load_playbooks()
    assert "Engineering playbooks" in text
    assert "Test-Driven Development" in text
    assert "Systematic Debugging" in text
    assert "Verification Before Completion" in text


def test_off_disables(monkeypatch):
    monkeypatch.setenv("RAMBO_DEV_PLAYBOOKS", "off")
    assert pb.load_playbooks() == ""


def test_subset_selection(monkeypatch):
    monkeypatch.setenv("RAMBO_DEV_PLAYBOOKS", "systematic-debugging")
    text = pb.load_playbooks()
    assert "Systematic Debugging" in text
    assert "Test-Driven Development" not in text


def test_unknown_name_ignored():
    text = pb.load_playbooks(["does-not-exist", "test-driven-development"])
    assert "Test-Driven Development" in text


def test_agent_system_includes_playbooks(monkeypatch):
    monkeypatch.delenv("RAMBO_DEV_PLAYBOOKS", raising=False)
    agent = CodingAgent(llm_client=None, worktree_path=".", personality_text="VOICE")
    assert "VOICE" in agent._system
    assert "Self-modification contract" in agent._system
    assert "Engineering playbooks" in agent._system


def test_agent_playbooks_can_be_disabled():
    agent = CodingAgent(llm_client=None, worktree_path=".", playbooks="")
    assert "Engineering playbooks" not in agent._system
