# Todo — Fix pérenne de l'expiration de session

## Contexte

Le 14/08/2026, tous les tools `docs_*` renvoyaient `Authentication failed`. Deux causes
distinctes, qui se cumulent :

1. **Le cookie pourrit sans que rien ne le renouvelle.** Le plist launchd documenté dans le
   README (section « Rafraîchissement automatique ») n'a jamais été installé. Dernier cookie
   obtenu le 10/06/2026, expiré depuis ~2 mois.
2. **Le serveur MCP ne voit pas un cookie rafraîchi.** `DocsClient.__init__` lit le cookie une
   seule fois et le fige dans le jar httpx (`client.py:82`). Après un
   `mcp-docs-refresh-session` réussi, le serveur continue d'envoyer l'ancien cookie jusqu'à
   redémarrage complet — d'où le 401 persistant alors que `curl` avec le nouveau cookie
   répond 200.

Corriger (1) seul laisse une fenêtre où il faut redémarrer le serveur à la main.
Corriger (2) seul ne renouvelle toujours rien. Il faut les deux.

## Plan

### A. Hot-reload du cookie sur 401 (code)

- [ ] Exposer `resolve_session_file()` dans `config.py` (aujourd'hui `_resolve_session_file`),
      et supprimer le doublon `_session_file()` de `session_refresh.py`
- [ ] `DocsClient` : mémoriser le chemin du fichier de session, uniquement quand il est
      « rechargeable » — mode `session` **et** `DOCS_SESSION_COOKIE` non défini (l'env explicite
      reste prioritaire, conformément à la précédence documentée dans `load_config`)
- [ ] Ajouter `_reload_session_cookie() -> bool` : relit le fichier, met à jour le jar httpx,
      renvoie `True` seulement si la valeur a réellement changé (évite toute boucle)
- [ ] Factoriser `_get/_post/_patch/_put/_delete` sur un `_send(method, url, **kwargs)` commun
      qui, sur HTTP 401, tente le reload puis rejoue la requête **une seule fois**
- [ ] Vérifier que le rejeu est sûr : un 401 est rejeté avant tout effet de bord, et les corps
      multipart sont des `bytes` (pas des file objects consommés) → rejouable

### B. Rafraîchissement automatique (infra)

- [ ] Générer `~/Library/LaunchAgents/mcp-docs.refresh.plist` à partir du modèle README,
      avec les chemins absolus réels (`which uv`, chemin du repo)
- [ ] `launchctl load` + vérifier que le job apparaît dans `launchctl list`
- [ ] Déclencher un run immédiat (`launchctl kickstart`) et confirmer via les logs
      que le fast-path « Session still valid » est bien pris

### C. Tests & vérif

- [ ] Test respx : 401 puis 200 après réécriture du fichier de session → la requête aboutit
- [ ] Test respx : 401 persistant → une seule tentative de reload, l'erreur remonte
- [ ] Test : mode `DOCS_SESSION_COOKIE` (env) → aucun reload tenté
- [ ] `uv run pytest`, `uv run ruff check .`, `uv run pyright` au vert
- [ ] Reconnecter le MCP et valider `docs_get_me` en conditions réelles

### D. Doc

- [ ] README : documenter le hot-reload (plus besoin de redémarrer le serveur après refresh)
- [ ] CLAUDE.md : noter le comportement dans la section Configuration
- [ ] `tasks/lessons.md` : ajouter le pattern « credential figé à la construction du client »

## Limite connue (à assumer)

Le refresh headless ne marche que tant que la session SSO ProConnect vit encore dans le profil
Chromium persistant. Quand elle meurt pour de bon, une ré-authentification interactive reste
nécessaire — c'est le rôle de la notification macOS déjà implémentée dans `session_refresh.py`.
Ce plan réduit la fréquence des interventions manuelles, il ne les supprime pas. La vraie
suppression, c'est la migration OIDC vers `/external_api/v1.0/`.

## Résultat

Tout le plan est fait. 189 tests au vert (180 avant → +9), ruff clean.

**A. Hot-reload** — `DocsClient._send` centralise les cinq verbes HTTP, relit le fichier de
session sur 401 et rejoue une fois si le cookie a changé. Les deux appels qui contournaient les
helpers (`_markdown_to_yjs_base64`, `update_document_content`) passent aussi par `_send`, donc
bénéficient du rechargement. `resolve_session_file()` est mutualisée entre `config.py` et
`session_refresh.py` (le doublon `_session_file()` a disparu).

**Bug trouvé par le test end-to-end, invisible en unitaire** : l'API renvoie son propre
`Set-Cookie: docs_sessionid`, donc le jar httpx contient plusieurs cookies homonymes et
`cookies.get("docs_sessionid")` lève `CookieConflict`. Le client suit désormais sa propre valeur
dans `self._session_cookie` au lieu de relire le jar, et `_set_session_cookie` purge les
doublons avant d'écrire. Test de régression ajouté.

**B. launchd** — `~/Library/LaunchAgents/mcp-docs.refresh.plist` installé et chargé
(`launchctl list` → exit 0, fast-path « Session still valid »). Le modèle du README était
incomplet : sans `--extra browser`, `uv run` résout un environnement sans Playwright et le job
n'échoue qu'au premier vrai refresh. Corrigé dans le README. `UV_PROJECT_ENVIRONMENT=/tmp/...`
retiré : `~/Documents` n'est pas synchronisé iCloud ici, le `.venv` du repo convient.

**C. Tests** — 9 tests couvrant : adoption + rejeu, rejeu unique (pas de boucle), cookie
inchangé, fichier absent, fichier malformé, cookie épinglé par l'env, mode OIDC, POST multipart,
et le cas `Set-Cookie` dupliqué. Vérifiés par mutation : les 4 tests qui portent sur le
rechargement échouent bien si on le désactive.

**Validation réelle** — client construit avec un cookie périmé + fichier de session valide →
`401` → `Adopted refreshed session cookie` → `get_me()` et `get_document_content()` réussissent
contre l'API de production.

### Reste à faire côté utilisateur

Reconnecter le serveur MCP (`/mcp` en terminal interactif, ou relancer l'app) : le process en
cours tourne encore sur l'ancien code **et** l'ancien cookie. C'est la dernière fois que ce
redémarrage manuel est nécessaire.

### Hors périmètre, repéré au passage

`session_refresh.py:114` — erreur pyright pré-existante (`c["value"]` sur un TypedDict où
`value` n'est pas requis), identique sur `main`. Non touchée.
