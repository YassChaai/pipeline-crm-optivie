"""
Pipeline CRM Optivie - Livrable 4 (prototype fonctionnel)
Groupe 7 - Promotion 2026

Maquette du funnel redessine au Livrable 3, rendue vivante avec les vraies
donnees du dataset. Perimetre acquisition uniquement (feuilles Leads et Journal).

Lancement local :
    uv sync
    uv run streamlit run app.py

Architecture en quatre couches, separees de l'affichage :
    1. Chargement et preparation des donnees
    2. Placement de chaque lead dans une etape du funnel
    3. Regle de priorite et suggestion d'allocation
    4. Affichage Streamlit (fonction main)

Chaque chiffre affiche est calcule depuis le dataset, jamais en dur.
"""

from pathlib import Path
import pandas as pd
import numpy as np
import altair as alt
import streamlit as st

# --------------------------------------------------------------------------
# Constantes du cas (coherence inter-livrables)
# --------------------------------------------------------------------------
DATA_PATH = Path(__file__).parent / "Optivie_Dataset.xlsx"
COMMISSION = 152          # commission recurrente moyenne par contrat (dataset)
SLA_LENT_H = 12           # seuil de delai au-dela duquel un lead reco est lent
CARTES_PAR_COLONNE = 12   # plafond d'affichage par colonne (les comptes restent complets)
CANAUX = ["Recommandation", "Comparateurs", "Prospection"]

STAGES = [
    "Reception et tri",
    "Attribution",
    "Contact et qualification",
    "Devis",
    "Relance cadencee",
    "Signature et saisie",
]

NOTES_CONTEXTE = {"Budget valide", "Tres interesse", "Decision sous 1 mois",
                  "Rappeler dans 2 semaines", "Injoignable", "Compare avec MAAF"}


# ==========================================================================
# COUCHE 1 - Chargement et preparation
# ==========================================================================
def charger_donnees():
    """Lit les feuilles Leads et Journal, recale les en-tetes, rattache
    l'activite a chaque lead. Ne decide rien, produit des tables propres."""
    leads = pd.read_excel(DATA_PATH, sheet_name="📋 Leads", header=2)
    leads = leads.dropna(how="all").reset_index(drop=True)
    jour = pd.read_excel(DATA_PATH, sheet_name="📓 Journal", header=2)
    jour = jour.dropna(how="all").reset_index(drop=True)

    # Regroupement des sources en trois canaux
    leads["canal"] = leads["Source"].replace({
        "Assurland": "Comparateurs",
        "LesFurets": "Comparateurs",
        "Prospection directe": "Prospection",
    })
    leads["delai_h"] = pd.to_numeric(leads["Délai contact h"], errors="coerce")
    leads["Nb relances"] = pd.to_numeric(leads["Nb relances"], errors="coerce").fillna(0).astype(int)

    # Signaux tires du Journal, rattaches par ID lead
    a_un_devis = set(jour.loc[jour["Type action"] == "Devis envoyé", "ID lead"])
    leads["a_devis"] = leads["ID lead"].isin(a_un_devis)

    # Derniere activite connue (pour le contexte affiche sur la carte)
    jour = jour.copy()
    jour["_d"] = pd.to_datetime(jour["Date"], format="%d/%m/%Y", errors="coerce")
    last = (jour.sort_values("_d").groupby("ID lead").tail(1)
                .set_index("ID lead")[["Type action", "Résultat", "Note"]])
    leads = leads.join(last, on="ID lead")

    return leads, jour


def conversion(df):
    """Taux de conversion sur leads aboutis (convertis / convertis + perdus)."""
    ab = df[df["Statut lead"].isin(["Converti", "Perdu"])]
    if len(ab) == 0:
        return np.nan, 0, 0
    c = int((ab["Statut lead"] == "Converti").sum())
    return 100 * c / len(ab), c, len(ab)


# ==========================================================================
# COUCHE 2 - Placement dans une etape du funnel
# ==========================================================================
def placer_etape(row):
    """Range un lead dans une des six etapes, d'apres son statut et son
    activite reelle. Le devis vient du Journal, pas d'une supposition."""
    if row["Statut lead"] == "Converti":
        return "Signature et saisie"
    # Lead en cours : on s'appuie sur la presence d'un devis et des relances
    if row["a_devis"]:
        return "Relance cadencee" if row["Nb relances"] >= 1 else "Devis"
    return "Contact et qualification"


# ==========================================================================
# COUCHE 3 - Regle de priorite et allocation
# ==========================================================================
def prioriser(row):
    """Applique la regle verrouillee avec El-M3allem.
    Haute  : reco, en cours, pas encore au devis, et (delai > 12h ou jamais relance)
    Moyenne: le reste de la recommandation en cours
    Rapide : comparateurs et prospection en cours
    """
    if row["Statut lead"] != "En cours":
        return "Historique"
    if row["canal"] == "Recommandation":
        pas_au_devis = not row["a_devis"]
        glisse = (row["delai_h"] > SLA_LENT_H) or (row["Nb relances"] == 0)
        if pas_au_devis and glisse:
            return "Haute"
        return "Moyenne"
    return "Rapide"


def prochaine_action(row):
    """Action conseillee, deduite de la priorite et de l'etat du lead."""
    if row["priorite"] == "Haute":
        if row["Nb relances"] == 0:
            return "Relancer maintenant, jamais relance"
        return "Reprendre vite, contact tardif"
    if row["priorite"] == "Moyenne":
        if row["a_devis"]:
            return "Pousser le devis vers la signature"
        return "Maintenir le suivi"
    if row["priorite"] == "Rapide":
        return "Traiter en mode rapide, sans surinvestir"
    return ""


def suggestion_allocation(leads):
    """Choisit, depuis les donnees, le meilleur convertisseur de recommandation
    a la fois dans le CRM et sous-alimente, et signale l'angle mort hors CRM."""
    reco = leads[leads["canal"] == "Recommandation"]
    perf = {}
    crm = {}
    charge = {}
    for b in reco["Courtier attribué"].unique():
        d = reco[reco["Courtier attribué"] == b]
        r, _, _ = conversion(d)
        perf[b] = r
        crm[b] = (d["Dans CRM"] == "Oui").mean() if "Dans CRM" in d else 1.0
        charge[b] = len(leads[leads["Courtier attribué"] == b])
    # Meilleur convertisseur dans le CRM (visible), le moins charge a egalite d'esprit
    dans_crm = {b: p for b, p in perf.items() if crm.get(b, 0) >= 0.5}
    cible = max(dans_crm, key=dans_crm.get) if dans_crm else max(perf, key=perf.get)
    # Angle mort : meilleur convertisseur hors CRM
    hors_crm = {b: p for b, p in perf.items() if crm.get(b, 0) < 0.5}
    angle_mort = max(hors_crm, key=hors_crm.get) if hors_crm else None
    return cible, perf.get(cible), charge.get(cible), angle_mort, perf.get(angle_mort)


def prep_equipe(leads):
    """Prepare les donnees de l'onglet equipe : une table longue courtier x canal
    (taux, convertis, aboutis, leads) et des meta par courtier (total leads, part
    CRM). A canal constant, conversion sur leads aboutis. Rien en dur."""
    courtiers = leads["Courtier attribué"].value_counts().index.tolist()
    lignes, meta = [], {}
    for b in courtiers:
        d = leads[leads["Courtier attribué"] == b]
        part_crm = (d["Dans CRM"] == "Oui").mean() if "Dans CRM" in d else 1.0
        meta[b] = {"leads": len(d), "crm": part_crm}
        for canal in CANAUX:
            r, c, n = conversion(d[d["canal"] == canal])
            if n > 0:
                lignes.append({"Courtier": b, "Canal": canal, "Taux": round(r, 1),
                               "Convertis": c, "Aboutis": n,
                               "Leads": int((d["canal"] == canal).sum())})
    return pd.DataFrame(lignes), meta, courtiers


# ==========================================================================
# COUCHE 4 - Affichage
# ==========================================================================
CSS = """
<style>
/* ---- Cadre general ---- */
[data-testid="stHeader"] {background:transparent;}
[data-testid="stAppDeployButton"] {display:none;}
.stApp {background:#F4F6F9;}
.block-container {padding-top:2.4rem; padding-bottom:2rem; max-width:1580px;}
[data-testid="stSidebar"] {background:#FFFFFF; border-right:1px solid #E6EBF1;}

/* ---- En-tete ---- */
.app-head {display:flex; align-items:center; gap:13px; margin-bottom:2px;}
.app-mark {width:40px; height:40px; border-radius:11px; background:#27496D; color:#FFFFFF;
           display:flex; align-items:center; justify-content:center;}
.app-mark svg {width:22px; height:22px;}
.app-title {font-size:1.6rem; font-weight:700; color:#1A2733; letter-spacing:-0.01em; margin:0; line-height:1.1;}
.app-sub {font-size:0.81rem; color:#7A8AA0; margin:6px 0 2px;}

/* ---- Tuiles KPI ---- */
.tile {display:flex; gap:13px; align-items:center; background:#FFFFFF; border:1px solid #E9EDF2;
       border-radius:16px; padding:15px 17px; box-shadow:0 1px 2px rgba(16,32,56,0.04); height:100%;}
.tile-ico {flex:none; width:46px; height:46px; border-radius:12px; background:#EAF0F6;
           display:flex; align-items:center; justify-content:center; color:#27496D;}
.tile-ico svg {width:22px; height:22px;}
.tile.accent .tile-ico {background:#FCECEC; color:#E04F4F;}
.tile-label {font-size:0.68rem; text-transform:uppercase; letter-spacing:0.06em; color:#8294A8; font-weight:700;}
.tile-value {font-size:1.65rem; font-weight:700; color:#1A2733; line-height:1.12; margin-top:2px;}
.tile.accent .tile-value {color:#E04F4F;}
.tile-sub {font-size:0.72rem; color:#9AA8B8; margin-top:2px;}

/* ---- Legende ---- */
.legend {display:flex; align-items:center; gap:15px; font-size:0.76rem; color:#6B7A8D; margin:20px 0 11px;}
.legend .lg {display:flex; align-items:center; gap:6px;}
.legend .dot {width:9px; height:9px; border-radius:50%; display:inline-block;}

/* ---- Board kanban ---- */
.board {display:flex; align-items:flex-start; gap:11px; overflow-x:auto; padding:2px 1px 12px;}
.lane {background:#ECEFF4; border-radius:16px; padding:12px 11px 6px;}
.lane.empty {background:#EFF1F5;}
.lane-head {margin-bottom:12px;}
.lane-title {display:flex; justify-content:space-between; align-items:center; font-weight:700;
             color:#2B3A4B; font-size:0.80rem;}
.lane-title .lane-count {font-size:0.70rem; font-weight:700; color:#3D5675; background:#FFFFFF;
                         border-radius:20px; padding:1px 10px; box-shadow:0 1px 1px rgba(16,32,56,0.05);}
.lane.empty .lane-title {color:#9AA8B8;}
.lane-bar {height:4px; border-radius:3px; background:#DCE2EA; margin-top:9px; overflow:hidden;}
.lane-bar > div {height:100%; background:#27496D; border-radius:3px;}
.lane.empty .lane-bar > div {background:#C4CDD9;}
.lane-empty {border:1.5px dashed #CDD6E0; border-radius:12px; padding:18px 6px; text-align:center;
             color:#9AA8B8; font-size:0.73rem; background:rgba(255,255,255,0.45);}
.lane-more {display:block; text-align:center; font-size:0.72rem; color:#3D5675; font-weight:700;
            text-decoration:none; background:#FFFFFF; border:1px solid #DCE3EC; border-radius:9px;
            padding:7px 6px; margin:2px 2px 9px; cursor:pointer; transition:background .12s ease;}
.lane-more:hover {background:#EAF0F6; border-color:#C3D0DF; color:#27496D;}
/* Bouton natif tout voir / reduire, sous chaque colonne */
.stButton {margin-top:-6px;}
.stButton > button {width:100%; background:#FFFFFF; color:#3D5675; border:1px solid #DCE3EC;
        border-radius:9px; font-size:0.72rem; font-weight:700; padding:6px 6px; min-height:0;
        box-shadow:none;}
.stButton > button:hover {background:#EAF0F6; border-color:#C3D0DF; color:#27496D;}
.stButton > button:focus:not(:active) {color:#27496D; border-color:#C3D0DF;}

/* ---- Carte lead ---- */
.card {position:relative; background:#FFFFFF; border:1px solid #EDF0F4; border-radius:13px;
       padding:12px 13px 12px 16px; margin-bottom:10px;
       box-shadow:0 1px 3px rgba(16,32,56,0.07), 0 1px 2px rgba(16,32,56,0.04);
       transition:box-shadow .15s ease, transform .15s ease;}
.card:hover {box-shadow:0 7px 18px rgba(16,32,56,0.11); transform:translateY(-1px);}
.card::before {content:""; position:absolute; left:0; top:11px; bottom:11px; width:4px;
               border-radius:0 4px 4px 0; background:#6E86A6;}
.card.haute::before {background:#E04F4F;}
.card.moyenne::before {background:#E0922A;}
.card.rapide::before {background:#6E86A6;}
.card-name {font-weight:700; color:#1A2733; font-size:0.85rem; line-height:1.25;}
.tags {display:flex; flex-wrap:wrap; gap:5px; margin:8px 0 7px;}
.pill {font-size:0.58rem; font-weight:800; padding:2px 8px; border-radius:20px;
       text-transform:uppercase; letter-spacing:0.04em; white-space:nowrap;}
.pill.haute {background:#FCECEC; color:#C23B3B;}
.pill.moyenne {background:#FBF1E1; color:#A96B0C;}
.pill.rapide {background:#EDF1F6; color:#56708F;}
.chip {font-size:0.65rem; font-weight:600; padding:2px 9px; border-radius:20px;
       background:#EEF2F7; color:#3D5675; white-space:nowrap;}
.meta {color:#6B7A8D; font-size:0.72rem;}
.action {color:#27496D; font-weight:600; font-size:0.755rem; margin-top:8px;}
.alloc {margin-top:9px; font-size:0.71rem; color:#27496D; background:#EAF0F6;
        border-radius:8px; padding:6px 9px; line-height:1.3;}
.alloc b {color:#1F3A57;}

/* ---- Scrollbar douce du board ---- */
.board::-webkit-scrollbar {height:9px;}
.board::-webkit-scrollbar-thumb {background:#CBD4DF; border-radius:20px;}
.board::-webkit-scrollbar-track {background:transparent;}

/* ---- Onglet equipe : cartes courtier ---- */
.grid {display:flex; flex-wrap:wrap; gap:14px; margin:6px 0 18px;}
.bcard {flex:1 1 290px; max-width:430px; background:#FFFFFF; border:1px solid #E9EDF2;
        border-left:4px solid #6E86A6; border-radius:16px; padding:15px 18px;
        box-shadow:0 1px 2px rgba(16,32,56,0.04);}
.bcard.alert {border-left-color:#E04F4F;}
.bcard.warn {border-left-color:#E0922A;}
.bcard-top {display:flex; align-items:center; justify-content:space-between; gap:8px;}
.bcard-name {font-size:1.02rem; font-weight:700; color:#1A2733;}
.bbadge {font-size:0.59rem; font-weight:800; text-transform:uppercase; letter-spacing:0.04em;
         padding:3px 9px; border-radius:20px; white-space:nowrap; margin-left:5px;}
.bbadge.alert {background:#FCECEC; color:#C23B3B;}
.bbadge.warn {background:#FBF1E1; color:#A96B0C;}
.bbadge.neutre {background:#EDF1F6; color:#56708F;}
.bcard-leads {font-size:0.73rem; color:#8294A8; margin:3px 0 13px;}
.brow {display:flex; align-items:center; gap:9px; margin:7px 0;}
.brow-lbl {flex:0 0 98px; font-size:0.72rem; color:#5A6B7B;}
.btrack {flex:1 1 auto; height:8px; background:#EEF2F7; border-radius:5px; overflow:hidden;}
.btrack > div {height:100%; background:#27496D; border-radius:5px;}
.brow-val {flex:0 0 36px; text-align:right; font-size:0.76rem; font-weight:700; color:#27496D;}
.brow.muted .brow-val {color:#B6C0CD;}

/* ---- Onglet equipe : graphes en carte ---- */
[data-testid="stVegaLiteChart"] {background:#FFFFFF; border:1px solid #E9EDF2; border-radius:16px;
        padding:16px 18px 12px; box-shadow:0 1px 2px rgba(16,32,56,0.04); box-sizing:border-box;
        margin-bottom:14px;}
[data-testid="stVegaLiteChart"] canvas, [data-testid="stVegaLiteChart"] svg {border-radius:8px;}

/* ---- Onglet equipe : cartes d'action ---- */
.action-card {flex:1 1 300px; background:#FFFFFF; border:1px solid #E9EDF2; border-radius:14px;
              padding:14px 17px; box-shadow:0 1px 2px rgba(16,32,56,0.04); border-top:3px solid #27496D;}
.action-card.mort {border-top-color:#E04F4F;}
.ac-h {font-size:0.64rem; font-weight:800; text-transform:uppercase; letter-spacing:0.05em; color:#8294A8;}
.ac-t {font-size:0.98rem; font-weight:700; color:#27496D; margin:4px 0 5px;}
.action-card.mort .ac-t {color:#C23B3B;}
.ac-d {font-size:0.78rem; color:#5A6B7B; line-height:1.4;}
</style>
"""

PRIO_CLASSE = {"Haute": "haute", "Moyenne": "moyenne", "Rapide": "rapide"}

# Icones inline (style trait, heritent de la couleur du conteneur)
_SVG = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round">{}</svg>')
ICO_MARQUE = _SVG.format('<line x1="3" y1="3" x2="3" y2="21"/><line x1="3" y1="21" x2="21" y2="21"/>'
                         '<rect x="7" y="11" width="3.2" height="7"/><rect x="12.4" y="7" width="3.2" height="11"/>'
                         '<rect x="17.8" y="13" width="3.2" height="5"/>')
ICO_LEADS = _SVG.format('<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>'
                        '<path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>')
ICO_RECO = _SVG.format('<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/>')
ICO_HAUTE = _SVG.format('<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>')
ICO_EURO = _SVG.format('<rect x="1" y="4" width="22" height="16" rx="2.5"/><line x1="1" y1="10" x2="23" y2="10"/>')


def kpi(label, value, sub, icon, accent=False):
    """Tuile de chiffre cle, icone a gauche, stylee maison."""
    classe = "tile accent" if accent else "tile"
    return (f"<div class='{classe}'><div class='tile-ico'>{icon}</div><div>"
            f"<div class='tile-label'>{label}</div>"
            f"<div class='tile-value'>{value}</div>"
            f"<div class='tile-sub'>{sub}</div></div></div>")


def styler_chart(ch):
    """Charte commune des graphes Altair de l'onglet equipe : fond transparent
    (la carte fournit le blanc), pas de cadre de vue, axes et legendes aux
    couleurs de la maquette."""
    return (ch.configure(background="transparent")
              .configure_view(strokeWidth=0)
              .configure_axis(labelColor="#5A6B7B", titleColor="#5A6B7B",
                              gridColor="#EEF2F7", domainColor="#E3E8EF",
                              tickColor="#E3E8EF", labelFontSize=11, titleFontSize=12)
              .configure_legend(labelColor="#5A6B7B", titleColor="#8294A8",
                                labelFontSize=11, titleFontSize=11))


def carte_courtier(b, meta_b, lignes_b, badges):
    """Carte d'un courtier : total leads, part CRM, barre de conversion par canal,
    badges d'alerte. badges = liste de (texte, classe)."""
    flag = ""
    if any(c == "alert" for _, c in badges):
        flag = " alert"
    elif any(c == "warn" for _, c in badges):
        flag = " warn"
    badge_html = "".join(f"<span class='bbadge {c}'>{t}</span>" for t, c in badges)
    leads = meta_b["leads"]
    crm = round(100 * meta_b["crm"])
    rows = ""
    for canal in CANAUX:
        sub = lignes_b[lignes_b["Canal"] == canal]
        if len(sub):
            taux = float(sub.iloc[0]["Taux"])
            rows += (f"<div class='brow'><span class='brow-lbl'>{canal}</span>"
                     f"<div class='btrack'><div style='width:{taux:.0f}%'></div></div>"
                     f"<span class='brow-val'>{taux:.0f}%</span></div>")
        else:
            rows += (f"<div class='brow muted'><span class='brow-lbl'>{canal}</span>"
                     f"<div class='btrack'></div><span class='brow-val'>—</span></div>")
    return (f"<div class='bcard{flag}'>"
            f"<div class='bcard-top'><span class='bcard-name'>{b}</span>"
            f"<span>{badge_html}</span></div>"
            f"<div class='bcard-leads'>{leads} leads attribues · {crm}% dans le CRM</div>"
            f"{rows}</div>")


def carte_lead(row, cible_alloc):
    """Carte d'un lead, arrondie, ombre douce, barre d'accent selon la priorite."""
    prio = row["priorite"]
    classe = PRIO_CLASSE.get(prio, "rapide")
    nom = f"{row.get('Prénom','')} {row.get('Nom','')}".strip()
    relances = int(row["Nb relances"])
    delai = row["delai_h"]
    delai_txt = f"{delai:.0f}h" if pd.notna(delai) else "n.c."
    alloc = (f"<div class='alloc'>Orienter vers <b>{cible_alloc}</b></div>"
             if prio == "Haute" else "")
    return (f"<div class='card {classe}'>"
            f"<div class='card-name'>{nom}</div>"
            f"<div class='tags'><span class='pill {classe}'>{prio}</span>"
            f"<span class='chip'>{row['canal']}</span>"
            f"<span class='chip'>{row['Courtier attribué']}</span></div>"
            f"<div class='meta'>1er contact {delai_txt} · {relances} relance(s)</div>"
            f"<div class='action'>{row['action']}</div>"
            f"{alloc}</div>")


def lane_html(etape, sous, cible, max_cartes, largeur_bar, deplie=False):
    """En-tete (compteur, barre de volume) puis les cartes, en un bloc HTML. Le
    bouton tout voir / reduire est un bouton Streamlit natif, rendu sous la colonne,
    pour garder les filtres et permettre plusieurs colonnes depliees a la fois."""
    n = len(sous)
    vide = " empty" if n == 0 else ""
    tete = (f"<div class='lane-head'><div class='lane-title'><span>{etape}</span>"
            f"<span class='lane-count'>{n}</span></div>"
            f"<div class='lane-bar'><div style='width:{largeur_bar}%'></div></div></div>")
    if n == 0:
        corps = "<div class='lane-empty'>Aucun lead actif</div>"
    else:
        montre = n if deplie else max_cartes
        corps = "".join(carte_lead(r, cible) for _, r in sous.head(montre).iterrows())
    return f"<div class='lane{vide}'>{tete}{corps}</div>"


def _basculer_colonne(stage):
    """Bascule l'etat deplie/replie d'une colonne, conserve entre les reruns."""
    cle = f"open_{stage}"
    st.session_state[cle] = not st.session_state.get(cle, False)


def main():
    st.set_page_config(page_title="Pipeline CRM Optivie", layout="wide",
                       initial_sidebar_state="expanded")
    st.markdown(CSS, unsafe_allow_html=True)

    leads, jour = st.cache_data(charger_donnees)()
    leads["etape"] = leads.apply(placer_etape, axis=1)
    leads["priorite"] = leads.apply(prioriser, axis=1)
    leads["action"] = leads.apply(prochaine_action, axis=1)
    cible, perf_cible, charge_cible, angle_mort, perf_mort = suggestion_allocation(leads)

    st.markdown(
        f"<div class='app-head'><div class='app-mark'>{ICO_MARQUE}</div>"
        f"<h1 class='app-title'>Pipeline CRM Optivie</h1></div>"
        "<p class='app-sub'>Groupe 7 · Livrable 4 · le funnel du Livrable 3 sur les donnees reelles 2025, "
        "demonstrateur de ce qu'on parametrerait ensuite dans HubSpot.</p>",
        unsafe_allow_html=True)

    # ---- Barre laterale, filtres de demo ----
    en_cours = leads[leads["Statut lead"] == "En cours"]
    relances_dispo = sorted(int(x) for x in en_cours["Nb relances"].dropna().unique())
    dmax = en_cours["delai_h"].max()
    delai_max = int(dmax) if pd.notna(dmax) else 48
    with st.sidebar:
        st.header("Filtres")
        f_courtiers = st.multiselect("Courtier", sorted(leads["Courtier attribué"].unique()),
                                     placeholder="Tous les courtiers")
        f_canaux = st.multiselect("Canal", CANAUX, placeholder="Tous les canaux")
        f_prio = st.multiselect("Priorite", ["Haute", "Moyenne", "Rapide"],
                                placeholder="Toutes les priorites")
        f_etapes = st.multiselect("Etape du funnel", STAGES, placeholder="Toutes les etapes")
        f_relances = st.multiselect("Nombre de relances", relances_dispo,
                                    placeholder="Tous", format_func=lambda x: f"{x} relance(s)")
        f_delai = st.slider("Delai de 1er contact au-dela de (h)", 0, delai_max, 0)
        hors_crm = st.toggle("Hors CRM seulement")
        st.divider()
        st.caption(f"SLA lead lent : au-dela de {SLA_LENT_H}h · "
                   f"Commission recurrente : {COMMISSION} € par contrat")

    onglet_pipeline, onglet_equipe = st.tabs(["Pipeline", "Performance equipe"])

    # =================== ONGLET PIPELINE ===================
    with onglet_pipeline:
        actifs = leads[leads["Statut lead"] == "En cours"].copy()

        # Chiffres cles, calcules sur les leads actifs
        n_actifs = len(actifs)
        part_reco = 100 * (actifs["canal"] == "Recommandation").mean() if n_actifs else 0
        n_haute = int((actifs["priorite"] == "Haute").sum())
        argent = n_haute * COMMISSION

        k1, k2, k3, k4 = st.columns(4)
        k1.markdown(kpi("Leads en cours", f"{n_actifs}", "en acquisition", ICO_LEADS),
                    unsafe_allow_html=True)
        k2.markdown(kpi("Part recommandation", f"{part_reco:.0f}%", "du flux actif", ICO_RECO),
                    unsafe_allow_html=True)
        k3.markdown(kpi("Pile haute", f"{n_haute}", "leads prioritaires", ICO_HAUTE, accent=True),
                    unsafe_allow_html=True)
        k4.markdown(kpi("Recurrent en jeu", f"{argent:,.0f} €".replace(",", " "),
                        f"{n_haute} x {COMMISSION} € de commission", ICO_EURO),
                    unsafe_allow_html=True)

        # Filtres
        vue = actifs
        if f_courtiers:
            vue = vue[vue["Courtier attribué"].isin(f_courtiers)]
        if f_canaux:
            vue = vue[vue["canal"].isin(f_canaux)]
        if f_prio:
            vue = vue[vue["priorite"].isin(f_prio)]
        if f_etapes:
            vue = vue[vue["etape"].isin(f_etapes)]
        if f_relances:
            vue = vue[vue["Nb relances"].isin(f_relances)]
        if f_delai > 0:
            vue = vue[vue["delai_h"] >= f_delai]
        if hors_crm:
            vue = vue[vue["Dans CRM"] == "Non"]

        # Legende des priorites
        st.markdown(
            "<div class='legend'><span style='font-weight:700;color:#2B3A4B'>Priorite</span>"
            "<span class='lg'><span class='dot' style='background:#E04F4F'></span>Haute</span>"
            "<span class='lg'><span class='dot' style='background:#E0922A'></span>Moyenne</span>"
            "<span class='lg'><span class='dot' style='background:#6E86A6'></span>Rapide</span></div>",
            unsafe_allow_html=True)

        # Board kanban des six etapes. Chaque colonne est une vraie colonne Streamlit,
        # avec un bouton natif tout voir / reduire en bas. L'etat de chaque colonne est
        # garde dans st.session_state, donc les filtres restent et plusieurs colonnes
        # peuvent etre depliees en meme temps.
        # Tri une fois : priorite, puis retard decroissant dans la pile haute.
        ordre_prio = {"Haute": 0, "Moyenne": 1, "Rapide": 2, "Historique": 3}
        vue = vue.copy()
        vue["_p"] = vue["priorite"].map(ordre_prio)
        vue = vue.sort_values(["_p", "delai_h"], ascending=[True, False])
        comptes = {s: int((vue["etape"] == s).sum()) for s in STAGES}
        mx = max(comptes.values()) or 1
        poids = [2.0 if comptes[s] > 0 else 1.0 for s in STAGES]
        for col, s in zip(st.columns(poids, gap="small"), STAGES):
            with col:
                n = comptes[s]
                ouvert = st.session_state.get(f"open_{s}", False)
                st.markdown(lane_html(s, vue[vue["etape"] == s], cible, CARTES_PAR_COLONNE,
                                      int(round(100 * n / mx)), deplie=ouvert),
                            unsafe_allow_html=True)
                if n > CARTES_PAR_COLONNE:
                    label = "Reduire" if ouvert else f"+ {n - CARTES_PAR_COLONNE} autres, tout voir"
                    st.button(label, key=f"voir_{s}", on_click=_basculer_colonne, args=(s,))

        with st.expander("Methode et provenance des chiffres"):
            st.markdown(
                f"""
**Perimetre.** Monde acquisition uniquement, feuilles Leads et Journal. Les feuilles
Contrats, Resiliations et Portefeuille (la retention) restent hors champ.

**Etapes du funnel.** Les six colonnes sont le funnel redessine au Livrable 3. Un lead
est range d'apres son activite reelle, l'etape devis vient de l'action *Devis envoye*
du Journal.

**Regle de priorite.**
- Haute, les leads qui glissent : recommandation, en cours, pas encore au devis, et
  delai de premier contact superieur a {SLA_LENT_H}h ou jamais relance. Tri par retard decroissant.
- Moyenne : le reste de la recommandation en cours.
- Rapide : comparateurs et prospection, traites sans surinvestir car la donnee montre
  que l'effort supplementaire n'y change presque rien.

**Allocation.** Pour un lead prioritaire, l'outil suggere de l'orienter vers le meilleur
convertisseur de recommandation visible dans le CRM, ici {cible} ({perf_cible:.0f}% sur ce canal).
Il signale aussi que {angle_mort}, meilleur convertisseur ({perf_mort:.0f}%), reste hors CRM donc invisible.

**Chiffres.** Tout est calcule depuis le dataset. Conversion sur leads aboutis,
convertis divises par convertis plus perdus. Le recurrent en jeu vaut {COMMISSION} € par lead,
notre commission recurrente moyenne.
                """
            )

    # =================== ONGLET PERFORMANCE EQUIPE ===================
    with onglet_equipe:
        st.subheader("Force par courtier et par canal")
        st.caption("Conversion sur leads aboutis, lue a canal constant pour ne pas confondre "
                   "la performance avec le simple effet d'allocation.")

        tidy, meta, courtiers = prep_equipe(leads)
        maxleads = max(m["leads"] for m in meta.values())
        ref = {canal: conversion(leads[leads["canal"] == canal])[0] for canal in CANAUX}

        sous_a, sous_b, sous_c, sous_d = st.tabs(
            ["Cartes courtier", "Matrice a bulles", "Barres par canal", "Reco et actions"])

        # ----- A. Cartes courtier -----
        with sous_a:
            cartes = ""
            for b in courtiers:
                badges = []
                if b == angle_mort:
                    badges.append(("Hors CRM", "alert"))
                if b == cible:
                    badges.append(("Sous-alimente", "warn"))
                if meta[b]["leads"] == maxleads:
                    badges.append(("Surcharge", "neutre"))
                cartes += carte_courtier(b, meta[b], tidy[tidy["Courtier"] == b], badges)
            st.markdown(f"<div class='grid'>{cartes}</div>", unsafe_allow_html=True)
            st.caption("Repere canal, tous courtiers : "
                       + " · ".join(f"{c} {ref[c]:.0f}%" for c in CANAUX))

        # ----- B. Matrice a bulles -----
        with sous_b:
            base = alt.Chart(tidy)
            bulles = base.mark_circle(opacity=0.9).encode(
                x=alt.X("Canal:N", sort=CANAUX, title=None),
                y=alt.Y("Courtier:N", sort=courtiers, title=None),
                size=alt.Size("Leads:Q", scale=alt.Scale(range=[200, 3000]),
                              legend=alt.Legend(title="Nb leads")),
                color=alt.Color("Taux:Q", scale=alt.Scale(scheme="blues", domain=[0, 75]),
                                legend=alt.Legend(title="Conv. %")),
                tooltip=[alt.Tooltip("Courtier:N"), alt.Tooltip("Canal:N"),
                         alt.Tooltip("Taux:Q", title="Conversion %", format=".0f"),
                         alt.Tooltip("Convertis:Q"), alt.Tooltip("Aboutis:Q"),
                         alt.Tooltip("Leads:Q")])
            txt = base.mark_text(fontSize=11, fontWeight="bold").encode(
                x=alt.X("Canal:N", sort=CANAUX), y=alt.Y("Courtier:N", sort=courtiers),
                text=alt.Text("Taux:Q", format=".0f"),
                color=alt.condition("datum.Taux > 45", alt.value("white"), alt.value("#27496D")))
            st.altair_chart(styler_chart((bulles + txt).properties(height=340)), width="stretch")
            st.caption("Taille de bulle = nombre de leads attribues, couleur = taux de conversion. "
                       "On lit le volume et la force au meme endroit.")

        # ----- C. Barres groupees par canal -----
        with sous_c:
            barres = alt.Chart(tidy).mark_bar(cornerRadius=3).encode(
                x=alt.X("Courtier:N", sort=courtiers, title=None),
                xOffset=alt.XOffset("Canal:N", sort=CANAUX),
                y=alt.Y("Taux:Q", title="Conversion (%)", scale=alt.Scale(domain=[0, 80])),
                color=alt.Color("Canal:N", sort=CANAUX,
                                scale=alt.Scale(domain=CANAUX,
                                                range=["#27496D", "#6E86A6", "#C2CDDB"]),
                                legend=alt.Legend(title=None, orient="top")),
                tooltip=[alt.Tooltip("Courtier:N"), alt.Tooltip("Canal:N"),
                         alt.Tooltip("Taux:Q", title="Conversion %", format=".0f"),
                         alt.Tooltip("Aboutis:Q")]).properties(height=360)
            st.altair_chart(styler_chart(barres), width="stretch")
            st.caption("A canal constant. Les comparateurs plafonnent tout le monde autour de 16%, "
                       "les vrais ecarts sont sur la recommandation.")

        # ----- D. Reco et actions -----
        with sous_d:
            reco = tidy[tidy["Canal"] == "Recommandation"]
            reco_mean = ref["Recommandation"]
            barre = alt.Chart(reco).mark_bar(color="#27496D", cornerRadius=4).encode(
                y=alt.Y("Courtier:N", sort="-x", title=None),
                x=alt.X("Taux:Q", title="Conversion sur la recommandation (%)",
                        scale=alt.Scale(domain=[0, 75], nice=False),
                        axis=alt.Axis(values=[0, 10, 20, 30, 40, 50, 60, 70])),
                tooltip=[alt.Tooltip("Courtier:N"),
                         alt.Tooltip("Taux:Q", title="Conversion %", format=".0f"),
                         alt.Tooltip("Convertis:Q"), alt.Tooltip("Aboutis:Q")])
            etiquette = alt.Chart(reco).mark_text(align="left", dx=5, fontWeight="bold",
                                                  color="#27496D").encode(
                y=alt.Y("Courtier:N", sort="-x"), x=alt.X("Taux:Q"),
                text=alt.Text("Taux:Q", format=".0f"))
            moyenne = alt.Chart(pd.DataFrame({"m": [reco_mean]})).mark_rule(
                color="#E0922A", strokeDash=[5, 3], size=2).encode(x="m:Q")
            st.altair_chart(
                styler_chart((barre + etiquette + moyenne).properties(
                    height=240, padding={"left": 6, "right": 22, "top": 6, "bottom": 6})),
                width="stretch")
            st.caption(f"Ligne ambre : moyenne du canal recommandation, {reco_mean:.0f}%. "
                       "Romain et Clara ne traitent pas de recommandation, ils n'apparaissent pas ici. "
                       "Les comparateurs restent plats, 13 a 18% pour tous.")
            st.markdown(
                f"<div class='grid'>"
                f"<div class='action-card'><div class='ac-h'>Action</div>"
                f"<div class='ac-t'>Orienter vers {cible}</div>"
                f"<div class='ac-d'>Bonne convertisseuse sur la recommandation ({perf_cible:.0f}%), "
                f"dans le CRM donc visible, et la moins alimentee de l'equipe. On lui envoie les leads "
                f"de recommandation qui glissent.</div></div>"
                f"<div class='action-card mort'><div class='ac-h'>Angle mort</div>"
                f"<div class='ac-t'>Recuperer le portefeuille de {angle_mort}</div>"
                f"<div class='ac-d'>Meilleur convertisseur sur la recommandation ({perf_mort:.0f}%) "
                f"mais hors CRM, donc invisible au pilotage. A ramener dans le systeme pour cesser "
                f"de piloter a l'aveugle.</div></div></div>",
                unsafe_allow_html=True)

        st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)
        with st.expander("Lecture et consequence"):
            st.markdown(
                f"""
**Lecture.** Sur la recommandation, les ecarts sont reels. {angle_mort} convertit {perf_mort:.0f}%,
au-dessus de la moyenne du canal, mais tout son portefeuille est hors CRM donc invisible.
{cible} convertit {perf_cible:.0f}% et recoit le moins de leads de l'equipe, on sous-alimente
une bonne convertisseuse. Sur les comparateurs, tout le monde se tient autour du plafond du
canal, il n'y a pas de specialiste a creer, le canal decide a la place du courtier.

**Consequence.** Orienter les leads de recommandation vers les forts convertisseurs disponibles,
et ramener le portefeuille hors CRM dans le systeme pour cesser de piloter a l'aveugle.
                """
            )


if __name__ == "__main__":
    main()
