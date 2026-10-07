import pytest

from support_agent.pii import find, iban_ok
from support_agent.redact import redact


@pytest.mark.parametrize("text, kind", [
    ("card 4111.1111.1111.1111", "card"),
    ("card 4111/1111/1111/1111", "card"),
    ("card 4111_1111_1111_1111", "card"),
    ("iban ua213223130000026007233566001", "iban"),
    ("IBAN: UA21-3223-1300-0002-6007-2335-6600-1", "iban"),
    ("IBAN DE89 3704 0044 0532 0130 00 for the refund", "iban"),
    ("call me at +380 67 123 45 67", "phone"),
    ("my phone is +1 (555) 123-4567", "phone"),
    ("passport AB123456", "passport"),
    ("login bob@example.com password hunter22", "secret"),
    ("Пароль от панели qwerty123", "secret"),
])
def test_detects(text, kind):
    assert kind in {f.kind for f in find(text)}


def test_iban_checksum():
    assert iban_ok("DE89 3704 0044 0532 0130 00") and not iban_ok("DE88 3704 0044 0532 0130 00")


def test_dashed_iban_is_masked_whole_not_half_read_as_a_card():
    assert redact("IBAN: UA21-3223-1300-0002-6007-2335-6600-1 thanks") == "IBAN: [iban] thanks"


@pytest.mark.parametrize("text", [
    "my sftp password is not working",
    "the world seed is 1234567890123456789",
    "server ip: 51.68.12.4:25565",
])
def test_ordinary_numbers_and_phrases_are_left_alone(text):
    assert find(text) == [] and redact(text) == text
