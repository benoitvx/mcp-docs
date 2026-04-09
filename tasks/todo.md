# Todo — Prochaines étapes

## P0 — Migration auth OIDC

- [ ] Migrer le client vers `/external_api/v1.0/` avec auth OIDC Bearer token
- [ ] Intégrer ProConnect (authorization_code flow) pour obtenir le token
- [ ] Supprimer le hack CSRF (plus nécessaire avec Bearer token)
- [ ] Mettre à jour les tests et la doc

Ref : issue [suitenumerique/docs#1703](https://github.com/suitenumerique/docs/issues/1703), PR [#1923](https://github.com/suitenumerique/docs/pull/1923)

## P1 — Fonctionnalités

- [ ] Implémenter `docs_list_children` (lister les sous-documents)
- [ ] Suivre le token exchange (@jmaupetit, La Suite)

## P2 — Qualité

- [ ] Ajouter le pre-commit hook gitleaks (`uv run pre-commit install`)
- [ ] Configurer le repo GitHub (branch protection, required checks)
