"""Copia sul disco solo le skill e le rule scelte, dentro radici consentite."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

from skill_fit.index import (
    find_entry,
    github_json,
    http_get,
    load_entries,
    safe_slug,
)

MAX_FILES = 50
MAX_BYTES = 2 * 1024 * 1024
GLOBAL_RULE_WARNING = (
    "Le User Rules globali non sono file. Incolla il testo in Customize → Rules."
)

Fetch = Callable[[str, str, str, str, str], "list[tuple[str, bytes]] | str"]


def install_entries(
    ids: list[str],
    scope: str,
    project_root: str | None = None,
    overwrite: bool = False,
    *,
    entries: list[dict[str, Any]] | None = None,
    fetch: Fetch | None = None,
    skills_home: Path | None = None,
) -> dict[str, Any]:
    """Installa gli id scelti. scope è project/progetto oppure global/globale."""
    kind = normalize_scope(scope)
    if kind is None:
        return _empty(
            avvisi=[{"motivo": "Ambito sconosciuto. Usa project o global."}],
        )
    if not ids:
        return _empty(avvisi=[{"motivo": "Nessuna voce da installare."}])

    try:
        rows = entries if entries is not None else load_entries()
    except FileNotFoundError as exc:
        return {
            "verdetto": "indice non disponibile",
            "motivo": str(exc),
            "installate": [],
            "conflitti": [],
            "non_installabili": [],
            "avvisi": [],
        }

    project = Path(project_root).expanduser() if project_root else None
    if kind == "project" and (project is None or not project.is_dir()):
        return _empty(
            avvisi=[{"motivo": "Manca la cartella del progetto, oppure non è una directory."}],
        )

    downloader = fetch or default_fetch
    home = skills_home if skills_home is not None else Path.home() / ".cursor" / "skills"
    installed: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    for raw_id in ids:
        ident = str(raw_id).strip()
        entry = find_entry(rows, ident)
        if entry is None:
            rejected.append({"id": ident, "motivo": "Non è nell'indice."})
            continue
        outcome = install_one(
            entry,
            scope=kind,
            project=project,
            overwrite=overwrite,
            fetch=downloader,
            skills_home=home,
        )
        bucket = outcome["esito"]
        payload = outcome["scheda"]
        if bucket == "installata":
            installed.append(payload)
        elif bucket == "conflitto":
            conflicts.append(payload)
        elif bucket == "avviso":
            warnings.append(payload)
        else:
            rejected.append(payload)

    return {
        "verdetto": "skill trovate" if installed else "nessuna skill",
        "installate": installed,
        "conflitti": conflicts,
        "non_installabili": rejected,
        "avvisi": warnings,
    }


def install_one(
    entry: dict[str, Any],
    *,
    scope: str,
    project: Path | None,
    overwrite: bool,
    fetch: Fetch,
    skills_home: Path,
) -> dict[str, Any]:
    ident = str(entry.get("id") or "")
    tipo = str(entry.get("tipo") or "")
    url = str(entry.get("url") or "")
    if tipo == "rule" and scope == "global":
        return {
            "esito": "avviso",
            "scheda": {"id": ident, "nome": entry.get("nome"), "url": url, "motivo": GLOBAL_RULE_WARNING},
        }

    spec = classify_url(url, tipo)
    if isinstance(spec, str):
        return {
            "esito": "rifiutata",
            "scheda": {"id": ident, "nome": entry.get("nome"), "url": url, "motivo": spec},
        }

    dest = destination_for(spec, scope=scope, project=project, skills_home=skills_home)
    if isinstance(dest, str):
        return {"esito": "rifiutata", "scheda": {"id": ident, "url": url, "motivo": dest}}

    root = allowed_root(spec, scope=scope, project=project, skills_home=skills_home)
    if root is None or not is_within(root, dest):
        return {
            "esito": "rifiutata",
            "scheda": {"id": ident, "url": url, "motivo": "Destinazione fuori dalle cartelle consentite."},
        }
    if dest.exists() and not overwrite:
        return {
            "esito": "conflitto",
            "scheda": {
                "id": ident,
                "percorso": str(dest),
                "motivo": "Esiste già. Per sostituirla serve un sì esplicito e overwrite true.",
            },
        }

    fetched = fetch(spec["owner"], spec["repo"], spec["ref"], spec["path"], spec["mode"])
    if isinstance(fetched, str):
        return {"esito": "rifiutata", "scheda": {"id": ident, "url": url, "motivo": fetched}}
    limited = limit_error(fetched)
    if limited:
        return {"esito": "rifiutata", "scheda": {"id": ident, "url": url, "motivo": limited}}
    if spec["mode"] == "dir" and not any(Path(rel).name == "SKILL.md" for rel, _ in fetched):
        return {
            "esito": "rifiutata",
            "scheda": {"id": ident, "url": url, "motivo": "Nella cartella non c'è SKILL.md."},
        }

    write_files(dest, fetched, spec["mode"], root)
    return {
        "esito": "installata",
        "scheda": {
            "id": ident,
            "nome": entry.get("nome"),
            "tipo": tipo,
            "percorso": str(dest),
            "contiene_script": contains_script(fetched),
        },
    }


def classify_url(url: str, tipo: str) -> dict[str, str] | str:
    parsed = parse_github_content(url)
    if parsed is None:
        return "Non installabile: il link non è un file o una cartella GitHub."
    owner, repo, kind, ref, path = parsed
    if kind == "blob" and path.endswith("SKILL.md"):
        parent = path.rsplit("/", 1)[0] if "/" in path else ""
        folder = safe_slug(Path(parent).name if parent else repo)
        if folder is None:
            return "Non installabile: nome cartella non valido."
        return {"owner": owner, "repo": repo, "ref": ref, "path": parent, "mode": "dir", "nome": folder}
    if kind == "blob" and path.endswith(".mdc") and tipo == "rule":
        file_name = Path(path).name
        if safe_slug(file_name.removesuffix(".mdc")) is None:
            return "Non installabile: nome del file non valido."
        return {
            "owner": owner,
            "repo": repo,
            "ref": ref,
            "path": path,
            "mode": "file",
            "nome": file_name,
        }
    if kind == "tree" and tipo == "skill":
        folder = safe_slug(Path(path).name)
        if folder is None:
            return "Non installabile: nome cartella non valido."
        return {"owner": owner, "repo": repo, "ref": ref, "path": path, "mode": "dir", "nome": folder}
    return "Non installabile: serve una cartella di skill oppure un file .mdc."


def parse_github_content(url: str) -> tuple[str, str, str, str, str] | None:
    cleaned = url.strip().split("#", 1)[0].split("?", 1)[0].rstrip("/")
    prefix = "https://github.com/"
    if cleaned.startswith("http://github.com/"):
        cleaned = "https://" + cleaned.removeprefix("http://")
    if not cleaned.startswith(prefix):
        return None
    parts = cleaned.removeprefix(prefix).split("/")
    if len(parts) < 5:
        return None
    owner, repo, kind, ref = parts[0], parts[1], parts[2], parts[3]
    path = "/".join(parts[4:])
    repo = repo.removesuffix(".git")
    if kind not in {"blob", "tree"} or not path or ".." in path.split("/"):
        return None
    return owner, repo, kind, ref, path


def destination_for(
    spec: dict[str, str],
    *,
    scope: str,
    project: Path | None,
    skills_home: Path,
) -> Path | str:
    if spec["mode"] == "dir":
        root = skills_home if scope == "global" else project_skills(project)
        if root is None:
            return "Manca la cartella del progetto."
        return root / spec["nome"]
    root = project_rules(project)
    if root is None:
        return "Manca la cartella del progetto."
    return root / spec["nome"]


def allowed_root(
    spec: dict[str, str],
    *,
    scope: str,
    project: Path | None,
    skills_home: Path,
) -> Path | None:
    if spec["mode"] == "dir":
        return skills_home if scope == "global" else project_skills(project)
    return project_rules(project)


def project_skills(project: Path | None) -> Path | None:
    if project is None:
        return None
    return project / ".cursor" / "skills"


def project_rules(project: Path | None) -> Path | None:
    if project is None:
        return None
    return project / ".cursor" / "rules"


def is_within(root: Path, target: Path) -> bool:
    root_resolved = root.resolve()
    target_resolved = target.resolve()
    if target_resolved == root_resolved:
        return False
    try:
        target_resolved.relative_to(root_resolved)
    except ValueError:
        return False
    return True


def limit_error(files: list[tuple[str, bytes]]) -> str | None:
    if not files:
        return "Nessun file da copiare."
    if len(files) > MAX_FILES:
        return "Supera il limite di 50 file."
    if sum(len(payload) for _, payload in files) > MAX_BYTES:
        return "Supera il limite di 2 MB."
    for rel, _payload in files:
        path = Path(rel)
        if path.is_absolute() or ".." in path.parts:
            return "Percorso del file non valido."
    return None


def contains_script(files: list[tuple[str, bytes]]) -> bool:
    for rel, _payload in files:
        parts = Path(rel).parts
        if "scripts" in parts:
            return True
    return False


def write_files(dest: Path, files: list[tuple[str, bytes]], mode: str, root: Path) -> None:
    if dest.exists():
        if not is_within(root, dest):
            raise OSError("rifiutata la rimozione fuori radice")
        if dest.is_dir():
            shutil.rmtree(dest)
        else:
            dest.unlink()
    if mode == "file":
        if not is_within(root, dest):
            raise OSError("file fuori radice")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(files[0][1])
        return
    dest.mkdir(parents=True, exist_ok=True)
    for rel, payload in files:
        target = dest.joinpath(*Path(rel).parts)
        if not is_within(dest, target):
            raise OSError("file fuori dalla cartella della skill")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)


def default_fetch(owner: str, repo: str, ref: str, path: str, mode: str) -> list[tuple[str, bytes]] | str:
    try:
        files: list[tuple[str, bytes]] = []
        total = 0

        def add(rel: str, payload: bytes) -> None:
            nonlocal total
            checked = Path(rel)
            if checked.is_absolute() or ".." in checked.parts:
                raise ValueError("percorso non valido")
            if len(files) >= MAX_FILES or total + len(payload) > MAX_BYTES:
                raise RuntimeError("limite")
            total += len(payload)
            files.append((rel, payload))

        if mode == "file":
            payload = download_bytes(owner, repo, ref, path)
            if payload is None:
                return "Download non riuscito."
            add(Path(path).name, payload)
            return files
        if not walk_dir(owner, repo, ref, path, "", add):
            return "Download non riuscito."
        return files
    except RuntimeError:
        return "Supera il limite di 50 file o 2 MB."
    except (OSError, ValueError):
        return "Download non riuscito."


def walk_dir(
    owner: str,
    repo: str,
    ref: str,
    path: str,
    prefix: str,
    add: Callable[[str, bytes], None],
) -> bool:
    data = contents(owner, repo, ref, path)
    if data is None:
        return False
    if isinstance(data, dict) and data.get("type") == "file":
        payload = read_content_item(data)
        if payload is None:
            return False
        add(prefix or str(data.get("name") or Path(path).name), payload)
        return True
    if not isinstance(data, list):
        return False
    for item in data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        if name in {"", ".", "..", ".git"}:
            continue
        rel = f"{prefix}/{name}" if prefix else name
        item_path = str(item.get("path") or "")
        if item.get("type") == "dir":
            if not walk_dir(owner, repo, ref, item_path, rel, add):
                return False
        elif item.get("type") == "file":
            payload = read_content_item(item)
            if payload is None:
                return False
            add(rel, payload)
    return True


def contents(owner: str, repo: str, ref: str, path: str) -> Any | None:
    refs = [ref] if ref not in {"HEAD", ""} else ["HEAD", "main", "master"]
    for candidate in refs:
        quoted = quote(path, safe="/")
        suffix = f"/{quoted}" if quoted else ""
        url = (
            f"https://api.github.com/repos/{owner}/{repo}/contents{suffix}"
            f"?ref={quote(candidate, safe='')}"
        )
        data = github_json(url)
        if isinstance(data, dict) and data.get("message") and "type" not in data:
            continue
        if data is not None:
            return data
    return None


def download_bytes(owner: str, repo: str, ref: str, path: str) -> bytes | None:
    data = contents(owner, repo, ref, path)
    if not isinstance(data, dict):
        return None
    return read_content_item(data)


def read_content_item(item: dict[str, Any]) -> bytes | None:
    download = item.get("download_url")
    if isinstance(download, str) and download:
        return http_get(download, limit=MAX_BYTES + 1)
    return None


def normalize_scope(scope: str) -> str | None:
    value = scope.strip().lower()
    if value in {"project", "progetto"}:
        return "project"
    if value in {"global", "globale"}:
        return "global"
    return None


def _empty(*, avvisi: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "verdetto": "nessuna skill",
        "installate": [],
        "conflitti": [],
        "non_installabili": [],
        "avvisi": avvisi,
    }
