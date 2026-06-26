from brains.ev.parks import hr_factor, PARK_HR_FACTOR

def test_known_hitter_park_above_neutral():
    assert hr_factor("COL") > 1.0          # Coors

def test_unknown_defaults_neutral():
    assert hr_factor("ZZZ") == 1.0

def test_case_insensitive_and_table_size():
    assert hr_factor("col") == hr_factor("COL")
    assert len(PARK_HR_FACTOR) == 30
