"""Server MCP stdio: skill e Cursor Rules adatte al compito."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from skill_fit.index import explain_entry as explain
from skill_fit.index import list_collections as collections
from skill_fit.index import search_skills as search
from skill_fit.install import install_entries as install

mcp = MCPServer(
    "skill-fit",
    instructions=(
        "Cerca skill e Cursor Rules nelle raccolte indicate. "
        "Rispondi in italiano partendo dal verdetto. "
        "Usa solo id, nome, tipo, descrizione, url, raccolta e, se c'è, rischio: "
        "non inventare capacità. "
        "Il perché nel progetto lo scrive chi chiama il tool, dal contesto aperto. "
        "Installa solo dopo un sì esplicito, e non eseguire i file copiati."
    ),
)


@mcp.tool()
def search_skills(
    query: str,
    tipo: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Cerca skill o rule per un compito.

    tipo è skill (default), rule o tutti. query è una frase corta: restano i termini
    significativi. Restituisce il verdetto e, per ogni voce, solo i fatti del catalogo.
    """
    try:
        return search(query, tipo=tipo, limit=limit)
    except FileNotFoundError as exc:
        return {"verdetto": "indice non disponibile", "motivo": str(exc), "risultati": []}


@mcp.tool()
def explain_entry(id: str) -> dict[str, Any]:
    """Scheda di una voce già in indice. id accetta l'id, l'URL o il nome univoco."""
    try:
        return explain(id)
    except FileNotFoundError as exc:
        return {"verdetto": "indice non disponibile", "motivo": str(exc), "risultati": []}


@mcp.tool()
def list_collections() -> dict[str, Any]:
    """Elenca le raccolte del catalogo, con tipo e numero di voci."""
    try:
        return collections()
    except FileNotFoundError as exc:
        return {"verdetto": "indice non disponibile", "motivo": str(exc), "raccolte": []}


@mcp.tool()
def install_entries(
    ids: list[str],
    scope: str,
    project_root: str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Copia solo gli id scelti, dopo un sì di chi usa la skill.

    scope è project o global. Le skill di progetto finiscono in .cursor/skills,
    quelle globali in ~/.cursor/skills. Le rule solo in .cursor/rules del progetto.
    Una rule globale non viene scritta. overwrite true solo dopo un secondo sì.
    """
    try:
        return install(ids, scope, project_root=project_root, overwrite=overwrite)
    except FileNotFoundError as exc:
        return {"verdetto": "indice non disponibile", "motivo": str(exc), "installate": []}


def main() -> None:
    mcp.run()
