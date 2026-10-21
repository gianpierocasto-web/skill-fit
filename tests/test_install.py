from pathlib import Path

from skill_fit.install import classify_url, install_entries, is_within


def _skill(nome: str = "data-labeling") -> dict[str, str]:
    return {
        "id": f"seb1n/awesome-ai-agent-skills/{nome}",
        "nome": nome,
        "tipo": "skill",
        "descrizione": "Create labeled datasets for machine learning model training.",
        "url": f"https://github.com/seb1n/awesome-ai-agent-skills/tree/HEAD/ai-ml-operations/{nome}",
        "raccolta": "seb1n/awesome-ai-agent-skills",
    }


def _rule() -> dict[str, str]:
    return {
        "id": "sanjeed5/awesome-cursor-rules-mdc/angular",
        "nome": "angular",
        "tipo": "rule",
        "descrizione": "Tag pubblicati: frontend, typescript",
        "url": "https://github.com/sanjeed5/awesome-cursor-rules-mdc/blob/HEAD/rules-mdc/angular.mdc",
        "raccolta": "sanjeed5/awesome-cursor-rules-mdc",
    }


def _files(count: int = 1, script: bool = False) -> list[tuple[str, bytes]]:
    rows = [("SKILL.md", b"---\nname: data-labeling\n---\n# Demo\n")]
    if script:
        rows.append(("scripts/run.sh", b"echo hi\n"))
    while len(rows) < count:
        rows.append((f"notes/n{len(rows)}.md", b"x"))
    return rows


def test_classify_skill_directory_and_rule_file() -> None:
    skill = classify_url(_skill()["url"], "skill")
    assert isinstance(skill, dict)
    assert skill["mode"] == "dir"
    assert skill["nome"] == "data-labeling"
    rule = classify_url(_rule()["url"], "rule")
    assert isinstance(rule, dict)
    assert rule["mode"] == "file"
    assert rule["nome"] == "angular.mdc"


def test_classify_rejects_non_mdc_and_parent_segments() -> None:
    cursorrules = (
        "https://github.com/alifesoftware/awesome-cursor-rules/blob/HEAD/"
        "rules/angular/.cursorrules"
    )
    assert isinstance(classify_url(cursorrules, "rule"), str)
    assert isinstance(classify_url("https://officialskills.sh/anthropics/skills/docx", "skill"), str)
    escaped = "https://github.com/owner/repo/blob/HEAD/../../SKILL.md"
    assert isinstance(classify_url(escaped, "skill"), str)


def test_global_rule_is_warning_and_writes_nothing(tmp_path: Path) -> None:
    def fetch(*_args: object) -> list[tuple[str, bytes]]:
        raise AssertionError("una rule globale non si scarica")

    result = install_entries(
        ["sanjeed5/awesome-cursor-rules-mdc/angular"],
        "global",
        entries=[_rule()],
        fetch=fetch,
        skills_home=tmp_path / "skills",
    )
    assert result["avvisi"][0]["motivo"].startswith("Le User Rules globali")
    assert result["installate"] == []
    assert not (tmp_path / "skills").exists()


def test_project_skill_installs_folder_and_reports_scripts(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()

    def fetch(*_args: object) -> list[tuple[str, bytes]]:
        return _files(script=True)

    result = install_entries(
        ["seb1n/awesome-ai-agent-skills/data-labeling"],
        "progetto",
        project_root=str(project),
        entries=[_skill()],
        fetch=fetch,
        skills_home=tmp_path / "unused",
    )
    dest = project / ".cursor" / "skills" / "data-labeling" / "SKILL.md"
    assert dest.is_file()
    assert result["installate"][0]["contiene_script"] is True
    assert result["installate"][0]["percorso"] == str(project / ".cursor" / "skills" / "data-labeling")


def test_overwrite_is_blocked(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    dest = project / ".cursor" / "skills" / "data-labeling"
    dest.mkdir(parents=True)
    (dest / "SKILL.md").write_text("vecchia", encoding="utf-8")

    def fetch(*_args: object) -> list[tuple[str, bytes]]:
        raise AssertionError("non scaricare se la cartella esiste")

    result = install_entries(
        ["seb1n/awesome-ai-agent-skills/data-labeling"],
        "project",
        project_root=str(project),
        entries=[_skill()],
        fetch=fetch,
        skills_home=tmp_path / "skills",
    )
    assert result["conflitti"]
    assert (dest / "SKILL.md").read_text(encoding="utf-8") == "vecchia"


def test_file_limit_refuses_the_copy(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()

    def fetch(*_args: object) -> list[tuple[str, bytes]]:
        return _files(count=51)

    result = install_entries(
        ["seb1n/awesome-ai-agent-skills/data-labeling"],
        "project",
        project_root=str(project),
        entries=[_skill()],
        fetch=fetch,
        skills_home=tmp_path / "skills",
    )
    assert "50 file" in result["non_installabili"][0]["motivo"]
    assert not (project / ".cursor" / "skills" / "data-labeling").exists()


def test_destination_cannot_leave_the_root(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    root.mkdir()
    inside = root / "data-labeling"
    outside = tmp_path / "elsewhere"
    assert is_within(root, inside)
    assert not is_within(root, outside)
    assert not is_within(root, root)
