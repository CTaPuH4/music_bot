import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.tags import resolve_user_tags, resolve_single_tag

def run_tests():
    test_cases = [
        ("рок, поп, дип хаус", ["rock", "pop", "deep house"], []),
        ("synthwave, rock, hip-hop, lo-fi", ["synthwave", "rock", "hip hop", "lo-fi"], []),
        ("lofi, deep house, 80s", ["lo-fi", "deep house", "1980s"], []),
        ("#рок!, \"попса\", 'электроника', фонк", ["rock", "pop", "electronic", "phonk"], []),
        ("дарк эмбиент, мелодик рок, русский рок", ["dark ambient", "melodic rock", "russian rock"], []),
        ("хэвиметалл, ньювейв", ["heavy metal", "new wave"], []),
        ("хэви металл, хэвиметал", ["heavy metal"], []),
        ("синтвейв, джаз, несуществующийжанр123", ["synthwave", "jazz"], ["несуществующийжанр123"]),
        ("  ", [], []),
    ]

    for raw, expected_valid, expected_invalid in test_cases:
        valid, invalid = resolve_user_tags(raw)
        print(f"INPUT: '{raw}'")
        print(f"  GOT VALID:   {valid}")
        print(f"  GOT INVALID: {invalid}")
        assert valid == expected_valid, f"Expected {expected_valid}, got {valid}"
        assert invalid == expected_invalid, f"Expected {expected_invalid}, got {invalid}"

    print("ALL TAG TESTS PASSED!")

if __name__ == "__main__":
    run_tests()
