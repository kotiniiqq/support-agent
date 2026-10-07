from support_agent.kb import chunks, load_articles, parse_article


def test_all_articles_load_with_summary_and_steps():
    articles = load_articles()
    assert len(articles) == 13
    for a in articles:
        assert set(a.sections) == {"Summary", "Steps"}, a.id
        assert a.title and a.tags


def test_parse_article_front_matter_and_sections():
    a = parse_article("---\nid: x\ntitle: X\ntags: [a, b]\n---\n## Summary\nhello\n\n## Steps\n1. go\n")
    assert (a.id, a.title, a.tags) == ("x", "X", ["a", "b"])
    assert a.sections == {"Summary": "hello", "Steps": "1. go"}


def test_chunks_are_per_section_with_title_and_tags():
    cs = chunks(load_articles())
    assert len(cs) == 26
    first = next(c for c in cs if c.chunk_id == "backups#1")
    assert first.text.startswith("Create and restore backups.") and "restore" in first.text
