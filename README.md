# Pipeline CRM Optivie, Livrable 4 (Groupe 7)

Maquette du funnel redessine au Livrable 3, rendue vivante avec les vraies donnees
du dataset 2025. Demonstrateur de ce qu'on parametrerait ensuite dans HubSpot.

## Demo en ligne

https://pipeline-crm-optivie-boy5mbcymapswkwjbgmjwj.streamlit.app/

Sur l'offre gratuite, l'app se met en veille apres inactivite et se reveille en
quelques secondes au premier acces.

## Lancer en local (uv)

```bash
uv sync
uv run streamlit run app.py
```

L'app s'ouvre dans le navigateur. En local, tout tourne sans connexion.

## Contenu

- `app.py`, l'application, organisee en quatre couches separees de l'affichage.
- `pyproject.toml`, dependances pour l'environnement local (streamlit, pandas, openpyxl).
- `requirements.txt`, dependances pour le deploiement Streamlit Cloud (installe avec pip).
- `Optivie_Dataset.xlsx`, le dataset du cas, lu au demarrage.
- `.streamlit/config.toml`, theme sobre, accent bleu.

## Ce que fait l'application

Deux onglets.

Onglet Pipeline. Un board kanban des six etapes du funnel, chaque lead range d'apres
son activite reelle, l'etape devis venant de l'action Devis envoye du Journal. En haut,
quatre chiffres cles. Une barre laterale de filtres (courtier, canal, priorite, etape,
nombre de relances, delai de premier contact, hors CRM) avec un bouton pour tout
reinitialiser. Chaque colonne peut etre depliee pour afficher tous ses leads.

Onglet Performance equipe. Quatre vues au choix : cartes par courtier, matrice a bulles,
barres par canal, et une vue recommandation avec les actions a mener. Lecture a canal
constant pour ne pas confondre la performance avec le simple effet d'allocation.

## Logique (verrouillee ensemble)

Perimetre acquisition uniquement (feuilles Leads et Journal).

Regle de priorite sur les leads en cours :
- Haute, les leads qui glissent : recommandation, pas encore au devis, et delai de
  premier contact superieur a 12h ou jamais relance. Tri par retard decroissant.
- Moyenne : le reste de la recommandation en cours.
- Rapide : comparateurs et prospection, sans surinvestir.

Allocation : pour un lead prioritaire, suggestion d'orientation vers le meilleur
convertisseur de recommandation visible dans le CRM, avec alerte sur l'angle mort hors CRM.

Tous les chiffres sont calcules depuis le dataset, aucun n'est inscrit en dur.
