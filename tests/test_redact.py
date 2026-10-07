from support_agent.redact import redact


def test_redacts_card_email_iban_and_secret():
    text = ("card 4111 1111 1111 1111, mail ann@example.com, "
            "IBAN UA21 3223 1300 0002 6007 2335 6600 1, password: hunter22")
    out = redact(text)
    assert "[card ****1111]" in out and "[email]" in out and "[iban]" in out
    assert "hunter22" not in out and "ann@example.com" not in out and "4111 1111" not in out


def test_leaves_ordinary_text_alone():
    assert redact("Restart the server on port 25565") == "Restart the server on port 25565"
