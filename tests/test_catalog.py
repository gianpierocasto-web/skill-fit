from skill_fit.index import (
    absolute_url,
    entries_from_sanjeed5,
    entries_from_sickn33,
    extract_terms,
    frontmatter_fields,
    needs_frontmatter,
    parse_markdown,
    score_entry,
    search_entries,
)


SPENCER = """
- [Skills](#skills)
- [`suggesting-cursor-rules`](resources/suggesting-cursor-rules/SKILL.md) - If you keep correcting the agent on the same convention, it suggests a rule file.
- [![badge](https://img.shields.io/badge/a-b)](https://example.com) - ignored because the label is an image
"""

VOLT = """
- **[anthropics/docx](https://officialskills.sh/anthropics/skills/docx)** - Create, edit, and analyze Word documents
"""

SEB = """
| [Agent Engineering](./agent-engineering/) | [Code](./code/) | [Writing](./writing/) |
| [data-labeling](./ai-ml-operations/data-labeling) | Create labeled datasets for machine learning model training |
"""


def test_parse_bullet_resolves_relative_skill() -> None:
    entries = parse_markdown(SPENCER, "spencerpauly/awesome-cursor-skills", "skill")
    assert len(entries) == 1
    entry = entries[0]
    assert entry["nome"] == "suggesting-cursor-rules"
    assert entry["tipo"] == "skill"
    assert entry["url"] == (
        "https://github.com/spencerpauly/awesome-cursor-skills/blob/HEAD/"
        "resources/suggesting-cursor-rules/SKILL.md"
    )
    assert "convention" in entry["descrizione"]


def test_parse_bold_bullet_keeps_external_url() -> None:
    entries = parse_markdown(VOLT, "VoltAgent/awesome-agent-skills", "skill")
    assert entries[0]["url"] == "https://officialskills.sh/anthropics/skills/docx"
    assert entries[0]["descrizione"].startswith("Create, edit")


def test_parse_table_skips_category_row() -> None:
    entries = parse_markdown(SEB, "seb1n/awesome-ai-agent-skills", "skill")
    assert [entry["nome"] for entry in entries] == ["data-labeling"]
    assert entry_url(entries[0]).endswith("/tree/HEAD/ai-ml-operations/data-labeling")


def test_absolute_url_rejects_parent_segments() -> None:
    assert absolute_url("owner/repo", "../secrets/SKILL.md") == ""


def test_name_outranks_description() -> None:
    named = {
        "id": "a/b/alpha-widget",
        "nome": "alpha-widget",
        "tipo": "skill",
        "descrizione": "does nothing related",
        "url": "https://github.com/a/b/tree/HEAD/alpha-widget",
        "raccolta": "a/b",
    }
    described = {
        "id": "a/b/other",
        "nome": "other",
        "tipo": "skill",
        "descrizione": "alpha widget helper for the task",
        "url": "https://github.com/a/b/tree/HEAD/other",
        "raccolta": "a/b",
    }
    assert score_entry(named, ["alpha", "widget"])[1] > score_entry(described, ["alpha", "widget"])[1]
    hits = search_entries([described, named], ["alpha", "widget"], "skill", 5)
    assert hits[0]["nome"] == "alpha-widget"


def test_search_filters_rules() -> None:
    skill = _entry("docx", "skill")
    rule = _entry("angular", "rule")
    hits = search_entries([skill, rule], ["angular", "docx"], "rule", 5)
    assert [hit["nome"] for hit in hits] == ["angular"]


def test_extract_terms_drops_glue_words() -> None:
    assert extract_terms("una skill per i test") == ["skill", "test"]


def test_frontmatter_and_threshold() -> None:
    name, description = frontmatter_fields("---\nname: data-labeling\ndescription: Create labeled datasets\n---\n# Body\n")
    assert name == "data-labeling"
    assert description == "Create labeled datasets"
    assert needs_frontmatter("seb1n/awesome-ai-agent-skills", 3)
    assert not needs_frontmatter("seb1n/awesome-ai-agent-skills", 20)
    assert not needs_frontmatter("VoltAgent/awesome-agent-skills", 0)


def test_sickn33_and_sanjeed5_indexes() -> None:
    skills = entries_from_sickn33(
        [
            {
                "name": "00-andruia-consultant",
                "path": "skills/00-andruia-consultant",
                "description": "Diagnostica un progetto di IA e propone skill esistenti.",
                "risk": "safe",
            }
        ]
    )
    assert skills[0]["rischio"] == "safe"
    assert skills[0]["url"].endswith("/tree/HEAD/skills/00-andruia-consultant")
    rules = entries_from_sanjeed5({"libraries": [{"name": "angular", "tags": ["frontend", "typescript"]}]})
    assert rules[0]["tipo"] == "rule"
    assert rules[0]["descrizione"] == "Tag pubblicati: frontend, typescript"
    assert rules[0]["url"].endswith("/rules-mdc/angular.mdc")


def _entry(nome: str, tipo: str) -> dict[str, str]:
    return {
        "id": f"demo/repo/{nome}",
        "nome": nome,
        "tipo": tipo,
        "descrizione": f"Voce pubblicata su {nome} per il catalogo di prova.",
        "url": f"https://github.com/demo/repo/tree/HEAD/{nome}",
        "raccolta": "demo/repo",
    }


def entry_url(entry: dict[str, str]) -> str:
    return entry["url"]
