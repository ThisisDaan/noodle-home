import os
import tempfile

os.environ.setdefault("NOODLE_DATA", tempfile.mkdtemp())

from noodle import updates  # noqa: E402


def test_newer_compares_numbers_not_text():
    assert updates.newer("0.10.0", "0.9.0")
    assert updates.newer("1.0.0", "0.9.9")
    assert not updates.newer("0.1.0", "0.1.0")
    assert not updates.newer("0.1.0", "0.2.0")
    assert not updates.newer("garbage", "0.1.0")
