# Version alternative — déploiement hébergé sur Mistral Studio (Apps / Workflows)

> **Statut (05/11/2026)** : piste exploratoire (objectif de formation), **non retenue pour la
> v1**. La v1 reste l'orchestrateur Python local + cron ([conception.md](conception.md) §2) ;
> le scénario « Workflows Studio » avait été écarté en §6 (public preview à l'époque — les
> Workflows sont passés GA le 05/11/2026, les Apps restent en preview).

## 1. Objectif

Exécuter le pipeline de tri de messages **sans dépendance à la machine locale** : exécution
24/7 hébergée, déclencheurs serveur (remplacement du cron), interface web éventuelle, avec
authentification et contrôle d'accès fournis par la plateforme.

## 2. Ce que propose Studio au 05/11/2026

- **Apps** : projet déployable regroupant API **Python** + **Postgres** + agents + workflows +
  frontend optionnel, hébergé sur Mistral Cloud (auth/accès fournis). Déploiement via le Mistral
  CLI depuis un **dépôt GitHub** (`mistral init --preset app` → `mistral dev` →
  `mistral deploy`) : le code reste versionné dans git, déployé par commit — l'objection
  « orchestration externe au code » du §6 est levée sur ce point.
- **Managed agents** (Agents SDK Python, `agents deploy`) : runtime géré par Mistral, durable,
  reprise après crash.
- **Connecteurs** (dont Gmail en built-in, authentification déléguée au connecteur),
  **Secrets Manager**, **triggers/webhooks**, tracing/observabilité.
- **Contraintes** : Apps en **public preview** (API/comportement susceptibles d'évoluer) ;
  plan incluant Apps requis (hors Free).

## 3. Correspondance composant par composant

| Composant v1 (local) | Équivalent Studio |
| --- | --- |
| Orchestrateur CLI Python (`src/`), lancé sur le poste | API Python / worker de workflow de l'app, déployé par `mistral deploy` |
| cron local | triggers / webhooks Studio |
| checkpoints JSON (`data/checkpoints/`) | Postgres de l'app + reprise durable des workflows (resume après crash) |
| `logs/gmailagent.log` | logs et tracing Studio (évaluations online/offline en tier Enterprise) |
| token OAuth Gmail local (`data/gmail_token.json`) | connecteur Gmail enregistré dans Studio (consentement via le connecteur) |
| `MISTRAL_API_KEY` en variable d'environnement | inutile côté hébergé (inférence native) ; autres secrets via Secrets Manager |
| prompts + schémas stricts + allow-list `OUTILS_GMAIL` | agents Studio (Agents SDK) ou définitions d'agent du projet, versionnés dans le dépôt |
| registre de libellés `config/labels.yaml` + `config/settings.yaml` | embarqués dans le déploiement (fichiers du dépôt) |

## 4. Invariants de sécurité à re-porter dans le code (rien n'est fourni clé en main)

- validation programmatique C1–C6 (`collecter_ids_reels`, `valider_synthese`, `extraire_json`,
  empreintes recalculées) ;
- gardes : complétude de lecture (threads/messages), écart corbeille/ids, plafond anti-boucle,
  **substitution de la requête `search_threads`** par celle de l'orchestrateur (périmètre imposé
  par le code, D54) ;
- **corbeille uniquement** (`TRASH`), jamais de suppression définitive ni d'envoi ; scope
  `gmail.modify` (moindre privilège) ;
- **dry-run** (règle E) à réimplémenter explicitement dans l'app ;
- prompts versionnés avec le code (D2) ; libellés système `TRASH`/`SPAM`/`INBOX` en dur (D43).

## 5. Données, secrets, confidentialité

- Le contenu des messages transite déjà vers l'API Mistral aujourd'hui (aperçus bornés) ;
  l'hébergement ajoute un **accès serveur via le connecteur Gmail** : préférer les endpoints
  régionaux UE et le zero data retention si requis.
- Plus de token Google en local : consentement via le connecteur ; secrets restants dans le
  Secrets Manager de Studio.

## 6. Planification et état

- cron → triggers/webhooks (run de tri périodique ; run de suppression T+24h, D47) ;
- checkpoints locaux → Postgres + workflows durables ; journalisation → tracing Studio.

## 7. Risques et limites

- Apps en **public preview** au 05/11/2026 (changements d'API possibles) ; plan payant requis ;
- ce n'est **pas un copier-coller** : l'orchestration est à réécrire en composants app/workflow,
  avec toutes les gardes de sécurité à re-porter (cf. §4) ;
- le plan de tests (TU/TI) est à rejouer dans le nouvel environnement, en commençant par un
  équivalent du dry-run puis un petit périmètre réel (règle E).

## 8. Plan de migration indicatif

1. scaffolder l'app (`mistral init --preset app`), dépôt GitHub, déploiement manuel ;
2. porter prompts / schémas / agents (Agents SDK) ;
3. porter l'orchestrateur en workflow + validations et gardes (hooks pour la logique custom) ;
4. connecter le connecteur Gmail et les secrets ; supprimer le token local ;
5. mettre en place les triggers (tri périodique, suppression T+24h) ;
6. rejouer les tests : dry-run d'abord, puis petit périmètre réel.

## 9. Références

- [Apps overview — Mistral Docs](https://docs.mistral.ai/studio/apps/overview) (consulté le 05/11/2026)
- Agents SDK / managed agents, Workflows, Connectors, Secrets Manager : `docs.mistral.ai/studio`
- [conception.md](conception.md) §2 (v1 retenue) et §6 (options écartées)
