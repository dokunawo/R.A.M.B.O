"""Build folder naming — short, human slugs from a request."""
from dev_agent import builds as b


def test_heuristic_name_strips_filler():
    assert b._heuristic_name("build me a calculator app from scratch and place it") == "Calculator"
    assert b._heuristic_name("build a snake game simulator") == "Snake Game Simulator"
    assert b._heuristic_name("make me a pomodoro timer tool") == "Pomodoro Timer"


def test_slugify_from_name():
    assert b.slugify(b._heuristic_name("build me a calculator app")) == "calculator"
    assert b.slugify("Snake Game") == "snake-game"
    assert b.slugify("") == "build"
