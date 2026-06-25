# Pipeline CRM Optivie — Livrable 4 (Groupe 7)

Maquette du funnel redessine au Livrable 3, rendue vivante avec les vraies donnees
du dataset 2025. Demonstrateur de ce qu'on parametrerait ensuite dans HubSpot.

## Lancer en local (uv)

```bash
uv sync
uv run streamlit run app.py
```

L'app s'ouvre dans le navigateur. Tout tourne en local, aucune connexion requise.

## Contenu

- `app.py` — l'application, organisee en quatre couches separees de l'affichage.
- `pyproject.toml` — dependances (streamlit, pandas, openpyxl).
- `Optivie_Dataset.xlsx` — le dataset du cas, lu en local.
- `.streamlit/config.toml` — theme sobre, accent bleu.

## Logique (verrouillee ensemble)

Perimetre acquisition uniquement (feuilles Leads et Journal).

Regle de priorite sur les leads en cours :
- Haute, les leads qui glissent : recommandation, pas encore au devis, et delai de
  premier contact superieur a 12h ou jamais relance. Tri par retard decroissant.
- Moyenne : le reste de la recommandation en cours.
- Rapide : comparateurs et prospection, sans surinvestir.

Allocation : pour un lead prioritaire, suggestion d'orientation vers le meilleur
convertisseur de recommandation visible dans le CRM, avec alerte sur l'angle mort hors CRM.

Onglet Performance equipe : force par courtier et par canal, lue a canal constant.

Tous les chiffres sont calcules depuis le dataset, aucun n'est inscrit en dur.
