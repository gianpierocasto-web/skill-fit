"""Catalogo delle raccolte di skill e Cursor Rules, con cache di 24 ore."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("skill_fit")

CACHE = Path.home() / ".cache" / "skill-fit" / "entries.json"
MAX_AGE_SECONDS = 86400
CATALOG_BYTES = 8_000_000
SEB1N = "seb1n/awesome-ai-agent-skills"
FRONTMATTER_BELOW = 20
USER_AGENT = "skill-fit"

SOURCES: list[dict[str, str]] = [
    {"raccolta": "spencerpauly/awesome-cursor-skills", "tipo": "skill", "modo": "readme"},
    {"raccolta": "VoltAgent/awesome-agent-skills", "tipo": "skill", "modo": "readme"},
    {"raccolta": "heilcheng/awesome-agent-skills", "tipo": "skill", "modo": "readme"},
    {"raccolta": "ComposioHQ/awesome-claude-skills", "tipo": "skill", "modo": "readme"},
    {"raccolta": "composio-community/awesome-codex-skills", "tipo": "skill", "modo": "readme"},
    {"raccolta": "JackyST0/awesome-agent-skills", "tipo": "skill", "modo": "readme"},
    {"raccolta": SEB1N, "tipo": "skill", "modo": "readme"},
    {"raccolta": "sickn33/agentic-awesome-skills", "tipo": "skill", "modo": "skills_index"},
    {"raccolta": "PatrickJS/awesome-cursorrules", "tipo": "rule", "modo": "readme"},
    {"raccolta": "sanjeed5/awesome-cursor-rules-mdc", "tipo": "rule", "modo": "rules_json"},
    {"raccolta": "alifesoftware/awesome-cursor-rules", "tipo": "rule", "modo": "readme"},
]

RESERVED = {
    "aux",
    "com1",
    "com2",
    "com3",
    "com4",
    "con",
    "lpt1",
    "nul",
    "prn",
}

STOPWORDS = {
    "a",
    "al",
    "alla",
    "alle",
    "agli",
    "ai",
    "allo",
    "an",
    "and",
    "anche",
    "che",
    "con",
    "come",
    "da",
    "dei",
    "del",
    "della",
    "delle",
    "dello",
    "di",
    "e",
    "ed",
    "for",
    "gli",
    "i",
    "il",
    "in",
    "la",
    "le",
    "lo",
    "ma",
    "mi",
    "of",
    "on",
    "or",
    "per",
    "su",
    "the",
    "to",
    "un",
    "una",
    "uno",
    "with",
}

SYNONYMS: dict[str, list[str]] = {
    "auth": ["authentication", "login"],
    "autenticazione": ["auth", "authentication"],
    "regola": ["rule", "rules"],
    "regole": ["rule", "rules"],
    "rule": ["rules"],
    "rules": ["rule"],
    "test": ["testing", "tests"],
    "testing": ["test", "tests"],
    "tests": ["test", "testing"],
}

_BULLET = re.compile(
    r"^\s*[-*]\s+(?:\*\*)?\[`?([^`\]]+)`?\]\(([^)]+)\)(?:\*\*)?\s*[-–—:]\s+(.+?)\s*$"
)
_TABLE = re.compile(r"^\|\s*\[([^\]]+)\]\(([^)]+)\)\s*\|\s*(.*?)\s*\|\s*$")
_FM_NAME = re.compile(r"(?m)^name:\s*[\"']?(.+?)[\"']?\s*$")
_FM_DESCRIPTION = re.compile(r"(?m)^description:\s*[\"']?(.+?)[\"']?\s*$")

_lock = threading.Lock()
_entries: list[dict[str, Any]] | None = None
_loaded_mtime: float | None = None
_token: str | None = None


def search_skills(
    query: str,
    tipo: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Cerca nel catalogo. Restituisce solo i fatti pubblicati dalle raccolte."""
    terms = extract_terms(query)
    kind = normalize_tipo(tipo)
    if not terms:
        return {
            "verdetto": "nessuna skill",
            "motivo": (
                "Nella richiesta non resta nessun termine. Indica il compito, "
                "il framework o la funzione."
            ),
            "termini": [],
            "risultati": [],
            "indice": _meta_or_empty(),
        }
    try:
        entries = load_entries()
        meta = index_meta()
    except FileNotFoundError as exc:
        return {
            "verdetto": "indice non disponibile",
            "motivo": str(exc),
            "termini": terms,
            "risultati": [],
            "indice": {},
        }
    cards = search_entries(entries, terms, kind, clamp_limit(limit))
    if cards:
        motivo = (
            f"Trovate {len(cards)} voci per i termini: {', '.join(terms)}. "
            "Il perché nel progetto lo scrive la skill, usando solo questi campi."
        )
        verdetto = "skill trovate"
    else:
        motivo = (
            "Nessuna voce copre questi termini. Riprova con il nome del framework "
            f"o della funzione. Termini usati: {', '.join(terms)}."
        )
        verdetto = "nessuna skill"
    return {
        "verdetto": verdetto,
        "motivo": motivo,
        "termini": terms,
        "tipo": kind,
        "risultati": cards,
        "indice": meta,
    }


def explain_entry(ref: str) -> dict[str, Any]:
    """Scheda di una voce già in indice, per id, URL o nome."""
    try:
        entries = load_entries()
        meta = index_meta()
    except FileNotFoundError as exc:
        return {
            "verdetto": "indice non disponibile",
            "motivo": str(exc),
            "risultati": [],
            "indice": {},
        }
    entry = find_entry(entries, ref)
    if entry is None:
        return {
            "verdetto": "nessuna skill",
            "motivo": f"{ref} non è nell'indice.",
            "risultati": [],
            "indice": meta,
        }
    return {
        "verdetto": "skill trovate",
        "motivo": "Scheda letta dall'indice, senza una query di confronto.",
        "risultati": [public_card(entry)],
        "indice": meta,
    }


def list_collections() -> dict[str, Any]:
    """Elenca le raccolte attese, con il numero di voci in cache."""
    try:
        entries = load_entries()
        meta = index_meta()
    except FileNotFoundError as exc:
        return {
            "verdetto": "indice non disponibile",
            "motivo": str(exc),
            "raccolte": [],
            "indice": {},
        }
    counts: dict[str, int] = {}
    for entry in entries:
        key = str(entry.get("raccolta") or "")
        counts[key] = counts.get(key, 0) + 1
    raccolte = [
        {
            "raccolta": source["raccolta"],
            "tipo": source["tipo"],
            "voci": counts.get(source["raccolta"], 0),
        }
        for source in SOURCES
    ]
    return {"verdetto": "skill trovate", "raccolte": raccolte, "indice": meta}


def search_entries(
    entries: list[dict[str, Any]],
    terms: list[str],
    tipo: str,
    limit: int,
) -> list[dict[str, Any]]:
    ranked: list[tuple[tuple[int, float], dict[str, Any]]] = []
    for entry in entries:
        if tipo != "tutti" and entry.get("tipo") != tipo:
            continue
        scored = score_entry(entry, terms)
        if scored is None:
            continue
        ranked.append((scored, entry))
    ranked.sort(key=lambda item: (-item[0][0], -item[0][1], str(item[1].get("nome"))))
    return [public_card(entry) for _, entry in ranked[:limit]]


def score_entry(entry: dict[str, Any], terms: list[str]) -> tuple[int, float] | None:
    weighted = fields(entry)
    matched = 0
    total = 0.0
    for term in terms:
        best = 0.0
        for alternative in [term, *SYNONYMS.get(term, [])]:
            weight_factor = 1.0 if alternative == term else 0.7
            for weight, text in weighted:
                if term_hit(alternative, text):
                    best = max(best, weight * weight_factor)
        if best:
            matched += 1
            total += best
    if not matched:
        return None
    return (matched, total)


def fields(entry: dict[str, Any]) -> list[tuple[float, str]]:
    url = str(entry.get("url") or "")
    slug = url.rstrip("/").split("/")[-1].lower().replace("-", " ").replace("_", " ")
    return [
        (3.0, str(entry.get("nome") or "").lower()),
        (3.0, slug),
        (1.5, str(entry.get("descrizione") or "").lower()),
        (1.0, str(entry.get("raccolta") or "").lower()),
    ]


def term_hit(term: str, text: str) -> bool:
    if len(term) <= 3:
        return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) is not None
    return term in text


def extract_terms(query: str) -> list[str]:
    terms: list[str] = []
    for token in re.split(r"[\s,;:/|]+", query.lower()):
        cleaned = token.strip(".,;:!?\"'()[]{}`")
        if not cleaned or cleaned in STOPWORDS:
            continue
        if len(cleaned) == 1:
            continue
        if cleaned not in terms:
            terms.append(cleaned)
    return terms


def normalize_tipo(tipo: str | None) -> str:
    value = (tipo or "skill").strip().lower()
    if value in {"skill", "rule", "tutti"}:
        return value
    return "skill"


def clamp_limit(limit: int) -> int:
    try:
        value = int(limit)
    except (TypeError, ValueError):
        return 5
    return min(8, max(1, value))


def public_card(entry: dict[str, Any]) -> dict[str, Any]:
    card = {
        "id": entry.get("id"),
        "nome": entry.get("nome"),
        "tipo": entry.get("tipo"),
        "descrizione": entry.get("descrizione") or "",
        "url": entry.get("url"),
        "raccolta": entry.get("raccolta"),
    }
    rischio = entry.get("rischio")
    if rischio:
        card["rischio"] = rischio
    return card


def parse_markdown(text: str, raccolta: str, tipo: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in text.splitlines():
        parsed = _BULLET.match(line) or _TABLE.match(line)
        if parsed is None:
            continue
        nome, url, descrizione = parsed.group(1), parsed.group(2), parsed.group(3)
        if nome.startswith("!") or descrizione.strip().startswith("["):
            continue
        absolute = absolute_url(raccolta, url)
        if not absolute:
            continue
        entry = make_entry(
            raccolta=raccolta,
            tipo=tipo,
            nome=nome,
            descrizione=descrizione,
            url=absolute,
        )
        if entry is None or entry["id"] in seen:
            continue
        seen.add(str(entry["id"]))
        entries.append(entry)
    return entries


def absolute_url(raccolta: str, url: str) -> str:
    cleaned = url.strip().strip("<>")
    if cleaned.startswith("#") or cleaned.startswith("mailto:"):
        return ""
    if "shields.io" in cleaned or "img.shields.io" in cleaned:
        return ""
    if cleaned.startswith(("http://", "https://")):
        return cleaned.split()[0]
    if "://" in cleaned:
        return ""
    owner, _, repo = raccolta.partition("/")
    if not owner or not repo:
        return ""
    path = cleaned.split("#", 1)[0].split("?", 1)[0].strip()
    while path.startswith("./"):
        path = path[2:]
    path = path.strip("/")
    if not path or ".." in path.split("/"):
        return ""
    kind = "blob" if Path(path).suffix else "tree"
    return f"https://github.com/{owner}/{repo}/{kind}/HEAD/{path}"


def make_entry(
    *,
    raccolta: str,
    tipo: str,
    nome: str,
    descrizione: str,
    url: str,
    rischio: str | None = None,
) -> dict[str, Any] | None:
    title = nome.strip().strip("`").strip()
    summary = clean_description(descrizione)
    link = url.strip()
    if not title or len(summary) < 8 or not link:
        return None
    slug = safe_slug(title)
    if slug is None:
        return None
    entry: dict[str, Any] = {
        "id": f"{raccolta}/{slug}",
        "nome": title,
        "tipo": tipo,
        "descrizione": summary,
        "url": link,
        "raccolta": raccolta,
    }
    if rischio:
        entry["rischio"] = str(rischio).strip()
    return entry


def clean_description(text: str) -> str:
    plain = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    plain = plain.replace("**", "").replace("`", "")
    plain = re.sub(r"\s+", " ", plain).strip(" -–—*")
    return plain[:500]


def safe_slug(name: str) -> str | None:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    slug = slug[:80].strip("-")
    if not slug or slug in RESERVED:
        return None
    return slug


def needs_frontmatter(raccolta: str, count: int) -> bool:
    return raccolta == SEB1N and count < FRONTMATTER_BELOW


def frontmatter_fields(text: str) -> tuple[str, str]:
    stripped = text.lstrip("\ufeff")
    if not stripped.startswith("---"):
        return "", ""
    end = stripped.find("\n---", 3)
    if end < 0:
        return "", ""
    block = stripped[3:end]
    name_match = _FM_NAME.search(block)
    description_match = _FM_DESCRIPTION.search(block)
    name = name_match.group(1).strip() if name_match else ""
    description = description_match.group(1).strip() if description_match else ""
    return name, description


def entries_from_sickn33(data: Any) -> list[dict[str, Any]]:
    items = data if isinstance(data, list) else []
    raccolta = "sickn33/agentic-awesome-skills"
    entries: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip("/")
        if not path or ".." in path.split("/"):
            continue
        entry = make_entry(
            raccolta=raccolta,
            tipo="skill",
            nome=str(item.get("name") or ""),
            descrizione=str(item.get("description") or ""),
            url=f"https://github.com/{raccolta}/tree/HEAD/{path}",
            rischio=str(item.get("risk") or "") or None,
        )
        if entry is not None:
            entries.append(entry)
    return entries


def entries_from_sanjeed5(data: Any) -> list[dict[str, Any]]:
    libraries = data.get("libraries") if isinstance(data, dict) else None
    if not isinstance(libraries, list):
        return []
    raccolta = "sanjeed5/awesome-cursor-rules-mdc"
    entries: list[dict[str, Any]] = []
    for item in libraries:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        tags = item.get("tags") if isinstance(item.get("tags"), list) else []
        tag_text = ", ".join(str(tag) for tag in tags if str(tag).strip())
        if not name or not tag_text or ".." in name or "/" in name:
            continue
        entry = make_entry(
            raccolta=raccolta,
            tipo="rule",
            nome=name,
            descrizione=f"Tag pubblicati: {tag_text}",
            url=(
                "https://github.com/sanjeed5/awesome-cursor-rules-mdc/blob/HEAD/"
                f"rules-mdc/{name}.mdc"
            ),
        )
        if entry is not None:
            entries.append(entry)
    return entries


def find_entry(entries: list[dict[str, Any]], ref: str) -> dict[str, Any] | None:
    needle = ref.strip()
    lowered = needle.lower().rstrip("/")
    by_name: list[dict[str, Any]] = []
    for entry in entries:
        if str(entry.get("id") or "") == needle:
            return entry
        url = str(entry.get("url") or "").rstrip("/").lower()
        if url == lowered or url.removeprefix("https://").removeprefix("http://") == lowered.removeprefix(
            "https://"
        ).removeprefix("http://"):
            return entry
        if str(entry.get("nome") or "").lower() == lowered:
            by_name.append(entry)
    if len(by_name) == 1:
        return by_name[0]
    return None


def load_entries() -> list[dict[str, Any]]:
    global _entries, _loaded_mtime
    path = ensure_cache()
    mtime = path.stat().st_mtime
    with _lock:
        if _entries is not None and _loaded_mtime == mtime:
            return _entries
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data.get("entries") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise FileNotFoundError("L'indice non è un elenco di voci.")
        _entries = rows
        _loaded_mtime = mtime
        return _entries


def ensure_cache() -> Path:
    override = os.environ.get("SKILL_FIT_DATA")
    if override:
        path = Path(override)
        if not path.is_file():
            raise FileNotFoundError(f"SKILL_FIT_DATA non è un file: {path}")
        return path
    fresh = CACHE.is_file() and (time.time() - CACHE.stat().st_mtime) < MAX_AGE_SECONDS
    if fresh:
        return CACHE
    try:
        entries = build_entries()
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        logger.warning("catalogo non aggiornato: %s", exc)
        entries = []
    if not entries:
        if CACHE.is_file():
            logger.warning("uso la cache scaduta di skill-fit")
            return CACHE
        raise FileNotFoundError("Indice non scaricabile e nessuna cache locale.")
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generato": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "entries": entries,
    }
    temporary = CACHE.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temporary.replace(CACHE)
    return CACHE


def index_meta() -> dict[str, Any]:
    path = ensure_cache()
    updated = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
    return {"aggiornato": updated, "voci": len(load_entries())}


def build_entries() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for source in SOURCES:
        raccolta = source["raccolta"]
        tipo = source["tipo"]
        modo = source["modo"]
        if modo == "readme":
            text = fetch_text(raw_url(raccolta, "README.md"))
            if not text:
                continue
            found = parse_markdown(text, raccolta, tipo)
            if needs_frontmatter(raccolta, len(found)):
                found.extend(fetch_frontmatter_entries(raccolta))
            entries.extend(found)
        elif modo == "skills_index":
            text = fetch_text(raw_url(raccolta, "skills_index.json"))
            if not text:
                continue
            entries.extend(entries_from_sickn33(json.loads(text)))
        elif modo == "rules_json":
            text = fetch_text(raw_url(raccolta, "rules.json"))
            if not text:
                continue
            entries.extend(entries_from_sanjeed5(json.loads(text)))
        else:
            logger.warning("modo catalogo sconosciuto: %s", modo)
    return dedupe(entries)


def fetch_frontmatter_entries(raccolta: str) -> list[dict[str, Any]]:
    owner, _, repo = raccolta.partition("/")
    payload = github_json(f"https://api.github.com/repos/{owner}/{repo}/git/trees/HEAD?recursive=1")
    tree = payload.get("tree") if isinstance(payload, dict) else None
    if not isinstance(tree, list):
        return []
    paths = [
        str(item.get("path"))
        for item in tree
        if isinstance(item, dict) and str(item.get("path") or "").endswith("SKILL.md")
    ]
    entries: list[dict[str, Any]] = []
    for path in paths[:200]:
        if ".." in path.split("/"):
            continue
        text = fetch_text(raw_url(raccolta, path))
        if not text:
            continue
        name, description = frontmatter_fields(text)
        entry = make_entry(
            raccolta=raccolta,
            tipo="skill",
            nome=name,
            descrizione=description,
            url=f"https://github.com/{raccolta}/blob/HEAD/{path}",
        )
        if entry is not None:
            entries.append(entry)
    return entries


def dedupe(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_url: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for entry in entries:
        key = str(entry.get("url") or "").rstrip("/").lower()
        if not key:
            continue
        current = by_url.get(key)
        if current is None:
            by_url[key] = entry
            order.append(key)
            continue
        if len(str(entry.get("descrizione") or "")) > len(str(current.get("descrizione") or "")):
            by_url[key] = entry
    seen_ids: set[str] = set()
    unique: list[dict[str, Any]] = []
    for key in order:
        entry = dict(by_url[key])
        base = str(entry["id"])
        ident = base
        suffix = 2
        while ident in seen_ids:
            ident = f"{base}-{suffix}"
            suffix += 1
        entry["id"] = ident
        seen_ids.add(ident)
        unique.append(entry)
    return unique


def raw_url(raccolta: str, path: str) -> str:
    return f"https://raw.githubusercontent.com/{raccolta}/HEAD/{path}"


def fetch_text(url: str) -> str | None:
    payload = http_get(url, limit=CATALOG_BYTES)
    if payload is None:
        return None
    return payload.decode("utf-8", "replace")


def github_json(url: str) -> Any | None:
    payload = http_get(url, limit=CATALOG_BYTES)
    if payload is None:
        return None
    try:
        return json.loads(payload.decode("utf-8", "replace"))
    except json.JSONDecodeError:
        return None


def http_get(url: str, limit: int = CATALOG_BYTES) -> bytes | None:
    host = urllib.parse.urlparse(url).hostname
    if host not in {"api.github.com", "raw.githubusercontent.com"}:
        return None
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    token = github_token()
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read(limit)
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def github_token() -> str:
    global _token
    with _lock:
        if _token is not None:
            return _token
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
        if not token:
            try:
                result = subprocess.run(
                    ["gh", "auth", "token"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            except (OSError, subprocess.TimeoutExpired):
                result = None
            if result is not None and result.returncode == 0:
                token = result.stdout.strip()
        _token = token
        return _token


def _meta_or_empty() -> dict[str, Any]:
    try:
        return index_meta()
    except FileNotFoundError:
        return {}
