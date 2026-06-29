from speech_normalize import normalize_for_speech


def test_units_expanded():
    assert normalize_for_speech("wind 10 mph") == "wind 10 miles per hour"
    assert normalize_for_speech("75°F today") == "75 degrees Fahrenheit today"
    assert normalize_for_speech("turn 30°") == "turn 30 degrees"
    assert normalize_for_speech("weighs 12 lbs") == "weighs 12 pounds"


def test_symbols_expanded():
    assert normalize_for_speech("up 5%") == "up 5 percent"
    assert normalize_for_speech("PIT vs CIN") == "PIT versus CIN"
    assert normalize_for_speech("8+ strikeouts") == "8 plus strikeouts"
    assert normalize_for_speech("bacon & eggs") == "bacon and eggs"
    assert normalize_for_speech("meet @ noon") == "meet at noon"


def test_baseball_acronyms_expanded():
    assert normalize_for_speech("vs 3.80 ERA") == "versus 3.80 earned run average"
    assert normalize_for_speech("2 HR and 5 RBI") == "2 home runs and 5 runs batted in"
    assert normalize_for_speech("logged 6 IP") == "logged 6 innings pitched"


def test_team_codes_and_bare_k_untouched():
    # team codes must NOT be expanded or mangled
    assert normalize_for_speech("NYY at BOS") == "NYY at BOS"
    assert "strikeout" not in normalize_for_speech("Mr. K stepped up")  # bare K left alone
    assert normalize_for_speech("Mr. K stepped up") == "Mr. K stepped up"


def test_does_not_mangle_ordinary_words():
    # 'in' is a real word — must not become 'inches'; 'so' lowercase must not become strikeouts
    assert normalize_for_speech("the runner is in scoring position") == "the runner is in scoring position"
    assert normalize_for_speech("so he swings") == "so he swings"


def test_realistic_board_line():
    line = "10 mph, In From LF · 3.80 ERA · 75°F"
    out = normalize_for_speech(line)
    assert "miles per hour" in out
    assert "earned run average" in out
    assert "degrees Fahrenheit" in out
    assert "mph" not in out and "ERA" not in out


def test_safe_on_empty_and_clean():
    assert normalize_for_speech("") == ""
    assert normalize_for_speech(None) is None
    assert normalize_for_speech("a clean sentence.") == "a clean sentence."
