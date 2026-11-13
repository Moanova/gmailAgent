# Contrat canonique — agents (prompts, outils, schémas de sortie)

Source de vérité du code : `src/gmailagent/agent_runner.py` (runner `lancer_conversation`),
`src/gmailagent/agent_prompts.py` (prompts + allow-list d'outils), `src/gmailagent/agent_contracts.py` (schémas stricts).

## Principes

- **Conversations éphémères** (décision D2) : prompt + outils + schéma de sortie passés à
  chaque appel ; configuration versionnée avec le code. L'orchestrateur est le seul médiateur.
- **Trois agents** : `classification`, `spam`, `suppression` (constantes `AGENT_*` de
  `src/gmailagent/agent_contracts.py`).
- **Aucun libellé physique en dur** : les libellés sont injectés depuis le registre
  `config/labels.yaml` (clés logiques), jamais de nom `Agent/...` dans les prompts.
- **Allow-list d'outils** (`OUTILS_GMAIL`, moindre privilège) : `search_threads`,
  `get_thread`, `get_message`, `label_message`, `list_labels`. Aucun outil d'envoi ni de
  suppression définitive.
- **Périmètre de recherche imposé par le code** (D54) : la requête exécutée par
  `search_threads` est toujours celle fournie par l'orchestrateur (substitution journalisée
  sinon).
- **Schémas de sortie stricts** (`strict: true`) construits dynamiquement depuis le registre
  : enums `statut`, `categorie` (clés `classification.*`), `urgence` —
  `contracts.schema_agent` / `response_format_agent`.
- **Boucle bornée** : garde-fou anti-boucle `plafond_appels_outils` (50), cap de
  `search_threads` dérivé du budget (D58).
- **Sampling configurable** (T9.11) : `modele.temperature` / `modele.top_p` dans
  `config/settings.yaml` (défauts 0.0 / 1.0 — règle glouton : `temperature=0` exige `top_p=1`, code
  API 3054, imposé strictement par ex. `mistral-large-latest`), passés explicitement à chaque appel
  et journalisés dans `conversation lancee`.
- **Contenu en chunks** (T9.11) : `message.content` peut être une liste de chunks (modèles récents
  à raisonnement, ex. `mistral-large-latest`) ; `_contenu_texte` ne retient que les chunks
  `type="text"` (le raisonnement `thinking` est ignoré).
- **Refus renvoyés au modèle** via `_refuser` (erreurs d'outils en `ToolMessage`, gardes de
  complétude et synthèses invalides en `UserMessage`), compteur `max_tentatives_synthese`
  avant abandon propre. Voir [validation.md](validation.md) pour C1–C6.
- **Court-circuit** : `search_threads` à 0 thread → synthèse `aucun_message` sans appel au
  modèle.
