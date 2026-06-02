import pytest

from helius_limiter.rotation import KeyRotator


def test_empty_keys_rejected():
    with pytest.raises(ValueError):
        KeyRotator([])


def test_rotate_advances_and_skips_exhausted():
    rotator = KeyRotator(["a", "b", "c"])
    assert rotator.current() == "a"
    assert rotator.rotate()
    assert rotator.current() == "b"
    assert rotator.live_count == 2
    assert rotator.rotate()
    assert rotator.current() == "c"
    assert rotator.live_count == 1
    assert not rotator.rotate()
    assert rotator.live_count == 0
