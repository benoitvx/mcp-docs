# Lessons Learned

## Django CSRF avec session auth

**Erreur** : POST sur l'API Docs retourne 403 "CSRF cookie not set".
**Cause** : Django exige un cookie `csrftoken` + header `X-CSRFToken` + header `Referer` pour les POST avec auth par cookie de session. L'API ne renvoie jamais le cookie CSRF.
**Solution** : Générer un token de 64 chars côté client (`secrets.token_hex(32)`), l'injecter comme cookie et header.

## Cookie de session Docs

**Erreur** : Auth échoue avec le cookie `sessionid`.
**Cause** : Le cookie s'appelle `docs_sessionid`, pas `sessionid`.
**Règle** : Toujours vérifier le nom exact du cookie dans le navigateur (DevTools > Application > Cookies).

## uv sync casse le .venv sur iCloud

**Erreur** : `ModuleNotFoundError: No module named 'mcp_docs'` après `uv sync`.
**Cause** : `~/Dev` est un symlink vers iCloud. `uv` mélange les chemins réels et symlinks.
**Solution** : `rm -rf .venv && uv venv && uv sync` puis relancer Claude Code.

## pip audit vs pip-audit

**Erreur** : CI échoue avec `unknown command "audit"`.
**Cause** : `pip audit` n'existe pas — la commande est `pip-audit` (package séparé).
**Règle** : `pip-audit` est un outil standalone, pas une sous-commande pip.

## Credential figé à la construction du client

**Erreur** : après un `mcp-docs-refresh-session` réussi, les tools MCP renvoyaient toujours
`Authentication failed`, alors qu'un `curl` avec le même cookie répondait 200.
**Cause** : `DocsClient.__init__` lisait le cookie une seule fois et le figeait dans le jar
httpx. Un process long-vivant ne voit jamais un credential renouvelé hors de lui.
**Règle** : tout credential lu depuis un fichier réécrit par un autre process doit être
rechargeable à chaud. Recharger sur le code d'erreur d'auth (401) et rejouer une seule fois,
en conditionnant le rejeu au fait que la valeur a réellement changé — ça borne la boucle.

## Un plist launchd documenté n'est pas un plist installé

**Erreur** : cookie expiré depuis ~2 mois alors que le README documentait un refresh horaire.
**Cause** : le plist n'avait jamais été chargé (`launchctl list` vide).
**Règle** : vérifier `launchctl list | grep <label>` avant de conclure qu'une automatisation
tourne. Et tester la commande du plist en env minimal (`env -i HOME=... PATH=/usr/bin:/bin`)
avant de l'installer — un `uv run` sans `--extra browser` résout un environnement sans
Playwright et n'échoue qu'au moment où un vrai refresh devient nécessaire.

## `/documents/{id}/tree/` n'est pas récursif

**Erreur** : conçu une découverte d'arbre en un appel, en croyant que `/tree/` renvoyait le
sous-arbre complet du document demandé.
**Cause** : `/tree/` renvoie l'arbre de la **racine ancestrale**, avec seulement le chemin vers
le document demandé déplié. Les nœuds frères arrivent avec `children: []` alors que leur
`numchild` est non nul — c'est le endpoint qui alimente la sidebar, pas un dump d'arbre.
Le premier test semblait valider l'hypothèse par coïncidence : sur un document à 52 enfants
directs et 0 petit-enfant, les 53 nœuds renvoyés correspondaient à l'arbre complet.
**Règle** : vérifier une hypothèse de récursivité sur un arbre d'au moins 3 niveaux. Ici la
découverte se fait avec `/children/`, niveau par niveau. `/descendants/` renvoie 404 en prod
malgré `abilities.descendants: true`, et la liste plate `/documents/` ne contient que les
documents à accès direct — ni l'un ni l'autre ne remplace la descente récursive.

## respx réutilise le même objet Route pour un motif déjà enregistré

**Erreur** : deux tests asseyant `assert not route.called` échouaient alors que le code était
correct — ils réenregistraient les routes entre deux exécutions de la fonction testée.
**Cause** : `respx.get(...).mock(...)` sur un motif déjà connu renvoie l'objet `Route`
existant. Son compteur d'appels garde donc les appels du premier passage.
**Règle** : dans un test qui exécute deux fois le même flux, comparer un delta de
`route.call_count` plutôt qu'un booléen `route.called`.

## Rate limit de l'API Docs sur une sync d'arbre

**Erreur** : enchaîner deux synchronisations complètes de 129 documents (~300 requêtes en
20 s) déclenche un `429` que les 3 retries du client n'absorbent pas.
**Règle** : une sync d'arbre est proche du plafond. Espacer les racines dans une routine qui
en synchronise plusieurs, plutôt que de les lancer en rafale.

## Le connecteur `vault` casse si sa version n'est pas épinglée

**Erreur** : dans une session Cowork, tous les tools `mcp__vault__*` échouaient avec
`Tool '…' has an invalid outputSchema: JSON Schema declares an unsupported dialect
("$schema": "http://json-schema.org/draft-07/schema#")`. Symptôme trompeur : ça ressemble à
un problème de chemin ou de droits sur le vault, alors qu'aucun tool n'est appelable.
**Cause** : les configs déclaraient `npx -y @modelcontextprotocol/server-filesystem` **sans
version**, donc `latest`. Depuis `2025.11.25`, ce serveur expose un `outputSchema` sur ses 14
tools, généré par `zod-to-json-schema` qui émet du draft-07 ; l'hôte MCP ne valide qu'en
2020-12 et rejette tout. La dernière version sans `outputSchema` est `2025.8.21`.
**Règle** : épingler la version de tout serveur MCP lancé via `npx -y` — sinon une release
amont casse l'intégration sans qu'on ait rien changé. Épinglé dans les trois configs :
`~/.claude/settings.json`, `~/.claude.json`, et
`~/Library/Application Support/Claude/claude_desktop_config.json`.
**Contournement** : `docs_sync_tree` écrit dans le vault via `DOCS_VAULT_PATH` sans passer par
le connecteur `vault` — il reste utilisable même quand `vault` est cassé.
