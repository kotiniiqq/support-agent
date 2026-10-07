"""Plain data passed between the pipeline steps."""
from dataclasses import dataclass, field

ANSWER, HANDOFF = "answer", "handoff"
# handoff reasons, in the order the pipeline can produce them
SENSITIVE = ("personal_data", "billing", "abuse", "human_requested", "vip")
REASONS = SENSITIVE + ("no_match", "llm_escalated", "ungrounded", "error")


@dataclass
class Customer:
    name: str = "customer"
    plan: str = "standard"
    vip: bool = False


@dataclass
class Ticket:
    id: str
    text: str
    customer: Customer = field(default_factory=Customer)
    channel: str = "chat"


@dataclass
class Chunk:
    article_id: str
    chunk_id: str
    title: str
    text: str


@dataclass
class Hit:
    article_id: str
    chunk_id: str
    title: str
    text: str
    score: float  # normalised to 0..1


@dataclass
class Decision:
    route: str                      # ANSWER or HANDOFF
    reason: str | None = None       # one of REASONS when route == HANDOFF
    answer: str | None = None
    sources: list[str] = field(default_factory=list)
    score: float = 0.0
    evidence: str | None = None     # what triggered a rule, already redacted
    summary: str | None = None      # note for the human agent on handoff
    mode: str | None = None         # "extractive" or "llm"
