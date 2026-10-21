---
name: skill-fit
description: Cerca una skill o una Cursor Rule già pubblicata per il compito nel progetto aperto. Usa quando serve un workflow, una funzione o una convenzione e vuoi sapere quale skill o rule esiste, perché serve in questo contesto, e se installarla nel progetto o in globale. Chiama il MCP skill-fit.
---

# Skill adatta al contesto

Il catalogo sono le raccolte di skill e di Cursor Rules indicate nel README del plugin. Il MCP `skill-fit` le cerca. La frase sul perché la scrivi tu, dal progetto aperto.

## Quando usarla

Usa il MCP quando l'utente vuole una skill, un workflow o una convenzione per un compito, oppure prima di scrivere da zero un flusso che una skill pubblicata copre già.

## Contesto, sempre

Prima di chiamare il MCP, osserva il workspace: linguaggi, framework, file aperti e compito. Se non c'è un progetto, il contesto è solo la richiesta, e nella risposta lo dici.

Al MCP passa una query corta, da 1 a 4 termini. Non mandare il contenuto dei file.

## Come rispondere

1. Chiama `search_skills`. `tipo` è `skill` per un workflow, `rule` per una convenzione di progetto, `tutti` se servono entrambi. Se il verdetto è `nessuna skill` e la frase era lunga, riprova con meno termini. Se serve, chiama `list_collections`.
2. Per una voce già indicata, chiama `explain_entry`.
3. Rispondi in italiano. Prima il verdetto. Poi ogni voce con link, raccolta, tipo, la descrizione del catalogo e una frase sul perché, collegata a ciò che hai osservato.
4. Nella frase sul perché usa solo `descrizione` e, se c'è, `rischio`. Non aggiungere capacità che non stanno in quei campi.
5. Se la descrizione cita Composio o un'altra infrastruttura, ripetilo. Se `contiene_script` è vero dopo l'installazione, di' che i file sono stati copiati e non eseguiti.
6. Chiedi quali id installare e se l'ambito è il progetto o globale. Fermati se l'utente non lo ha già detto in modo esplicito.
7. Chiama `install_entries` solo dopo un sì. `scope` è `project` o `global`. Per il progetto passa la cartella del workspace in `project_root`.
8. Una rule con ambito globale non si installa: di' di incollarla in Customize → Rules e non passare quell'id al tool con scope global. Le skill globali vanno in `~/.cursor/skills`. Le rule di progetto vanno in `.cursor/rules`.
9. Se il tool segnala un conflitto, chiedi prima di sovrascrivere. `overwrite` true solo dopo quel secondo sì.
10. Non eseguire la skill appena installata. Non clonare le raccolte. Un link `non installabile` si riporta così com'è.

L'indice si aggiorna da solo ogni 24 ore. Non inventare voci che il tool non ha restituito.
