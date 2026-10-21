# skill-fit

Plugin Cursor. Cerca skill e Cursor Rules nelle raccolte indicate e, dopo un sì, installa solo le voci scelte. Skill e server MCP si installano insieme.

Sul PC serve [uv](https://docs.astral.sh/uv/) nel PATH. Poi, in una chat di Cursor:

```text
/add-plugin skill-fit@https://github.com/gianpierocasto-web/skill-fit
```

Scegli l'ambito utente. In alternativa, in Customize → Plugins → Import marketplace incolla `https://github.com/gianpierocasto-web/skill-fit`.

Quattro tool:

- `search_skills` — verdetto (`skill trovate`, `nessuna skill`, `indice non disponibile`) e, per ogni voce, nome, tipo, descrizione, link e raccolta
- `explain_entry` — scheda di un id già in indice
- `list_collections` — raccolte e numero di voci
- `install_entries` — copia gli id scelti

La skill legge il progetto aperto e scrive lei perché una voce serve in quel contesto. Il server restituisce solo i fatti del catalogo.

L'indice sta in `~/.cache/skill-fit/entries.json` e si ricostruisce ogni 24 ore dai README delle raccolte, da `skills_index.json` di sickn33 e da `rules.json` di sanjeed5 (quel README non elenca le rule). Il corpo di un `SKILL.md` si scarica solo per una voce scelta.

Installazione:

- skill di progetto in `.cursor/skills/<nome>/`
- skill globale in `~/.cursor/skills/<nome>/`
- rule di progetto in `.cursor/rules/<file>.mdc`
- rule globale: nessun file, va incollata in Customize → Rules

Un link che non è una cartella GitHub con `SKILL.md`, o un file `.mdc`, resta non installabile. La copia si ferma a 50 file e 2 MB. I file copiati non vengono eseguiti. Una destinazione già presente non si sovrascrive senza un secondo sì.

Per avviare il server a mano, dalla cartella del plugin:

```bash
uv run skill-fit
```
