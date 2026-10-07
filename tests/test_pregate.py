import pytest

from support_agent.models import Customer, Ticket
from support_agent.pregate import check, luhn_ok


def gate(text, vip=False):
    return check(Ticket(id="t", text=text, customer=Customer(vip=vip)))


def test_luhn():
    assert luhn_ok("4111111111111111")
    assert not luhn_ok("4111111111111112")


@pytest.mark.parametrize("text", [
    "My card 4111 1111 1111 1111 was charged twice",
    "IBAN UA21 3223 1300 0002 6007 2335 6600 1 for the refund",
    "my password is Hunter22, please log in and fix it",
    "мій пароль: qwerty123",
])
def test_personal_data(text):
    result = gate(text)
    assert result.reason == "personal_data"
    assert "4111 1111 1111 1111" not in (result.evidence or "")  # evidence is redacted


def test_order_number_that_fails_luhn_is_not_a_card():
    assert gate("Order 1234 5678 9012 3456 shows the wrong slot count") is None


@pytest.mark.parametrize("text", [
    "I want a refund for last month",
    "Why was I charged twice?",
    "Please send the invoice for September",
    "Хочу повернення коштів",
    "Верните деньги, оплата прошла дважды",
])
def test_billing(text):
    assert gate(text).reason == "billing"


@pytest.mark.parametrize("text", [
    "I will contact my lawyer if this is not fixed",
    "This is a scam, I am going to the police",
    "Я подам до суду",
])
def test_abuse_or_legal(text):
    assert gate(text).reason == "abuse"


@pytest.mark.parametrize("text", [
    "Can I speak to a real person?",
    "operator please",
    "Позовіть живого оператора",
])
def test_human_requested(text):
    assert gate(text).reason == "human_requested"


def test_vip_goes_to_a_person_even_for_simple_questions():
    assert gate("How do I restart my server?", vip=True).reason == "vip"


def test_personal_data_wins_over_billing():
    assert gate("Refund to card 4111 1111 1111 1111 please").reason == "personal_data"


@pytest.mark.parametrize("text", [
    "How do I restart my server?",
    "My graphics card is fine but the server lags",      # 'card' alone is not billing
    "The humanoid mobs do not spawn",                    # word boundaries
    "Where is the Invoicing plugin config?",             # 'invoice' inside another word
    "How do I upgrade my plan to get more RAM?",          # plan changes are a how-to, not billing
])
def test_ordinary_questions_pass(text):
    assert gate(text) is None


@pytest.mark.parametrize("text, reason", [
    ("Your DDoS protection failed again, I am suing you", "abuse"),
    ("my lawyers will contact you", "abuse"),
    ("you hacked my server and deleted my world backup", "abuse"),
    ("Звернуся до поліції", "abuse"),
    ("I paid for the upgrade to more RAM but my plan still shows the old RAM", "billing"),
    ("I was billed twice this month", "billing"),
    ("Мені двічі списали кошти", "billing"),
    ("Платеж не прошел", "billing"),
    ("you lost my backup, let me talk to a person", "human_requested"),
    ("restart my server now, I want to speak to an agent", "human_requested"),
    ("соедините с оператором", "human_requested"),
    ("позовіть менеджера", "human_requested"),
])
def test_inflections_and_paraphrases_reach_a_person(text, reason):
    assert gate(text).reason == reason


@pytest.mark.parametrize("text", [
    "How do I use the file manager to upload my world?",
    "how do I make myself operator on my minecraft server",
    "Can I give a sub-user manager permissions?",
    "I am under a DDoS threat right now, how do I enable protection?",
    "my sftp password is not working",
    "change the RCON password to a new one",
    "the world seed is 1234567890123456789",
    "Чекаю на відповідь щодо модів",           # "чекаю" = "I am waiting", not "чек" (receipt)
])
def test_how_to_questions_with_trigger_words_are_not_blocked(text):
    assert gate(text) is None
