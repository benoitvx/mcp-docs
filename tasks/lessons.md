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
