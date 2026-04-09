## Audit Sécurité ANSSI — Rapport de conformité

**Date :** 2026-04-09
**Périmètre audité :** mcp-docs — Serveur MCP local (stdio) pour l'API Docs (La Suite numérique)
**Résultat global :** 20/28 règles conformes (71% conforme)
(20 conformes, 2 non conformes, 2 partielles, 4 non applicables)

---

### Tableau de synthèse

| # | Domaine | Statut | Détail |
|---|---------|--------|--------|
| 1 | TLS / HTTPS | OK | Appels HTTPS vers docs.numerique.gouv.fr, pas de serveur HTTP exposé |
| 2 | Gestion des secrets | Partiel | Secrets via env vars, `.env` et `.mcp.json` dans `.gitignore`, mais pas de rotation ni de détection de fuite |
| 3 | Authentification et contrôle d'accès | OK | Auth déléguée à l'API Docs, moindre privilège respecté |
| 4 | Headers de sécurité HTTP | NA | Pas de serveur HTTP exposé (transport stdio) |
| 5 | Validation des entrées | OK | Toutes les entrées validées côté serveur dans `tools.py` |
| 6 | Gestion des dépendances | Partiel | Lock file (`uv.lock`) généré, mais pas d'audit automatisé (CI manquant) |
| 7 | Journalisation et monitoring | KO | Aucun logging implémenté |
| 8 | Protection des API | OK | Pagination, messages d'erreur safe, auth sur tous les endpoints |
| 9 | Sécurité des conteneurs et du déploiement | NA | Application locale, pas de conteneur ni déploiement serveur |
| 10 | Sécurité du poste de développement | NA | Hors périmètre code (responsabilité utilisateur) |
| 11 | Sauvegarde et continuité | NA | Application locale sans données persistantes |
| 12 | Gestion des incidents | KO | Pas de procédure de signalement ni de rotation d'urgence documentée |

---

### Non-conformités détectées

**[KO] Domaine 7 — Journalisation et monitoring**
- **Règle concernée :** Logger les événements de sécurité (erreurs d'auth, erreurs d'accès)
- **Constat :** Aucun appel `logging` dans le code. Les erreurs HTTP sont converties en messages utilisateur mais pas loggées côté serveur.
- **Risque :** Impossible de diagnostiquer des problèmes d'auth, des abus, ou des erreurs récurrentes.
- **Correction :** Ajouter `import logging` et logger les erreurs HTTP (sans données sensibles) dans `_error_response()` et dans le lifespan. Utiliser `logging.getLogger(__name__)`.
- **Priorité :** 🟠 Élevée

**[KO] Domaine 12 — Gestion des incidents**
- **Règle concernée :** Procédure de signalement documentée, capacité à révoquer des accès en urgence
- **Constat :** Pas de documentation sur la marche à suivre en cas de fuite du cookie de session ou du token OIDC.
- **Risque :** Temps de réaction allongé en cas d'incident.
- **Correction :** Ajouter une section "Sécurité / Incident" dans le README avec les étapes : révoquer la session ProConnect, supprimer le cookie des env vars, contacter le CERT.
- **Priorité :** 🟡 Modérée

### Conformités partielles

**[Partiel] Domaine 2 — Gestion des secrets**
- **Règles respectées :**
  - Aucun secret dans le code source
  - Secrets chargés via variables d'environnement (`os.environ.get`)
  - `.env` et `.mcp.json` dans `.gitignore`
  - Messages d'erreur sans fuite de secrets (pas de `repr()` du cookie/token)
- **Règles manquantes :**
  - Pas de scan de secrets dans le repo (ex: `gitleaks`, `trufflehog`)
  - Pas de politique de rotation documentée
- **Correction :** Ajouter `gitleaks` en pre-commit hook. Documenter la rotation des cookies de session (expiration ProConnect).
- **Priorité :** 🟡 Modérée

**[Partiel] Domaine 6 — Gestion des dépendances**
- **Règles respectées :**
  - Lock file `uv.lock` généré par `uv sync`
  - Nombre minimal de dépendances directes (2 runtime : `mcp`, `httpx`)
  - Versions minimales spécifiées
- **Règles manquantes :**
  - Pas de CI/CD avec audit automatique (`pip audit`, `trivy`)
  - Pas de Dependabot / Renovate configuré
- **Correction :** Ajouter un workflow GitHub Actions avec `uv run pip audit` et activer Dependabot.
- **Priorité :** 🟡 Modérée

---

### Domaines conformes

- **1. TLS / HTTPS** — Communication HTTPS uniquement vers `docs.numerique.gouv.fr`, httpx vérifie les certificats par défaut.
- **3. Authentification et contrôle d'accès** — Auth déléguée à l'API Docs (cookie session / OIDC). Le serveur MCP tourne en local (stdio), pas d'accès réseau entrant. Moindre privilège : seuls les endpoints nécessaires sont appelés.
- **5. Validation des entrées** — Toutes les entrées utilisateur validées dans `tools.py` : `page >= 1`, `page_size` borné 1-100, `content_format` whitelisté, `document_id` non vide, `query` non vide, `title` et `markdown_content` non vides.
- **8. Protection des API** — Pagination implémentée sur `list_documents` et `search_documents`. Messages d'erreur génériques sans détails internes (`_error_response`). API versionnée (`/api/v1.0/`). Auth requise sur tous les endpoints.

### Domaines non applicables

- **4. Headers de sécurité HTTP** — Le serveur MCP communique via stdio, pas de serveur HTTP exposé.
- **9. Sécurité des conteneurs** — Application locale, pas de conteneurisation à ce stade.
- **10. Sécurité du poste** — Responsabilité de l'utilisateur, hors périmètre du code.
- **11. Sauvegarde et continuité** — Pas de données persistantes côté serveur MCP.
