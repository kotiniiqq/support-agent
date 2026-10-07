"""Knowledge base: markdown articles with a small front matter, split into chunks."""
import re
from dataclasses import dataclass
from pathlib import Path

from .models import Chunk

KB_DIR = Path(__file__).resolve().parent / "kb"  # shipped inside the package


@dataclass
class Article:
    id: str
    title: str
    tags: list[str]
    sections: dict[str, str]  # heading -> text

    @property
    def body(self) -> str:
        return "\n\n".join(self.sections.values())


def parse_article(text: str) -> Article:
    match = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
    if not match:
        raise ValueError("article has no front matter")
    meta = dict(line.split(":", 1) for line in match.group(1).splitlines() if ":" in line)
    meta = {k.strip(): v.strip() for k, v in meta.items()}
    tags = [t.strip() for t in meta.get("tags", "").strip("[]").split(",") if t.strip()]
    sections, current = {}, None
    for line in match.group(2).splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = ""
        elif current is not None:
            sections[current] = (sections[current] + "\n" + line).strip()
    return Article(id=meta["id"], title=meta["title"], tags=tags, sections=sections)


def load_articles(kb_dir: Path | None = None) -> list[Article]:
    folder = kb_dir or KB_DIR
    return [parse_article(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("*.md"))]


def chunks(articles: list[Article]) -> list[Chunk]:
    """One chunk per section; the title and tags are prepended so short sections stay findable."""
    out = []
    for a in articles:
        for n, (heading, text) in enumerate(a.sections.items(), start=1):
            out.append(Chunk(article_id=a.id, chunk_id=f"{a.id}#{n}", title=a.title,
                             text=f"{a.title}. {' '.join(a.tags)}. {heading}: {text}"))
    return out
