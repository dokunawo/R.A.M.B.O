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


def test_write_launchers_top_level(tmp_path):
    (tmp_path / "main.py").write_text("print('hi')", encoding="utf-8")
    written = b.write_launchers(tmp_path, tmp_path / "main.py")
    assert written == ["run.bat", "run.sh"]
    bat = (tmp_path / "run.bat").read_text()
    assert "main.py" in bat and "pause" in bat and 'cd /d "%~dp0"' in bat
    assert (tmp_path / "run.sh").exists()


def test_write_launchers_nested_entry_cd(tmp_path):
    (tmp_path / "app").mkdir()
    entry = tmp_path / "app" / "main.py"
    entry.write_text("print('hi')", encoding="utf-8")
    b.write_launchers(tmp_path, entry)
    bat = (tmp_path / "run.bat").read_text()
    assert r'cd /d "%~dp0\app"' in bat and "main.py" in bat
