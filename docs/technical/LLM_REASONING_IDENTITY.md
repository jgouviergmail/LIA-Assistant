# LLM_REASONING_IDENTITY — écrire ce qu'un modèle accepte comme raisonnement

> **Comment l'identité de raisonnement d'un modèle du catalogue se saisit, sur les deux surfaces qui l'éditent : la fenêtre « Tarification LLM Texte » et le classeur Excel (ADR-228).**
>
> **Date** : 2026-08-24 — remplace `LLM_PRICING_TEMPLATES.md`
> **Statut** : ✅ Livré (v1.32.0)
> **Tables impactées** : `llm_models` (`is_reasoning_model`, `reasoning_enum_values`, `reasoning_doc_i18n_key`)

---

## 📖 Ce qu'il faut comprendre en premier

`reasoning_enum_values` **ne déclare pas** ce qu'un modèle sait faire. Il **retire** des profondeurs d'une échelle que le code connaît déjà.

L'échelle vient de `resolve_reasoning_profile(provider, model)` ([profiles.py](../../apps/api/src/infrastructure/llm/reasoning/profiles.py)), et la colonne ne peut que la **restreindre** — jamais l'élargir, jamais créer une famille. Trois conséquences, toutes visibles dans le code de résolution :

1. **Ça ne peut que retirer.** Déclarer `["low","medium","high"]` sur `claude-opus-4-6` retire `none` et `max` de ce que l'administrateur pourra choisir.
2. **Si aucune règle ne reconnaît le modèle, la colonne n'est pas lue** — la résolution sort avant. Faire raisonner un modèle d'une API inédite demande **du code** : une règle dans `profiles.py` et un rendu dans `translate.py`.
3. **Une déclaration qui ne recoupe rien est ignorée**, et `can_disable` n'est pas surchargeable : on ne peut pas désarmer un modèle par ce champ.

**Donc, dans l'immense majorité des cas : ne rien saisir.** La bonne question n'est pas « que supporte ce modèle ? » — le code le sait — mais « ce modèle précis refuse-t-il une profondeur que sa famille accepte en général ? ».

---

## 🖥️ Surface 1 — la fenêtre d'administration

`AdminLLMPricingSection.tsx` affiche l'échelle de la famille **en cases à cocher** et l'on décoche ce que le modèle refuse.

- La liste vient de `GET /admin/llm/reasoning-family?provider=…&model=…`, qui résout le couple avec **la même fonction** que le traducteur et le validateur d'écriture. Ce que le formulaire propose ne peut donc pas diverger de ce que l'API accepte (doctrine ADR-184 appliquée au raisonnement).
- **Tout coché ne stocke rien** : « pas de restriction » et « restreint à tout » sont la même chose pour le résolveur, et la valeur vide survit au jour où la famille gagne une profondeur.
- **Un modèle sans famille est annoncé comme tel**, au lieu d'une liste vide qui ressemblait à un bug.
- L'endpoint résout **sans** la restriction du catalogue : sinon une restriction enregistrée serait impossible à élargir, le formulaire n'offrant plus que ce qu'elle laisse.

## 📗 Surface 2 — le classeur Excel (ADR-228)

Deux colonnes éditables portent la même chose, plus une troisième en lecture seule :

| Colonne | Rôle |
|---|---|
| `is_reasoning_model` | booléen — ce modèle raisonne-t-il ? |
| `reasoning_enum_values` | texte, profondeurs séparées par des virgules. Vide = pas de restriction |
| `reasoning_shape` | **lecture seule** — la famille résolue et l'échelle que le runtime acceptera |

Une feuille de calcul ne sait pas afficher de cases à cocher : la garantie équivalente est **à l'import**. `_check_reasoning_ladder` refuse une profondeur que la famille ne propose pas et **nomme celles qui l'auraient été** (`reasoning_level_unknown`). Sur un modèle qu'aucune règle ne reconnaît, il ne dit rien : la valeur y est inerte, pas fausse, et `reasoning_shape` l'annonce déjà.

`SCHEMA_VERSION` est passée à **2** : un fichier écrit avant nomme une colonne qui n'existe plus et n'offre aucun moyen d'exprimer l'échelle.

---

## ⚠️ Effacer une restriction : pourquoi un drapeau

Élargir une échelle déjà restreinte ne peut pas voyager comme un `null` : le service construit son jeu de changements avec `exclude_none`, donc la valeur serait **jetée en route** et l'ancienne restriction survivrait. `clear_reasoning_enum_values` porte l'intention, exactement comme `clear_cached_input_price` le fait pour un prix vidé.

C'est la même règle que l'ADR-245 énonce ailleurs : **un réglage incapable d'exprimer sa propre valeur par défaut est un réglage cassé.**

---

## 🗑️ Ce qui a disparu, et pourquoi

Un mécanisme de **gabarits** occupait cette place : « ce nouveau modèle se comporte comme tel modèle existant », et le service copiait l'identité. Il avait un sens quand la forme du raisonnement tenait en quatre colonnes fragiles. Après l'ADR-245 il ne copiait plus que deux champs, et il portait un défaut que rien ne montrait : **un gabarit regroupe les modèles par leur échelle STOCKÉE, pas par famille**, donc en copier un d'une autre famille retirait des profondeurs en silence.

Il exigeait aussi un gabarit **pour créer un modèle qui ne raisonne pas** (`CREATION_NEEDS_TEMPLATE`), faute d'autre canal d'écriture dans le classeur.

Ont disparu avec lui : `GET /admin/llm/reasoning-templates`, `LLMModelService.list_templates` / `_fingerprint` / `_copy_from_template_row` / `_render_template_description`, `UnknownReasoningTemplateError`, le champ `reasoning_template` des schémas et son validateur XOR, la colonne `reasoning_template` du classeur et son référentiel `TEMPLATE`.

---

## 🧪 Tests

| Niveau | Fichier | Couverture |
|---|---|---|
| Endpoint (sans DB) | `tests/unit/domains/llm/test_reasoning_family_endpoint.py` | l'échelle publiée est celle que le runtime résout ; famille inconnue annoncée ; bornes de budget de la famille |
| Élargissement | `tests/unit/domains/llm/test_reasoning_ladder_clearing.py` | un `null` est jeté en route ; le drapeau survit ; les deux à la fois sont refusés |
| Classeur | `tests/unit/domains/llm/test_pricing_change_plan.py` | profondeur hors famille refusée par son nom ; modèle non raisonnant créable ; modèle sans famille laissé tranquille |
| Export | `tests/unit/domains/llm/test_pricing_sheet_rows.py` | l'échelle voyage telle qu'elle s'édite ; vide quand rien n'est restreint |
| Formulaire | `apps/web/src/components/settings/__tests__/ModelPricingModal.test.tsx` | cases sur l'échelle de la famille ; effacement plutôt que `null` ; famille inconnue annoncée |

---

## 🔗 Références

- [ADR-245 — une intention de raisonnement, un traducteur](../architecture/ADR-245-Reasoning-Unification.md)
- [ADR-228 — import/export tabulaire](../architecture/ADR-228-Import-Export-Tabulaire-Administration.md)
- [LLM_CONFIG_ADMIN.md](./LLM_CONFIG_ADMIN.md) — la configuration par agent, qui consomme cette identité
- [TABULAR_ADMIN_IO.md](./TABULAR_ADMIN_IO.md) — le socle du classeur
