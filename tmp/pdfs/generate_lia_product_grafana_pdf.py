"""Generate the LIA product metrics and Grafana dashboard specification PDF."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Sequence

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    LongTable,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


OUTPUT_PATH = Path("output/pdf/LIA_Specification_Dashboard_Grafana_Produit_v1.1.pdf")
PAGE_WIDTH, PAGE_HEIGHT = A4

NAVY = colors.HexColor("#17233C")
BLUE = colors.HexColor("#4A6CF7")
CYAN = colors.HexColor("#19A7CE")
PURPLE = colors.HexColor("#8A63D2")
GREEN = colors.HexColor("#2E9D71")
AMBER = colors.HexColor("#D99B2B")
RED = colors.HexColor("#CC4B4B")
INK = colors.HexColor("#222936")
MUTED = colors.HexColor("#667085")
LIGHT = colors.HexColor("#F5F7FB")
LIGHT_BLUE = colors.HexColor("#EEF2FF")
LINE = colors.HexColor("#D9DFEA")
WHITE = colors.white


def register_fonts() -> tuple[str, str, str]:
    """Register Segoe UI when available and return regular, bold, italic names."""
    font_dir = Path("C:/Windows/Fonts")
    regular = font_dir / "segoeui.ttf"
    bold = font_dir / "segoeuib.ttf"
    italic = font_dir / "segoeuii.ttf"
    if regular.exists() and bold.exists() and italic.exists():
        pdfmetrics.registerFont(TTFont("SegoeUI", str(regular)))
        pdfmetrics.registerFont(TTFont("SegoeUI-Bold", str(bold)))
        pdfmetrics.registerFont(TTFont("SegoeUI-Italic", str(italic)))
        return "SegoeUI", "SegoeUI-Bold", "SegoeUI-Italic"
    return "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"


FONT, FONT_BOLD, FONT_ITALIC = register_fonts()


class NumberedCanvasMixin:
    """Marker mixin kept for explicit PDF generation intent."""


def on_page(canvas, doc) -> None:
    """Draw a consistent page header and footer."""
    canvas.saveState()
    page = canvas.getPageNumber()
    if page > 1:
        canvas.setFillColor(NAVY)
        canvas.rect(0, PAGE_HEIGHT - 13 * mm, PAGE_WIDTH, 13 * mm, fill=1, stroke=0)
        canvas.setFont(FONT_BOLD, 7.6)
        canvas.setFillColor(WHITE)
        canvas.drawString(
            16 * mm,
            PAGE_HEIGHT - 8.2 * mm,
            "LIA - Dashboard Grafana Produit - Specification v1.1",
        )
        canvas.setFont(FONT, 7.2)
        canvas.drawRightString(
            PAGE_WIDTH - 16 * mm,
            PAGE_HEIGHT - 8.2 * mm,
            "Grafana + Prometheus + PostgreSQL",
        )
    canvas.setStrokeColor(LINE)
    canvas.line(16 * mm, 12 * mm, PAGE_WIDTH - 16 * mm, 12 * mm)
    canvas.setFont(FONT, 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(16 * mm, 7.6 * mm, "Restitution produit et technique - 29 juillet 2026")
    canvas.drawRightString(PAGE_WIDTH - 16 * mm, 7.6 * mm, f"Page {page}")
    canvas.restoreState()


styles = getSampleStyleSheet()
styles.add(
    ParagraphStyle(
        "CoverTitle",
        parent=styles["Title"],
        fontName=FONT_BOLD,
        fontSize=27,
        leading=31,
        textColor=WHITE,
        alignment=TA_LEFT,
        spaceAfter=8 * mm,
    )
)
styles.add(
    ParagraphStyle(
        "CoverSubtitle",
        parent=styles["Normal"],
        fontName=FONT,
        fontSize=13,
        leading=18,
        textColor=colors.HexColor("#DCE4FF"),
        spaceAfter=4 * mm,
    )
)
styles.add(
    ParagraphStyle(
        "H1x",
        parent=styles["Heading1"],
        fontName=FONT_BOLD,
        fontSize=17,
        leading=21,
        textColor=NAVY,
        spaceBefore=4 * mm,
        spaceAfter=3.5 * mm,
        keepWithNext=True,
    )
)
styles.add(
    ParagraphStyle(
        "H2x",
        parent=styles["Heading2"],
        fontName=FONT_BOLD,
        fontSize=12.2,
        leading=15,
        textColor=BLUE,
        spaceBefore=3.5 * mm,
        spaceAfter=2.2 * mm,
        keepWithNext=True,
    )
)
styles.add(
    ParagraphStyle(
        "H3x",
        parent=styles["Heading3"],
        fontName=FONT_BOLD,
        fontSize=9.5,
        leading=12,
        textColor=NAVY,
        spaceBefore=2.2 * mm,
        spaceAfter=1.5 * mm,
        keepWithNext=True,
    )
)
styles.add(
    ParagraphStyle(
        "Bodyx",
        parent=styles["BodyText"],
        fontName=FONT,
        fontSize=8.5,
        leading=12,
        textColor=INK,
        spaceAfter=2.2 * mm,
    )
)
styles.add(
    ParagraphStyle(
        "Smallx",
        parent=styles["BodyText"],
        fontName=FONT,
        fontSize=7.2,
        leading=9.5,
        textColor=INK,
    )
)
styles.add(
    ParagraphStyle(
        "Tinyx",
        parent=styles["BodyText"],
        fontName=FONT,
        fontSize=6.35,
        leading=8,
        textColor=INK,
    )
)
styles.add(
    ParagraphStyle(
        "Bulletx",
        parent=styles["BodyText"],
        fontName=FONT,
        fontSize=8.3,
        leading=11.5,
        leftIndent=4 * mm,
        firstLineIndent=-2.5 * mm,
        bulletIndent=0,
        textColor=INK,
        spaceAfter=1.1 * mm,
    )
)
styles.add(
    ParagraphStyle(
        "Calloutx",
        parent=styles["BodyText"],
        fontName=FONT,
        fontSize=8.6,
        leading=12,
        textColor=NAVY,
        leftIndent=3 * mm,
        rightIndent=3 * mm,
        spaceAfter=0,
    )
)
styles.add(
    ParagraphStyle(
        "Codex",
        parent=styles["Code"],
        fontName="Courier",
        fontSize=6.8,
        leading=9,
        textColor=INK,
        leftIndent=2 * mm,
        rightIndent=2 * mm,
    )
)
styles.add(
    ParagraphStyle(
        "TableHead",
        parent=styles["BodyText"],
        fontName=FONT_BOLD,
        fontSize=6.6,
        leading=8.1,
        textColor=WHITE,
        alignment=TA_LEFT,
    )
)
styles.add(
    ParagraphStyle(
        "TableCell",
        parent=styles["BodyText"],
        fontName=FONT,
        fontSize=6.2,
        leading=8,
        textColor=INK,
    )
)
styles.add(
    ParagraphStyle(
        "TableCellBold",
        parent=styles["BodyText"],
        fontName=FONT_BOLD,
        fontSize=6.2,
        leading=8,
        textColor=INK,
    )
)
styles.add(
    ParagraphStyle(
        "MetricId",
        parent=styles["BodyText"],
        fontName=FONT_BOLD,
        fontSize=6.2,
        leading=8,
        textColor=BLUE,
    )
)
styles.add(
    ParagraphStyle(
        "FooterNote",
        parent=styles["BodyText"],
        fontName=FONT_ITALIC,
        fontSize=7.2,
        leading=9.5,
        textColor=MUTED,
    )
)


def p(text: str, style: str = "Bodyx") -> Paragraph:
    """Create a styled paragraph."""
    return Paragraph(text, styles[style])


def h1(text: str) -> Paragraph:
    return p(text, "H1x")


def h2(text: str) -> Paragraph:
    return p(text, "H2x")


def h3(text: str) -> Paragraph:
    return p(text, "H3x")


def bullet(text: str) -> Paragraph:
    return Paragraph(f"- {text}", styles["Bulletx"])


def callout(text: str, color: colors.Color = LIGHT_BLUE) -> Table:
    """Create a highlighted single-cell callout."""
    table = Table([[p(text, "Calloutx")]], colWidths=[173 * mm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), color),
                ("BOX", (0, 0), (-1, -1), 0.8, BLUE),
                ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 2.8 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.8 * mm),
            ]
        )
    )
    return table


def code_block(text: str) -> Table:
    """Create a compact code or configuration block."""
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    escaped = escaped.replace("\n", "<br/>")
    table = Table([[p(escaped, "Codex")]], colWidths=[173 * mm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F0F2F6")),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 2.5 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2.5 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 2 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
            ]
        )
    )
    return table


def simple_table(
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    widths: Sequence[float],
    *,
    font_size: str = "TableCell",
    repeat_rows: int = 1,
    padding_mm: float = 1.4,
) -> LongTable:
    """Create a styled table that can span pages."""
    data = [[p(header, "TableHead") for header in headers]]
    for row in rows:
        cells = []
        for index, value in enumerate(row):
            if index == 0 and value and len(value) <= 12:
                cells.append(p(value, "MetricId"))
            else:
                cells.append(p(value, font_size))
        data.append(cells)
    table = LongTable(
        data,
        colWidths=[width * mm for width in widths],
        repeatRows=repeat_rows,
        hAlign="LEFT",
        splitByRow=1,
    )
    style_commands = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.35, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 1.6 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1.6 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), padding_mm * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), padding_mm * mm),
    ]
    for row_index in range(1, len(data)):
        if row_index % 2 == 0:
            style_commands.append(("BACKGROUND", (0, row_index), (-1, row_index), LIGHT))
    table.setStyle(TableStyle(style_commands))
    return table


@dataclass(frozen=True)
class Metric:
    identifier: str
    name: str
    formula: str
    source: str


EXISTING = "Existant"
PARTIAL = "Partiel"
NEW_DB = "Nouveau DB"
NEW_PROM = "Nouveau Prom."
NEW_CLIENT = "Nouveau client"
DERIVED = "Dérivé"
QA = "QA automatisée"


metric_groups: list[tuple[str, list[Metric]]] = [
    (
        "North Star et diffusion de la valeur",
        [
            Metric("NS-01", "Utilisateurs hebdomadaires avec résultat utile", "COUNT DISTINCT user_id avec au moins un résultat E1 ou E2 validé sur 7 jours.", NEW_DB),
            Metric("NS-02", "Taux de pénétration de la valeur", "Utilisateurs NS-01 / utilisateurs engagés éligibles.", DERIVED),
            Metric("NS-03", "Profondeur utile médiane", "Médiane des résultats utiles par utilisateur ayant au moins un résultat utile.", DERIVED),
            Metric("NS-04", "Volume de résultats utiles", "Nombre de result_id uniques E1 ou E2.", DERIVED),
            Metric("NS-05", "Part explicitement confirmée", "Résultats E1 / résultats E1 + E2.", DERIVED),
            Metric("NS-06", "Couverture de mesure", "Résultats avec E1, E2 ou rejet explicite / résultats produits.", DERIVED),
        ],
    ),
    (
        "Funnel, acquisition et activation",
        [
            Metric("FUN-01", "Visite vers inscription", "Inscriptions terminées / visiteurs éligibles.", NEW_CLIENT),
            Metric("FUN-02", "Finalisation inscription", "Inscriptions terminées / inscriptions commencées.", PARTIAL),
            Metric("FUN-03", "Premier objectif sélectionné", "Utilisateurs ayant choisi un objectif / inscrits.", NEW_CLIENT),
            Metric("FUN-04", "Première source activée", "Utilisateurs avec connecteur actif / flux de connexion initiés.", PARTIAL),
            Metric("FUN-05", "Démo terminée", "Démos terminées / démos commencées.", NEW_CLIENT),
            Metric("FUN-06", "Première demande", "Inscrits ayant envoyé une demande / inscrits.", NEW_DB),
            Metric("FUN-07", "Premier succès technique", "Inscrits avec premier résultat E3 ou mieux / inscrits.", NEW_DB),
            Metric("FUN-08", "Première valeur", "Inscrits avec premier résultat E1 ou E2 / inscrits.", NEW_DB),
            Metric("FUN-09", "Retour engagé D7", "Utilisateurs revenus et engagés à J+7 / cohorte inscrite.", DERIVED),
            Metric("FUN-10", "Première routine ou projet", "Utilisateurs ayant créé une routine ou un projet / activés.", NEW_DB),
            Metric("FUN-11", "Seconde semaine utile", "Inscrits obtenant un résultat utile en semaine 2 / inscrits.", DERIVED),
            Metric("FUN-12", "Temps inter-étapes", "P50 et P95 entre chaque étape consécutive du funnel.", DERIVED),
            Metric("ACQ-01", "Nouveaux inscrits", "Comptes créés sur la période.", EXISTING),
            Metric("ACQ-02", "Source d'acquisition", "Répartition des inscriptions par canal attribuable.", NEW_CLIENT),
            Metric("ACQ-03", "Conversion par canal", "Inscriptions / visiteurs du canal.", DERIVED),
            Metric("ACQ-04", "Première valeur par canal", "Activés E1/E2 / inscrits du canal.", DERIVED),
            Metric("ACQ-05", "Rétention D30 par canal", "Utilisateurs utiles D30 / activés du canal.", DERIVED),
            Metric("ACQ-06", "Coût d'acquisition", "Dépenses attribuables / nouveaux inscrits.", NEW_DB),
            Metric("ACQ-07", "Coût par utilisateur activé", "Dépenses attribuables / utilisateurs avec première valeur.", DERIVED),
            Metric("ACT-01", "Activation 24 h", "Inscrits avec E1/E2 sous 24 h / inscrits.", DERIVED),
            Metric("ACT-02", "Activation 7 j", "Inscrits avec E1/E2 sous 7 jours / inscrits.", DERIVED),
            Metric("ACT-03", "Délai de première valeur", "P50/P75/P95 de première validation - inscription.", DERIVED),
            Metric("ACT-04", "Activation première session", "Première valeur avant fin de session / inscrits.", NEW_CLIENT),
            Metric("ACT-05", "Onboarding terminé", "Onboardings terminés / commencés.", PARTIAL),
            Metric("ACT-06", "Onboarding abandonné", "Onboardings abandonnés / commencés.", NEW_CLIENT),
            Metric("ACT-07", "Activation avec connecteur", "Activés après connexion / utilisateurs connectés.", DERIVED),
            Metric("ACT-08", "Activation sans connecteur", "Activés sans source externe / utilisateurs sans connecteur.", DERIVED),
            Metric("ACT-09", "Démo vers demande réelle", "Utilisateurs avec demande réelle / démos terminées.", DERIVED),
            Metric("ACT-10", "Démo vers source connectée", "Utilisateurs connectés / démos terminées.", DERIVED),
            Metric("ACT-11", "Démo vers valeur réelle", "Utilisateurs E1/E2 / démos terminées.", DERIVED),
            Metric("ACT-12", "Échec avant valeur", "Inscrits sans résultat utile sous 7 jours.", DERIVED),
            Metric("ACT-13", "Étape bloquante dominante", "Plus forte perte relative entre deux étapes consécutives.", DERIVED),
        ],
    ),
    (
        "Engagement et rétention",
        [
            Metric("ENG-01", "DAU engagé", "Utilisateurs uniques ayant une action significative sur 24 h.", PARTIAL),
            Metric("ENG-02", "WAU engagé", "Utilisateurs uniques ayant une action significative sur 7 jours.", PARTIAL),
            Metric("ENG-03", "MAU engagé", "Utilisateurs uniques ayant une action significative sur 30 jours.", NEW_DB),
            Metric("ENG-04", "DAU/MAU", "DAU engagé / MAU engagé.", DERIVED),
            Metric("ENG-05", "WAU/MAU", "WAU engagé / MAU engagé.", DERIVED),
            Metric("ENG-06", "Jours actifs par semaine", "Médiane/P75 du nombre de jours engagés par utilisateur.", DERIVED),
            Metric("ENG-07", "Demandes par utilisateur", "Médiane/P75/P90 sur utilisateurs engagés.", PARTIAL),
            Metric("ENG-08", "Résultats utiles par utilisateur", "Médiane/P75/P90 des result_id E1/E2.", DERIVED),
            Metric("ENG-09", "Engagés sans valeur", "Utilisateurs engagés sans E1/E2 / utilisateurs engagés.", DERIVED),
            Metric("ENG-10", "Adoption par fonctionnalité", "Utilisateurs de la fonctionnalité / utilisateurs éligibles.", NEW_DB),
            Metric("ENG-11", "Adoption multi-domaines", "Utilisateurs actifs sur au moins 2 domaines / engagés.", DERIVED),
            Metric("ENG-12", "Adoption espaces/projets", "Utilisateurs actifs sur espaces / éligibles.", NEW_DB),
            Metric("ENG-13", "Adoption routines", "Utilisateurs avec routine active / éligibles.", PARTIAL),
            Metric("ENG-14", "Fermeture des boucles ouvertes", "Boucles closes / boucles détectées.", EXISTING),
            Metric("ENG-15", "Profondeur de session", "Actions significatives par session, médiane/P75.", NEW_CLIENT),
            Metric("RET-01", "Rétention engagée D1/D7/D30", "Retour engagé à J+1, J+7 et J+30 / cohorte.", DERIVED),
            Metric("RET-02", "Rétention utile D7/D30", "Nouveau résultat utile à J+7/J+30 / cohorte activée.", DERIVED),
            Metric("RET-03", "Courbe de cohorte", "Part d'utilisateurs utiles par semaine depuis activation.", DERIVED),
            Metric("RET-04", "Semaines utiles consécutives", "Médiane/P75 des semaines avec E1/E2.", DERIVED),
            Metric("RET-05", "Churn engagé", "Absence d'engagement au-delà du seuil.", DERIVED),
            Metric("RET-06", "Churn utile", "Absence de résultat utile au-delà du seuil.", DERIVED),
            Metric("RET-07", "Résurrection utile", "Utilisateurs churnés revenant avec un nouveau E1/E2.", DERIVED),
            Metric("RET-08", "Rétention par preuve", "Rétention comparée après E1, E2 et E3.", DERIVED),
            Metric("RET-09", "Rétention après connexion", "Connectés vs non connectés.", DERIVED),
            Metric("RET-10", "Rétention après routine", "Routine active vs usage interactif seul.", DERIVED),
            Metric("RET-11", "Rétention mobile/desktop", "Comparaison selon la première plateforme de valeur.", DERIVED),
        ],
    ),
    (
        "Qualité des résultats et orchestration",
        [
            Metric("OUT-01", "Résultats produits", "Nombre de result_id produits.", NEW_PROM),
            Metric("OUT-02", "Taux de résultat utile", "Résultats E1/E2 / résultats produits.", DERIVED),
            Metric("OUT-03", "Réussite end-to-end", "Workflows terminés avec résultat / workflows commencés.", PARTIAL),
            Metric("OUT-04", "Utile au premier passage", "Résultats first_pass E1/E2 / résultats produits.", NEW_DB),
            Metric("OUT-05", "Faux succès", "Succès techniques ensuite rejetés, corrigés ou révertis / succès techniques.", NEW_DB),
            Metric("OUT-06", "Taux de correction", "Résultats corrigés / résultats produits.", NEW_DB),
            Metric("OUT-07", "Taux de réversion", "Actions réverties / actions exécutées.", NEW_DB),
            Metric("OUT-08", "Taux de rejet", "Résultats explicitement rejetés / résultats évaluables.", PARTIAL),
            Metric("OUT-09", "Succès partiel", "Workflows partiellement réussis / workflows terminés.", EXISTING),
            Metric("OUT-10", "Résultat manquant", "Workflows terminés sans résultat exploitable / terminés.", NEW_DB),
            Metric("OUT-11", "Retry utilisateur", "Workflows relancés explicitement / workflows.", NEW_DB),
            Metric("OUT-12", "Replanification", "Workflows replanifiés / workflows.", PARTIAL),
            Metric("OUT-13", "Intervention manuelle", "Workflows repris manuellement / workflows.", NEW_DB),
            Metric("OUT-14", "Tours jusqu'au résultat", "P50/P75/P95 des tours utilisateur.", PARTIAL),
            Metric("OUT-15", "Tentatives jusqu'au résultat", "P50/P75/P95 des tentatives.", NEW_DB),
            Metric("OUT-16", "Temps jusqu'au résultat", "P50/P75/P95 de request_started à result_produced.", PARTIAL),
            Metric("OUT-17", "Délai de présentation", "result_presented - result_produced.", NEW_CLIENT),
            Metric("OUT-18", "Résultat utilisé", "Résultats E2 / résultats présentés.", NEW_CLIENT),
            Metric("OUT-19", "Résultat exporté ou partagé", "Résultats exportés/partagés / présentés.", NEW_CLIENT),
            Metric("OUT-20", "Qualité par domaine", "OUT-02 à OUT-16 ventilés par domaine borné.", DERIVED),
            Metric("OUT-21", "Qualité Pipeline/ReAct", "Comparaison normalisée par type de demande.", DERIVED),
            Metric("OUT-22", "Qualité par modèle/fournisseur", "Utilité et premier passage par modèle/fournisseur.", PARTIAL),
        ],
    ),
    (
        "HITL, plans et brouillons",
        [
            Metric("HITL-01", "Taux d'approbation", "Approbations acceptées / présentées.", EXISTING),
            Metric("HITL-02", "Acceptation sans modification", "Acceptées telles quelles / présentées.", PARTIAL),
            Metric("HITL-03", "Modification avant approbation", "Éditées puis approuvées / présentées.", EXISTING),
            Metric("HITL-04", "Rejet", "Approbations rejetées / présentées.", EXISTING),
            Metric("HITL-05", "Abandon d'approbation", "Approbations expirées sans décision / présentées.", PARTIAL),
            Metric("HITL-06", "Latence de décision", "P50/P75/P95 entre présentation et décision.", EXISTING),
            Metric("HITL-07", "Reprise réussie", "Reprises graph réussies / décisions positives.", EXISTING),
            Metric("HITL-08", "Succès post-approbation", "Exécutions réussies / approbations positives.", NEW_DB),
            Metric("HITL-09", "Regret post-approbation", "Actions corrigées/réverties / actions exécutées.", NEW_DB),
            Metric("HITL-10", "Taux de clarification", "Clarifications / workflows.", EXISTING),
            Metric("HITL-11", "Clarification utile", "Succès au tour suivant / clarifications répondues.", NEW_DB),
            Metric("HITL-12", "Abandon après clarification", "Abandons / clarifications présentées.", NEW_DB),
            Metric("HITL-13", "Sous-clarification probable", "Corrections sans clarification / workflows sans clarification.", DERIVED),
            Metric("HITL-14", "Itérations de brouillon", "Médiane des éditions avant confirmation.", EXISTING),
            Metric("HITL-15", "Brouillons exécutés", "Brouillons exécutés / créés.", EXISTING),
            Metric("HITL-16", "Brouillons annulés", "Brouillons annulés / créés.", EXISTING),
            Metric("HITL-17", "Durée du cycle brouillon", "Création vers exécution, annulation ou expiration.", EXISTING),
            Metric("HITL-18", "Décisions par niveau HITL", "Répartition des décisions selon les niveaux de validation.", PARTIAL),
        ],
    ),
    (
        "Connecteurs",
        [
            Metric("CON-01", "Initiations de connexion", "Nombre de flux OAuth/connecteur initiés.", EXISTING),
            Metric("CON-02", "Activation réussie", "Connecteurs activés / initiations.", EXISTING),
            Metric("CON-03", "Abandon OAuth", "Initiations sans état terminal / initiations.", PARTIAL),
            Metric("CON-04", "Durée d'activation", "P50/P95 de l'activation.", EXISTING),
            Metric("CON-05", "Couverture utilisateurs", "Utilisateurs avec au moins un connecteur actif / éligibles.", EXISTING),
            Metric("CON-06", "Connecteur réellement utilisé", "Connecteurs utilisés / connecteurs actifs.", NEW_DB),
            Metric("CON-07", "Activation vers premier usage", "Premier usage - activation.", NEW_DB),
            Metric("CON-08", "Succès API connecteur", "Appels réussis / appels.", EXISTING),
            Metric("CON-09", "Réauthentification nécessaire", "Connecteurs expirés / actifs.", PARTIAL),
            Metric("CON-10", "Réactivation réussie", "Réactivations réussies / requises.", NEW_DB),
            Metric("CON-11", "Donnée obsolète", "Workflows utilisant une donnée hors fenêtre de fraîcheur.", NEW_DB),
            Metric("CON-12", "Échec imputable au connecteur", "Workflows échoués par dépendance / workflows dépendants.", PARTIAL),
            Metric("CON-13", "Résultat utile avec connecteur", "E1/E2 / workflows dépendants.", NEW_DB),
            Metric("CON-14", "Valeur par type de connecteur", "Utilisateurs utiles et résultats utiles par type.", DERIVED),
        ],
    ),
    (
        "Routines, automatisations et proactivité",
        [
            Metric("AUT-01", "Routines créées", "Nombre de routines persistées.", PARTIAL),
            Metric("AUT-02", "Routines activées", "Routines actives / créées.", NEW_DB),
            Metric("AUT-03", "Première exécution", "Routines exécutées au moins une fois / créées.", PARTIAL),
            Metric("AUT-04", "Première exécution utile", "Routines avec sortie E1/E2 / créées.", NEW_DB),
            Metric("AUT-05", "Délai d'activation routine", "Création vers première sortie utile.", DERIVED),
            Metric("AUT-06", "Exécutions attendues", "Nombre de runs dus.", NEW_DB),
            Metric("AUT-07", "Exécutions à l'heure", "Runs démarrés dans la tolérance / dus.", NEW_DB),
            Metric("AUT-08", "Succès technique routine", "Runs réussis / démarrés.", PARTIAL),
            Metric("AUT-09", "Sortie utile routine", "Runs E1/E2 / terminés.", NEW_DB),
            Metric("AUT-10", "Sortie ignorée", "Sorties sans interaction / présentées.", NEW_CLIENT),
            Metric("AUT-11", "No-op", "Runs sans information nouvelle / runs.", NEW_DB),
            Metric("AUT-12", "Échec routine", "Runs échoués / démarrés.", PARTIAL),
            Metric("AUT-13", "Échecs consécutifs", "Distribution et P95 des consecutive_failures.", EXISTING),
            Metric("AUT-14", "Désactivation automatique", "Routines auto-désactivées / actives.", PARTIAL),
            Metric("AUT-15", "Intervention utilisateur", "Runs nécessitant reprise manuelle / runs.", NEW_DB),
            Metric("AUT-16", "Pause utilisateur", "Routines mises en pause / actives.", NEW_DB),
            Metric("AUT-17", "Survie 4 et 12 semaines", "Routines utiles encore actives à S+4/S+12.", DERIVED),
            Metric("AUT-18", "Coût par run utile", "Coût automation / runs E1/E2.", DERIVED),
            Metric("AUT-19", "Retard d'exécution", "P50/P95 de début réel - heure prévue.", NEW_DB),
            Metric("PRO-01", "Éléments proactifs générés", "Nombre de suggestions créées.", EXISTING),
            Metric("PRO-02", "Livraison", "Notifications délivrées / tentées.", EXISTING),
            Metric("PRO-03", "Ouverture", "Notifications ouvertes / délivrées.", NEW_CLIENT),
            Metric("PRO-04", "Action", "Notifications actionnées / délivrées.", NEW_CLIENT),
            Metric("PRO-05", "Utilité proactive", "Notifications E1/E2 / délivrées.", NEW_DB),
            Metric("PRO-06", "Utilité après ouverture", "Notifications E1/E2 / ouvertes.", DERIVED),
            Metric("PRO-07", "Feedback négatif proactif", "Pouces négatifs / feedbacks.", EXISTING),
            Metric("PRO-08", "Blocage", "Block / notifications évaluées.", EXISTING),
            Metric("PRO-09", "Désactivation notifications", "Utilisateurs désactivant / exposés.", NEW_CLIENT),
            Metric("PRO-10", "Dismissal", "Notifications fermées / délivrées.", NEW_CLIENT),
            Metric("PRO-11", "Bruit proactif", "Notifications sans ouverture, action ou feedback.", DERIVED),
            Metric("PRO-12", "Doublon évité", "Suggestions dédupliquées / candidates.", PARTIAL),
            Metric("PRO-13", "Pertinence temporelle", "Actions réalisées dans la fenêtre utile.", NEW_DB),
            Metric("PRO-14", "Coût par notification utile", "Coût proactif / notifications E1/E2.", DERIVED),
            Metric("PRO-15", "Valeur par source proactive", "Utilité par intérêts, heartbeat, briefing et routines.", DERIVED),
        ],
    ),
    (
        "Recherche, mobile et UX",
        [
            Metric("SEA-01", "Recherches", "Nombre de recherches valides.", NEW_CLIENT),
            Metric("SEA-02", "Zéro résultat", "Recherches sans résultat / recherches.", NEW_CLIENT),
            Metric("SEA-03", "Résultat ouvert", "Recherches avec ouverture / recherches.", NEW_CLIENT),
            Metric("SEA-04", "Résultat utilisé", "Recherches avec action utile / recherches.", NEW_CLIENT),
            Metric("SEA-05", "Reformulation", "Recherches reformulées / recherches.", NEW_CLIENT),
            Metric("SEA-06", "Succès après reformulation", "Reformulations avec usage / reformulations.", DERIVED),
            Metric("SEA-07", "Abandon après zéro résultat", "Zéro résultat sans suite / zéro résultat.", DERIVED),
            Metric("SEA-08", "Recherche vers chat", "Transferts vers chat / recherches.", NEW_CLIENT),
            Metric("SEA-09", "Temps jusqu'au résultat", "Soumission vers ouverture ou usage.", NEW_CLIENT),
            Metric("SEA-10", "Résultats présents inutilisés", "Recherches avec résultat mais sans ouverture/action.", DERIVED),
            Metric("UX-01", "Résultat utile mobile", "Utilisateurs mobiles E1/E2 / engagés mobile.", NEW_CLIENT),
            Metric("UX-02", "Écart mobile/desktop", "Taux utile mobile - taux utile desktop.", DERIVED),
            Metric("UX-03", "Activation mobile", "Première valeur mobile / inscrits mobile.", DERIVED),
            Metric("UX-04", "Réussite mobile end-to-end", "Workflows mobiles réussis / commencés.", NEW_CLIENT),
            Metric("UX-05", "Délai première valeur mobile", "P50/P95.", DERIVED),
            Metric("UX-06", "Abandon mobile", "Abandons mobiles / workflows mobiles.", NEW_CLIENT),
            Metric("UX-07", "Approbation mobile", "Approbations mobiles finalisées / présentées.", NEW_CLIENT),
            Metric("UX-08", "Upload mobile", "Uploads mobiles réussis / tentés.", PARTIAL),
            Metric("UX-09", "Usage vocal mobile utile", "Sessions vocales utiles / sessions vocales.", NEW_DB),
            Metric("UX-10", "Adoption et rétention PWA", "Installations et rétention utile PWA vs navigateur.", NEW_CLIENT),
            Metric("UX-11", "Cibles tactiles conformes", "Cibles conformes / cibles testées.", QA),
            Metric("UX-12", "Régressions responsive", "Écarts détectés par campagnes visuelles.", QA),
            Metric("UX-13", "Parité clair/sombre", "Écrans conformes dans les deux thèmes.", QA),
            Metric("UX-14", "Parité desktop/mobile", "Parcours critiques disponibles et utilisables.", QA),
            Metric("UX-15", "Navigation clavier", "Parcours critiques terminables au clavier.", QA),
            Metric("UX-16", "Erreurs d'interaction", "Clics sans effet, doubles soumissions, contrôles bloqués.", NEW_CLIENT),
            Metric("UX-17", "Complétion des tâches UX", "Parcours de référence terminés sans aide / tentés.", QA),
        ],
    ),
    (
        "Performance et fiabilité perçue",
        [
            Metric("PERF-01", "TTFT", "Demande vers premier token, P50/P95.", EXISTING),
            Metric("PERF-02", "Premier statut utile", "Demande vers premier feedback d'avancement.", PARTIAL),
            Metric("PERF-03", "Temps de production", "Demande vers result_produced.", PARTIAL),
            Metric("PERF-04", "Temps de présentation", "Demande vers result_presented.", NEW_CLIENT),
            Metric("PERF-05", "Durée silencieuse maximale", "Plus longue période sans feedback.", NEW_CLIENT),
            Metric("PERF-06", "Latence end-to-end", "P50/P75/P95.", EXISTING),
            Metric("PERF-07", "Annulation de génération", "Streams annulés / streams.", PARTIAL),
            Metric("PERF-08", "Abandon pendant attente", "Workflows quittés avant résultat.", NEW_CLIENT),
            Metric("PERF-09", "Erreur streaming", "Streams échoués / démarrés.", EXISTING),
            Metric("PERF-10", "Reconnexion SSE", "Streams reconnectés / interrompus.", NEW_CLIENT),
            Metric("PERF-11", "Timeout", "Workflows expirés / commencés.", EXISTING),
            Metric("PERF-12", "Sessions sans erreur", "Sessions sans erreur client/serveur / sessions.", NEW_CLIENT),
            Metric("PERF-13", "Requêtes sans erreur", "Réponses non 5xx / requêtes.", EXISTING),
            Metric("PERF-14", "Succès outils", "Appels d'outils réussis / appels.", EXISTING),
            Metric("PERF-15", "Latence outils", "P50/P95 par outil.", EXISTING),
            Metric("PERF-16", "Latence fournisseurs LLM", "P50/P95 par fournisseur.", EXISTING),
            Metric("PERF-17", "LCP/INP/CLS", "P75 mobile et desktop.", NEW_CLIENT),
            Metric("PERF-18", "Crash frontend", "Sessions avec exception non récupérée / sessions.", NEW_CLIENT),
        ],
    ),
    (
        "Coûts et efficacité",
        [
            Metric("COST-01", "Coût total", "LLM + API + image + STT + TTS.", EXISTING),
            Metric("COST-02", "Coût par utilisateur engagé", "Coût / utilisateurs engagés.", DERIVED),
            Metric("COST-03", "Coût par utilisateur utile", "Coût / utilisateurs E1/E2.", DERIVED),
            Metric("COST-04", "Coût par résultat produit", "Coût / résultats produits.", DERIVED),
            Metric("COST-05", "Coût par résultat utile", "Coût / résultats E1/E2.", NEW_DB),
            Metric("COST-06", "Coût du premier passage", "Coût / résultats first_pass utiles.", DERIVED),
            Metric("COST-07", "Coût des corrections", "Coût des tentatives correctives.", NEW_DB),
            Metric("COST-08", "Coût gaspillé", "Coût des échecs, rejets et abandons.", NEW_DB),
            Metric("COST-09", "Coût par domaine", "Ventilation par domaine borné.", PARTIAL),
            Metric("COST-10", "Coût Pipeline/ReAct", "Comparaison normalisée par type de demande.", PARTIAL),
            Metric("COST-11", "Coût par modèle/fournisseur", "Ventilation des coûts.", EXISTING),
            Metric("COST-12", "Tokens par résultat utile", "Tokens totaux / E1/E2.", NEW_DB),
            Metric("COST-13", "Cache utile", "Coût évité grâce aux tokens cache.", PARTIAL),
            Metric("COST-14", "Blocage par limite", "Workflows bloqués par budget / workflows.", EXISTING),
            Metric("COST-15", "Coût routines utiles", "Coût automation / sorties utiles.", DERIVED),
            Metric("COST-16", "Coût proactif utile", "Coût proactif / notifications utiles.", DERIVED),
        ],
    ),
    (
        "Satisfaction et qualité des données",
        [
            Metric("SAT-01", "Feedback positif brut", "Pouces positifs / résultats présentés.", PARTIAL),
            Metric("SAT-02", "Feedback négatif brut", "Pouces négatifs / résultats présentés.", PARTIAL),
            Metric("SAT-03", "Positif parmi les notés", "Pouces positifs / positifs + négatifs.", EXISTING),
            Metric("SAT-04", "Couverture du feedback", "Résultats notés / résultats présentés.", NEW_DB),
            Metric("SAT-05", "Commentaire négatif", "Négatifs avec commentaire / négatifs.", PARTIAL),
            Metric("SAT-06", "CSAT contextuel", "Moyenne des réponses échantillonnées.", NEW_CLIENT),
            Metric("SAT-07", "Feedback proactif", "Positifs, négatifs et block par source proactive.", EXISTING),
            Metric("SAT-08", "Motifs d'insatisfaction", "Répartition des catégories structurées.", NEW_CLIENT),
            Metric("DQ-01", "Événements acceptés", "Événements valides / reçus.", NEW_PROM),
            Metric("DQ-02", "Événements dupliqués", "Doublons / événements reçus.", NEW_PROM),
            Metric("DQ-03", "Événements en retard", "Événements reçus après SLA / reçus.", NEW_DB),
            Metric("DQ-04", "Fraîcheur du pipeline", "Maintenant - dernier agrégat réussi.", NEW_PROM),
            Metric("DQ-05", "Workflows sans identifiant", "Workflows sans workflow_id / workflows.", NEW_DB),
            Metric("DQ-06", "Résultats sans identifiant", "Résultats sans result_id / résultats.", NEW_DB),
            Metric("DQ-07", "Résultats orphelins", "Résultats sans workflow valide / résultats.", NEW_DB),
            Metric("DQ-08", "Dimensions manquantes", "Événements sans domaine, mode, canal ou version.", NEW_DB),
            Metric("DQ-09", "Schémas inconnus", "Événements de version non prise en charge.", NEW_PROM),
            Metric("DQ-10", "Divergence backend/analytics", "Écart de volumes équivalents.", DERIVED),
            Metric("DQ-11", "Couverture des terminaux", "Workflows avec état terminal / workflows.", DERIVED),
            Metric("DQ-12", "Réconciliation des coûts", "Écart agrégats produit vs message_token_summary.", DERIVED),
            Metric("DQ-13", "Tests de métriques réussis", "Tests contractuels réussis / exécutés.", QA),
        ],
    ),
]


existing_metric_rows = [
    ("Activité", "user_active_daily_gauge, user_active_weekly_gauge", "Réutiliser comme activité conversationnelle, ne pas les appeler engagement produit complet.", "Dashboards 01, 09, 17"),
    ("Inscriptions", "user_registrations_total, users_registered_last_24h", "Réutiliser pour acquisition et funnel.", "Dashboards 01/17"),
    ("Feedback réponses", "response_feedback_total{verdict}", "Réutiliser le volume; compléter par le dénominateur result_presented.", "Nouveau dashboard 26"),
    ("Feedback proactif", "proactive_feedback_total{task_type,feedback_type}", "Réutiliser pour utilité et bruit proactifs.", "Dashboard 13 + 26"),
    ("Abandon", "conversation_abandonment_total, business:slo:abandonment_rate:24h", "Réutiliser comme signal partiel; compléter par workflow_id et phase.", "Dashboards 02, 09, 17"),
    ("Succès agent", "agent_success_rate_total{agent_type,outcome}", "Réutiliser comme succès technique E3.", "Dashboard 26 diagnostic"),
    ("Outils", "agent_tool_usage_total, business:tool_success_rate:5m_by_tool", "Réutiliser pour diagnostic, jamais comme valeur utilisateur.", "Dashboards 07, 17"),
    ("Coûts", "conversation_cost_usd, cost_per_successful_conversation_usd", "Réutiliser, puis rattacher au result_id via run_id.", "Dashboards 05, 09"),
    ("Tours", "conversation_turns_total", "Réutiliser pour profondeur; ajouter tours jusqu'au résultat utile.", "Dashboard 09 + 26"),
    ("HITL", "hitl_resolutions_total, hitl_wait_duration_seconds", "Réutiliser pour décision et latence.", "Dashboard 08 + 26"),
    ("HITL classification", "hitl_classification_method_total, hitl_clarification_requests_total", "Réutiliser pour clarifications et décisions.", "Dashboard 08 + 26"),
    ("Reprise HITL", "hitl_resumption_total, hitl_resumption_duration_seconds", "Réutiliser pour succès post-décision technique.", "Dashboard 08 + 26"),
    ("Brouillons", "registry_drafts_created_total, registry_drafts_executed_total", "Réutiliser pour conversion brouillon.", "Dashboard 14 + 26"),
    ("Cycle brouillon", "registry_draft_actions_total, registry_draft_lifecycle_duration_seconds", "Réutiliser pour éditions, annulations et durée.", "Dashboard 14 + 26"),
    ("OAuth", "oauth_initiate_total, oauth_connector_activation_total", "Réutiliser pour le funnel de connexion.", "Dashboard 10 + 26"),
    ("Activation connecteur", "connector_activation_rate", "Réutiliser; le gauge est déjà calculé depuis PostgreSQL.", "Dashboards 09, 10"),
    ("API connecteurs", "connector_api_requests_total, connector_api_errors_total", "Réutiliser pour fiabilité.", "Dashboard 10 + 26"),
    ("Streaming", "sse_time_to_first_token_seconds, sse_streaming_errors_total", "Réutiliser pour performance perçue.", "Dashboards 07, 15 + 26"),
    ("ReAct", "react_agent_executions_total, react_agent_duration_seconds", "Réutiliser pour comparer les modes.", "Dashboard 20 + 26"),
    ("Briefing", "briefing_refresh_requests_total, briefing_section_status_total", "Réutiliser pour adoption et fiabilité du rituel.", "Dashboard 25 + 26"),
    ("Proactivité", "proactive_task_success_total, proactive_cost_eur_total", "Réutiliser pour coût et succès technique.", "Dashboard 13 + 26"),
    ("Routines DB", "scheduled_actions.execution_count, consecutive_failures, last_executed_at", "Agréger depuis PostgreSQL; aucune série utilisateur dans Prometheus.", "Dashboard 26"),
    ("Tokens/coûts DB", "message_token_summary, user_statistics", "Source durable à relier aux outcomes.", "Dashboard 05 + 26"),
]


new_prometheus_rows = [
    ("product_workflows_total", "Counter", "domain, execution_mode, channel, outcome", "Volumes end-to-end bornés."),
    ("product_outcomes_total", "Counter", "result_type, evidence, domain, execution_mode, status", "Résultats produits et validés."),
    ("product_outcome_duration_seconds", "Histogram", "result_type, domain, execution_mode, outcome", "Temps jusqu'au résultat."),
    ("product_outcome_turns", "Histogram", "result_type, domain, outcome", "Tours jusqu'au résultat."),
    ("product_outcome_cost_eur", "Histogram", "result_type, domain, evidence", "Coût par outcome."),
    ("product_users_with_useful_outcome", "Gauge DB-backed", "window, evidence, device_class", "North Star et diffusion."),
    ("product_value_penetration_ratio", "Gauge DB-backed", "window, device_class", "NS-02."),
    ("product_activation_rate", "Gauge DB-backed", "window, path, device_class", "Activation 24 h/7 j."),
    ("product_time_to_first_value_seconds", "Gauge DB-backed", "quantile, path, device_class", "P50/P95 première valeur."),
    ("product_retention_rate", "Gauge DB-backed", "period, segment", "D1/D7/D30 et utile."),
    ("product_funnel_users", "Gauge DB-backed", "stage, window, device_class", "Funnel courant."),
    ("product_search_total", "Counter", "surface, outcome, device_class", "Recherche, zéro résultat et usage."),
    ("product_client_sessions_total", "Counter", "device_class, channel, outcome", "Sessions et erreurs frontend."),
    ("product_web_vital_seconds", "Histogram", "metric, device_class", "LCP et INP; CLS via ratio dédié."),
    ("product_web_vital_ratio", "Histogram", "metric, device_class", "CLS et ratios sans unité."),
    ("product_data_quality_ratio", "Gauge DB-backed", "check", "Qualité des données."),
    ("product_metrics_last_refresh_timestamp_seconds", "Gauge", "job", "Fraîcheur des agrégats."),
]


dashboard_rows = [
    ("00", "Synthèse exécutive", "12", "Visible", "North Star, pénétration, activation, premier passage, succès E2E, rétention D7, coût, délai, mobile, feedback négatif, couverture et fraîcheur."),
    ("01", "North Star et valeur", "6", "Visible", "Tendance 12 semaines, E1/E2, profondeur médiane, répartition domaine et type de résultat."),
    ("02", "Funnel d'activation", "6", "Visible", "Inscription vers seconde semaine utile, chemins source/démo, conversion et temps inter-étapes."),
    ("03", "Qualité agentique", "8", "Repliée", "Succès E2E, premier passage, faux succès, corrections, retries, tours, durée, Pipeline/ReAct."),
    ("04", "HITL et brouillons", "8", "Repliée", "Approbations, édition, abandon, latence, reprise, regret, clarifications et drafts."),
    ("05", "Engagement et rétention", "8", "Repliée", "DAU/WAU/MAU engagés, stickiness, cohortes D1/D7/D30, résurrection, semaines utiles."),
    ("06", "Connecteurs", "7", "Repliée", "Activation, couverture, usage réel, fraîcheur, réauthentification, succès API et valeur."),
    ("07", "Routines et proactivité", "9", "Repliée", "Activation, ponctualité, sortie utile, bruit, survie, coûts, notifications et feedback."),
    ("08", "Recherche, mobile et UX", "9", "Repliée", "Zéro résultat, reformulation, mobile/desktop, PWA, Web Vitals, cibles tactiles et parité visuelle."),
    ("09", "Coûts et efficacité", "8", "Repliée", "Coût total, par utile, gaspillage, correction, domaine, mode, fournisseur et routines."),
    ("10", "Qualité des données", "7", "Visible", "Fraîcheur, invalides, doublons, orphelins, couverture IDs, réconciliation et tests."),
]


panel_rows = [
    ("1", "Utilisateurs avec résultat utile - 7 j", "Stat", "PostgreSQL", "NS-01", "Valeur, variation WoW, sparkline."),
    ("2", "Pénétration de la valeur", "Gauge", "PostgreSQL", "NS-02", "Résultats utiles / utilisateurs engagés."),
    ("3", "Résultats utiles par utilisateur", "Stat", "PostgreSQL", "NS-03", "Médiane et P75."),
    ("4", "Activation à 7 jours", "Stat", "PostgreSQL", "ACT-02", "Cohorte d'inscription."),
    ("5", "Utile au premier passage", "Gauge", "PostgreSQL", "OUT-04", "Vert si amélioration vs baseline."),
    ("6", "Succès end-to-end", "Gauge", "Mixte", "OUT-03", "Technique et résultat final."),
    ("7", "Rétention utile D7", "Stat", "PostgreSQL", "RET-02", "Cohorte activée."),
    ("8", "Coût par résultat utile", "Stat", "Mixte", "COST-05", "EUR, variation 7 j."),
    ("9", "Temps jusqu'au résultat utile", "Stat", "Mixte", "OUT-16", "P50 et P95."),
    ("10", "Écart mobile/desktop", "Stat", "PostgreSQL", "UX-02", "Points de pourcentage."),
    ("11", "Feedback négatif", "Stat", "Prometheus", "SAT-02", "Avec couverture de feedback."),
    ("12", "Couverture et fraîcheur", "Stat", "Mixte", "NS-06/DQ-04", "Deux valeurs compactes."),
    ("13", "North Star - 12 semaines", "Time series", "PostgreSQL", "NS-01", "E1 et E2 empilés."),
    ("14", "Valeur par domaine", "Bar chart", "PostgreSQL", "OUT-20", "Domaines bornés."),
    ("15", "Valeur par type de résultat", "Bar chart", "PostgreSQL", "NS-04", "Answer/action/artifact/etc."),
    ("16", "Funnel principal", "Funnel/Bar gauge", "PostgreSQL", "FUN-01..11", "Cohorte et période sélectionnées."),
    ("17", "Conversion par chemin", "Bar chart", "PostgreSQL", "ACT-07..11", "Connecteur, démo, sans source."),
    ("18", "Temps inter-étapes", "Heatmap", "PostgreSQL", "FUN-12", "P50/P95."),
    ("19", "Qualité du résultat", "Time series", "Mixte", "OUT-02..08", "Utile, first-pass, correction, faux succès."),
    ("20", "Tours et tentatives", "Heatmap", "Prometheus", "OUT-14/15", "Par domaine."),
    ("21", "Pipeline vs ReAct", "Table", "Mixte", "OUT-21", "Utilité, coût, durée, corrections."),
    ("22", "Décisions HITL", "Time series", "Prometheus", "HITL-01..05", "Approve/edit/reject/abandon."),
    ("23", "Latence et succès HITL", "Time series", "Prometheus", "HITL-06..09", "Décision, reprise et regret."),
    ("24", "Clarifications", "Bar chart", "Mixte", "HITL-10..13", "Taux, utilité, abandon."),
    ("25", "Cycle des brouillons", "Table", "Prometheus", "HITL-14..17", "Par draft_type."),
    ("26", "Engagement DAU/WAU/MAU", "Time series", "Mixte", "ENG-01..05", "Définition engagée."),
    ("27", "Rétention D1/D7/D30", "Cohort heatmap", "PostgreSQL", "RET-01..03", "Cohortes hebdomadaires."),
    ("28", "Semaines utiles et résurrection", "Time series", "PostgreSQL", "RET-04..07", "Habitude et retour."),
    ("29", "Funnel connecteur", "Bar chart", "Mixte", "CON-01..07", "Activation vers usage réel."),
    ("30", "Valeur et fiabilité connecteurs", "Table", "Mixte", "CON-08..14", "Par type de connecteur."),
    ("31", "Routines actives et activées", "Time series", "PostgreSQL", "AUT-01..05", "Création vers première utilité."),
    ("32", "Fiabilité et ponctualité", "Time series", "PostgreSQL", "AUT-06..14", "Runs dus, on-time, succès, auto-disable."),
    ("33", "Utilité et survie routines", "Cohort/Table", "PostgreSQL", "AUT-09..19", "Sorties utiles, survie et coût."),
    ("34", "Proactivité utile", "Time series", "Mixte", "PRO-01..06", "Delivery/open/action/useful."),
    ("35", "Bruit et feedback proactifs", "Bar chart", "Mixte", "PRO-07..15", "Negative, block, disable, noise."),
    ("36", "Recherche", "Time series", "Prometheus", "SEA-01..10", "Zero result, open, use, reformulate."),
    ("37", "Parité mobile/desktop", "Table", "PostgreSQL", "UX-01..10", "Activation, E2E, délai, abandon."),
    ("38", "Qualité UX automatisée", "Status history", "QA export", "UX-11..17", "Touch, themes, responsive, keyboard."),
    ("39", "Web Vitals et erreurs client", "Time series", "Prometheus", "PERF-17/18", "P75 par device."),
    ("40", "Performance perçue", "Time series", "Prometheus", "PERF-01..16", "TTFT, silence, total, streaming."),
    ("41", "Coût produit", "Time series", "Mixte", "COST-01..16", "Total, utile, gaspillé et correction."),
    ("42", "Qualité des données", "Status history", "Mixte", "DQ-01..13", "SLA, orphelins, reconciliation."),
]


requirements_rows = [
    ("P0", "Dashboard Grafana 26", "Créer 26-product-value.json, uid lia-product-value, tags lia/product/value, refresh 5m, période 30 j."),
    ("P0", "Réutilisation avant création", "Chaque panel doit référencer une source existante ou justifier une nouvelle métrique."),
    ("P0", "Aucune dépendance Langfuse", "Ni source, ni variable, ni lien, ni métrique dans le dashboard ou l'architecture."),
    ("P0", "Datasource Prometheus", "Réutiliser uid prometheus pour temps réel et diagnostics."),
    ("P0", "Datasource PostgreSQL produit", "Ajouter uid postgres-product-readonly sur vues dédiées en lecture seule."),
    ("P0", "Outcome canonique", "Introduire result_id, workflow_id, evidence_level et état de résultat durable."),
    ("P0", "North Star", "Calcul exact depuis PostgreSQL, E1/E2 seulement, déduplication par result_id."),
    ("P0", "Scorecard exécutive", "12 panels maximum, lisibles sans ouvrir de ligne diagnostique."),
    ("P0", "Qualité des données", "Fraîcheur, couverture, doublons, orphelins et réconciliation visibles."),
    ("P0", "Tests", "Validation JSON dashboard, PromQL, SQL, cardinalité, données vides et timezones."),
    ("P1", "Funnel client", "Instrumentation landing, démo, objectif, recherche, mobile et PWA."),
    ("P1", "Cohortes", "Vues activation et rétention hebdomadaires, heatmap Grafana."),
    ("P1", "Automatisation utile", "Relier les runs planifiés aux résultats produits et utilisés."),
    ("P1", "Alertes produit", "Alertes relatives à baseline après 4 semaines fiables."),
    ("P1", "QA UX exportée", "Publier les résultats de tests responsive, tactile et thèmes."),
    ("P2", "Expérimentations", "Ajouter dimensions variant/feature flag si des A/B tests existent."),
    ("P2", "Économie", "Ajouter MRR/ARR/marge seulement si la monétisation devient structurée."),
]


acceptance_rows = [
    ("Dashboard", "Le dashboard 26 est provisionné, charge sans erreur et n'altère aucun dashboard 01-25."),
    ("Dashboard", "La ligne 00 tient sur un écran desktop standard et affiche 12 panels au maximum."),
    ("Dashboard", "Toutes les lignes diagnostiques sont repliables; les variables filtrent sans casser les requêtes."),
    ("Architecture", "Aucune requête, source, variable ou lien ne dépend d'une plateforme analytics ou de tracing tierce."),
    ("Prometheus", "Aucun label ne contient user_id, workflow_id, result_id, UUID ou texte libre."),
    ("PostgreSQL", "Les requêtes Grafana ciblent uniquement des vues produit en lecture seule."),
    ("North Star", "Un utilisateur n'est compté qu'une fois par semaine; un résultat n'est compté qu'une fois."),
    ("North Star", "E3 est exclu; la ventilation E1/E2 est visible."),
    ("Funnel", "Les chemins démo, connecteur et sans source restent séparables."),
    ("Qualité", "Les métriques sans données affichent N/A et non zéro."),
    ("Qualité", "Les volumes Prometheus et PostgreSQL équivalents divergent de moins de 1 %."),
    ("Qualité", "La date de dernier refresh est visible et déclenche une alerte au-delà du SLA."),
    ("Responsive", "Le dashboard reste utilisable à 1440, 1024 et 390 px sans panneau illisible."),
    ("Performance", "Le chargement du dashboard ne déclenche pas de requête SQL non bornée."),
    ("Documentation", "Le dictionnaire des métriques définit nom, formule, dénominateur, source, owner et version."),
]


def metric_catalog_story() -> list:
    """Build all metric catalog sections."""
    story: list = []
    for title, metrics in metric_groups:
        story.append(h2(title))
        rows = [(m.identifier, m.name, m.formula, m.source) for m in metrics]
        story.append(
            simple_table(
                ["ID", "Indicateur", "Définition ou formule", "Source"],
                rows,
                [14, 44, 91, 24],
            )
        )
        story.append(Spacer(1, 3 * mm))
    return story


def build_story() -> list:
    """Build the complete PDF story."""
    story: list = []

    # Cover
    cover = Table(
        [
            [
                p(
                    "LIA",
                    "CoverTitle",
                )
            ],
            [
                p(
                    "Spécification du dashboard Grafana Produit",
                    "CoverTitle",
                )
            ],
            [
                p(
                    "Valeur utilisateur, activation, qualité des résultats, rétention et efficacité",
                    "CoverSubtitle",
                )
            ],
        ],
        colWidths=[173 * mm],
        rowHeights=[18 * mm, None, None],
    )
    cover.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), NAVY),
                ("LEFTPADDING", (0, 0), (-1, -1), 12 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 8 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8 * mm),
            ]
        )
    )
    story.extend(
        [
            Spacer(1, 18 * mm),
            cover,
            Spacer(1, 10 * mm),
            callout(
                "<b>Décision majeure :</b> architecture 100 % native à la stack LIA. Le dashboard produit réutilise les métriques Prometheus et les 25 dashboards Grafana existants, puis ajoute des vues PostgreSQL en lecture seule pour les utilisateurs uniques, funnels et cohortes.",
                colors.HexColor("#E9F8F2"),
            ),
            Spacer(1, 10 * mm),
            simple_table(
                ["Champ", "Valeur"],
                [
                    ("Version", "1.1"),
                    ("Date", "29 juillet 2026"),
                    ("Statut", "Proposition normative prête pour revue"),
                    ("Dashboard cible", "26 - Produit : valeur, activation et rétention"),
                    ("Datasources", "Prometheus existant + PostgreSQL produit en lecture seule"),
                    ("Exclusions", "Plateforme analytics ou tracing tierce, tracking exhaustif des clics"),
                ],
                [42, 131],
                font_size="Smallx",
            ),
            Spacer(1, 18 * mm),
            p(
                "Document généré à partir du dépôt LIA courant. Les métriques sont classées en existantes, partielles, dérivées ou nouvelles afin d'éviter de reconstruire ce qui fonctionne déjà.",
                "FooterNote",
            ),
            PageBreak(),
        ]
    )

    story.extend(
        [
            h1("1. Résumé exécutif"),
            p(
                "LIA dispose déjà d'une base d'observabilité très mature : 25 dashboards Grafana, des métriques Prometheus sur les utilisateurs, conversations, agents, HITL, connecteurs, coûts, proactivité, briefing, voix et recherches techniques. Le besoin n'est pas un nouveau système d'observabilité mais une vue produit unifiée répondant à une question : combien d'utilisateurs obtiennent une valeur réelle, avec quelle qualité, à quel coût, et reviennent-ils ?"
            ),
            callout(
                "<b>Recommandation :</b> créer le dashboard <b>26-product-value.json</b> avec une scorecard exécutive visible et dix lignes diagnostiques repliables. Les panels temps réel réutilisent Prometheus; les utilisateurs uniques, cohortes et funnels exacts interrogent des vues PostgreSQL dédiées."
            ),
            h2("Ce qui change par rapport à la version précédente"),
            bullet("Langfuse est entièrement retiré de l'architecture, des métriques, des panels et des dépendances."),
            bullet("Grafana devient l'unique surface de restitution du système de métriques produit."),
            bullet("Les 25 dashboards actuels restent les vues techniques de détail; le dashboard 26 les synthétise sans les dupliquer."),
            bullet("Prometheus reste la source des séries temps réel et opérationnelles."),
            bullet("PostgreSQL fournit les agrégats exacts nécessitant des utilisateurs uniques, de la déduplication ou des cohortes."),
            bullet("Les métriques nouvelles sont strictement limitées aux concepts absents : résultat utile, première valeur, correction, réversion, funnel, cohortes, mobile et qualité data."),
            h2("North Star recommandée"),
            callout(
                "<b>Utilisateurs hebdomadaires ayant obtenu au moins un résultat utile validé.</b><br/>Un résultat validé est soit explicitement confirmé par l'utilisateur (E1), soit validé par un comportement fort (E2). Un simple succès technique E3 est exclu.",
                colors.HexColor("#FFF7E6"),
            ),
            h2("Principes de conception du dashboard"),
            bullet("Décision avant diagnostic : la première ligne doit indiquer la santé produit en moins de 30 secondes."),
            bullet("Contexte systématique : valeur actuelle, précédente, variation, cible et dénominateur."),
            bullet("Pas de faux zéros : absence de données = N/A."),
            bullet("Aucune série Prometheus à forte cardinalité."),
            bullet("Une métrique nouvelle doit avoir un owner, une formule, une source et un test."),
            bullet("Les lignes diagnostiques restent repliées par défaut."),
            PageBreak(),
        ]
    )

    story.extend(
        [
            h1("2. État actuel et stratégie de réutilisation"),
            p(
                "L'inventaire confirme que les indicateurs utiles sont dispersés entre les dashboards 01, 02, 05, 07, 08, 09, 10, 13, 14, 17, 20, 25 et les recording rules business. Le dashboard produit ne doit pas remplacer ces vues mais fournir un cockpit de décision et des liens de drill-down."
            ),
            simple_table(
                ["Domaine", "Métriques ou données existantes", "Décision", "Destination"],
                existing_metric_rows,
                [27, 58, 63, 25],
                padding_mm=0.95,
            ),
            Spacer(1, 3 * mm),
            callout(
                "<b>Point de vigilance :</b> user_active_daily_gauge et user_active_weekly_gauge reposent actuellement sur les conversations mises à jour. Ils mesurent une activité conversationnelle, pas encore l'ensemble des utilisateurs engagés par routine, proactivité ou projet."
            ),
            h2("Gaps réellement bloquants"),
            bullet("Pas d'identifiant canonique de résultat utile relié au workflow et au coût."),
            bullet("Pas de distinction persistante E1/E2/E3."),
            bullet("Pas de funnel complet inscription vers première valeur."),
            bullet("Pas de cohortes d'activation et de rétention utile."),
            bullet("Pas de segmentation produit mobile/desktop/PWA."),
            bullet("Pas de mesure complète de correction, réversion ou usage d'un résultat."),
            bullet("Pas de contrôle consolidé de la qualité de la donnée produit."),
            PageBreak(),
        ]
    )

    story.extend(
        [
            h1("3. Architecture Grafana produit"),
            h2("Sources et responsabilités"),
            simple_table(
                ["Composant", "Responsabilité", "Contenu", "Interdit"],
                [
                    ("Prometheus", "Temps réel, alertes, distributions", "Counters, gauges DB-backed, histograms, recording rules", "user_id, result_id, UUID, texte libre"),
                    ("PostgreSQL", "Vérité produit durable", "Outcomes, funnels, cohortes, agrégats journaliers", "Requêtes Grafana sur tables métier brutes"),
                    ("Grafana", "Restitution et drill-down", "Dashboard 26, variables, annotations, alertes", "Logique métier dupliquée dans chaque panel"),
                    ("Loki/Tempo", "Diagnostic technique existant", "Logs et traces en drill-down", "Calcul de la North Star"),
                ],
                [28, 48, 61, 36],
            ),
            h2("Flux recommandé"),
            simple_table(
                ["Étape", "Traitement", "Fréquence"],
                [
                    ("1", "Les événements backend et frontend enrichissent product_events et product_outcomes.", "Temps réel ou best effort"),
                    ("2", "Un job calcule les vues journalières et cohortes.", "Toutes les heures + recalcul quotidien"),
                    ("3", "Le lifetime metrics updater exporte les gauges produit bornées vers Prometheus.", "Cycle existant"),
                    ("4", "Grafana interroge Prometheus pour le temps réel et PostgreSQL pour exactitude/cohortes.", "À l'affichage"),
                    ("5", "Les règles de réconciliation comparent DB, Prometheus et sources métier.", "Quotidien"),
                ],
                [14, 130, 29],
            ),
            h2("Datasource PostgreSQL Grafana"),
            p(
                "Grafana prend nativement en charge le provisioning d'une datasource PostgreSQL par YAML. La datasource produit doit pointer vers des vues dédiées et utiliser un compte en lecture seule. Les secrets restent injectés par l'environnement et ne figurent pas dans le dépôt."
            ),
            code_block(
                """- name: Product PostgreSQL
  type: postgres
  uid: postgres-product-readonly
  access: proxy
  url: postgres:5432
  user: grafana_product_reader
  secureJsonData:
    password: ${GRAFANA_PRODUCT_DB_PASSWORD}
  jsonData:
    database: lia
    sslmode: disable
    postgresVersion: 1600
    timescaledb: false
    maxOpenConns: 5
    maxIdleConns: 2
    connMaxLifetime: 300
  editable: false"""
            ),
            p(
                "Référence de provisioning : documentation officielle Grafana PostgreSQL, https://grafana.com/docs/grafana/latest/datasources/postgres/configure/",
                "FooterNote",
            ),
            PageBreak(),
        ]
    )

    story.extend(
        [
            h1("4. Modèle normatif de la valeur"),
            h2("Utilisateur engagé éligible"),
            p(
                "Utilisateur ayant envoyé une demande, repris ou approuvé un workflow, déclenché/utilisé une routine, exploité un résultat proactif ou travaillé dans un projet/espace. Une simple ouverture, un login ou une notification reçue ne suffit pas."
            ),
            h2("Types de résultat"),
            simple_table(
                ["Code", "Définition", "Exemple"],
                [
                    ("answer", "Réponse informationnelle ou explicative", "Synthèse ou recommandation"),
                    ("action", "Action externe réellement exécutée", "Événement créé, email envoyé"),
                    ("preparation", "Brouillon, plan ou préparation", "Email prêt à valider"),
                    ("artifact", "Document, image, fichier ou export", "PDF ou image générée"),
                    ("automation_run", "Sortie d'une routine", "Brief automatique exploité"),
                    ("proactive_item", "Suggestion ou information proactive", "Alerte pertinente"),
                    ("project_progress", "Avancement significatif d'un projet/espace", "Corpus mis à jour"),
                ],
                [30, 88, 55],
            ),
            h2("Niveaux de preuve"),
            simple_table(
                ["Niveau", "Preuve", "North Star"],
                [
                    ("E1", "Confirmation explicite après résultat : pouce positif, validation textuelle, CSAT positive.", "Inclus"),
                    ("E2", "Comportement fort : action approuvée et non révertie, artefact utilisé, routine actionnée.", "Inclus"),
                    ("E3", "Succès technique : outil success, réponse affichée, routine terminée sans usage.", "Exclu"),
                ],
                [18, 119, 36],
            ),
            h2("Règles de comptage"),
            bullet("Un result_id ne compte qu'une fois, même avec plusieurs signaux positifs."),
            bullet("Un workflow batch compte comme un résultat métier principal; les items restent diagnostiques."),
            bullet("Un résultat corrigé sort du premier passage et alimente correction/faux succès."),
            bullet("L'absence de correction ne vaut jamais confirmation."),
            bullet("Une action E2 exige succès technique et absence de correction/réversion pendant au moins 24 h."),
            bullet("La démo n'est pas un résultat utile réel."),
            h2("Champs product_outcomes"),
            simple_table(
                ["Champ", "Rôle"],
                [
                    ("result_id", "Identifiant unique du résultat"),
                    ("workflow_id / attempt_id", "Lignage de l'exécution"),
                    ("user_id", "Utilisateur, uniquement en base"),
                    ("result_type / domain", "Nature et domaine bornés"),
                    ("execution_mode / channel", "Pipeline, ReAct, direct; web, PWA, voice, scheduler"),
                    ("state / evidence_level", "État canonique et niveau E1/E2/E3"),
                    ("produced_at / validated_at", "Dates de production et validation"),
                    ("first_pass / corrected / reverted", "Qualité et regret"),
                    ("turn_count / attempt_count", "Effort utilisateur"),
                    ("latency_ms / cost_eur / run_id", "Performance et coût réconciliables"),
                    ("device_class / locale / app_version", "Segments bornés"),
                ],
                [48, 125],
            ),
            PageBreak(),
        ]
    )

    story.extend(
        [
            h1("5. Blueprint du dashboard Grafana 26"),
            h2("Identité et configuration"),
            simple_table(
                ["Propriété", "Valeur"],
                [
                    ("Fichier", "infrastructure/observability/grafana/dashboards/26-product-value.json"),
                    ("Titre", "26 - Produit : valeur, activation et rétention"),
                    ("UID", "lia-product-value"),
                    ("Tags", "lia, product, value, growth, outcomes"),
                    ("Schema", "Même schemaVersion que les dashboards courants"),
                    ("Période par défaut", "30 derniers jours"),
                    ("Refresh", "5 minutes"),
                    ("Timezone", "Browser pour affichage; UTC dans les requêtes"),
                    ("Datasources", "Prometheus + postgres-product-readonly"),
                ],
                [50, 123],
            ),
            h2("Variables"),
            simple_table(
                ["Variable", "Valeurs", "Source"],
                [
                    ("domain", "all + domaines bornés", "PostgreSQL / label Prometheus"),
                    ("execution_mode", "all, pipeline, react, direct", "Mixte"),
                    ("channel", "all, web, pwa, voice, scheduler, channel", "Mixte"),
                    ("device_class", "all, mobile, tablet, desktop", "PostgreSQL"),
                    ("result_type", "all + 7 types", "PostgreSQL"),
                    ("evidence", "all, E1, E2, E3", "PostgreSQL"),
                    ("locale", "all, fr, en, de, es, it, zh", "PostgreSQL"),
                ],
                [38, 88, 47],
            ),
            h2("Organisation des lignes"),
            simple_table(
                ["# row", "Nom", "Panels", "État", "Contenu"],
                dashboard_rows,
                [14, 42, 17, 22, 78],
            ),
            PageBreak(),
            h2("Catalogue des panels"),
            simple_table(
                ["ID", "Panel", "Type", "Source", "Métriques", "Notes"],
                panel_rows,
                [11, 45, 24, 28, 30, 35],
                padding_mm=1.0,
            ),
            PageBreak(),
        ]
    )

    story.extend(
        [
            h1("6. Métriques existantes à réutiliser"),
            p(
                "Le dashboard doit consommer les métriques actuelles plutôt que créer des variantes synonymes. Les métriques techniques restent dans leurs dashboards d'origine; le dashboard 26 ne reprend que celles nécessaires à la décision produit."
            ),
            simple_table(
                ["Domaine", "Source existante", "Décision", "Destination"],
                existing_metric_rows,
                [27, 58, 63, 25],
                padding_mm=0.95,
            ),
            h2("Nouvelles métriques Prometheus minimales"),
            p(
                "Ces séries sont bornées par construction. Aucun label utilisateur, workflow, résultat, UUID, texte libre ou version complète ne doit être exposé."
            ),
            simple_table(
                ["Nom", "Type", "Labels", "Usage"],
                new_prometheus_rows,
                [52, 28, 57, 36],
            ),
            h2("Vues PostgreSQL recommandées"),
            simple_table(
                ["Vue", "Grain", "Usage Grafana"],
                [
                    ("product_outcomes", "1 ligne par result_id", "Vérité canonique résultat et preuve"),
                    ("product_funnel_daily", "jour x étape x segment", "Funnel et conversions"),
                    ("product_activation_cohorts", "cohorte x âge x segment", "Activation 24 h/7 j"),
                    ("product_retention_cohorts", "cohorte x semaine x segment", "Heatmaps D1/D7/D30 et utile"),
                    ("product_value_daily", "jour x domaine/type/mode/device", "North Star et qualité"),
                    ("product_automation_daily", "jour x routine type/status", "Routines et proactivité"),
                    ("product_mobile_parity_daily", "jour x device_class", "Écarts mobile/desktop"),
                    ("product_cost_daily", "jour x outcome/domain/mode", "Coût utile et gaspillage"),
                    ("product_data_quality_daily", "jour x check", "Qualité et réconciliation"),
                ],
                [55, 61, 57],
            ),
            PageBreak(),
        ]
    )

    story.extend([h1("7. Catalogue complet des indicateurs")])
    story.extend(metric_catalog_story())
    story.append(PageBreak())

    story.extend(
        [
            h1("8. Alertes et seuils"),
            p(
                "Les seuils produit doivent être calibrés après quatre semaines de baseline. Les valeurs ci-dessous sont des seuils de démarrage et doivent être ajustées à la variance réelle."
            ),
            simple_table(
                ["Sévérité", "Condition", "Action attendue"],
                [
                    ("Critique", "Agrégats produit sans refresh depuis 2 h", "Vérifier job, DB et exporter Prometheus"),
                    ("Critique", "Résultats orphelins > 5 %", "Bloquer la confiance du dashboard et corriger le lignage"),
                    ("Critique", "Succès E2E -25 % sur 24 h", "Drill-down domaine/mode/connecteur"),
                    ("Élevée", "North Star -20 % vs tendance comparable", "Analyser funnel, qualité et incidents"),
                    ("Élevée", "Coût par résultat utile +30 % sur 3 j", "Comparer mode, modèle et corrections"),
                    ("Élevée", "Échec routines +10 points", "Analyser scheduler et connecteurs"),
                    ("Moyenne", "Feedback négatif +5 points", "Analyser domaines et versions"),
                    ("Moyenne", "Abandon HITL +10 points", "Analyser niveau, device et latence"),
                    ("Moyenne", "Écart mobile/desktop > 15 points", "Ouvrir le dashboard UX"),
                    ("Moyenne", "Zéro résultat recherche +10 points", "Analyser surface et reformulations"),
                    ("Qualité", "Couverture confirmation < 20 %", "Afficher incertitude et améliorer la collecte"),
                    ("Qualité", "Divergence source/analytics > 1 %", "Suspendre les décisions sur métrique concernée"),
                ],
                [26, 87, 60],
            ),
            h2("Hygiène des alertes"),
            bullet("Owner, runbook et dashboard obligatoires."),
            bullet("Alertes relatives à baseline préférées aux seuils arbitraires."),
            bullet("Fenêtre anti-bruit et condition de clôture explicites."),
            bullet("Aucune alerte sur une métrique dont la qualité est rouge."),
            PageBreak(),
        ]
    )

    story.extend(
        [
            h1("9. Exigences et critères d'acceptation"),
            h2("Exigences priorisées"),
            simple_table(["Priorité", "Exigence", "Description"], requirements_rows, [20, 52, 101]),
            Spacer(1, 4 * mm),
            h2("Critères d'acceptation"),
            simple_table(["Domaine", "Critère"], acceptance_rows, [38, 135]),
            PageBreak(),
        ]
    )

    story.extend(
        [
            h1("10. Plan de mise en œuvre"),
            simple_table(
                ["Phase", "Objectif", "Livrables", "Dépendances"],
                [
                    ("0 - Inventaire", "Figer le contrat", "Dictionnaire, mappings existants, IDs, ADR", "Aucune"),
                    ("1 - Dashboard immédiat", "Valoriser l'existant", "Dashboard 26 v0 avec Prometheus uniquement et liens drill-down", "Dashboards actuels"),
                    ("2 - Outcome durable", "Calculer la North Star", "product_outcomes, E1/E2/E3, gauges DB-backed, panels 1-15", "Migration + instrumentation backend"),
                    ("3 - Funnel et cohortes", "Mesurer activation/rétention", "product_events, vues cohortes, datasource PostgreSQL, panels 16-28", "Événements onboarding/client"),
                    ("4 - Automation/UX", "Couvrir routines, proactivité, search et mobile", "Panels 29-40, QA UX, Web Vitals", "Instrumentation frontend/scheduler"),
                    ("5 - Baseline", "Fixer les objectifs", "4 semaines de données, seuils commit/stretch, alertes", "Qualité verte"),
                ],
                [27, 42, 75, 29],
            ),
            h2("Stratégie de livraison rapide"),
            callout(
                "<b>Quick win recommandé :</b> livrer d'abord le dashboard 26 v0 en lecture seule avec les métriques existantes. Sa structure définitive est déjà posée; les panels North Star et cohortes affichent N/A avec une description claire jusqu'à l'arrivée de product_outcomes. Cela produit une première valeur sans attendre tout le chantier analytique."
            ),
            h2("Tests requis"),
            bullet("Validation syntaxique et provisioning du JSON Grafana."),
            bullet("Tests de chaque PromQL sur série présente et absente."),
            bullet("EXPLAIN ANALYZE des requêtes PostgreSQL sur les périodes 7, 30 et 90 jours."),
            bullet("Tests de déduplication result_id et événements rejoués."),
            bullet("Tests E1/E2/E3, correction, réversion et feedback modifié."),
            bullet("Tests de timezone et cohortes aux changements de jour/semaine."),
            bullet("Tests de cardinalité des nouveaux labels."),
            bullet("Snapshots desktop, tablette et mobile du dashboard."),
            PageBreak(),
        ]
    )

    story.extend(
        [
            h1("11. Gouvernance et décisions"),
            simple_table(
                ["Sujet", "Décision proposée", "Owner"],
                [
                    ("North Star", "Inclure E1 et E2, ventilation obligatoire", "Produit"),
                    ("Copie simple", "Signal faible, insuffisant seul pour E2", "Produit/UX"),
                    ("Téléchargement", "E2 uniquement pour un artefact explicitement produit", "Produit"),
                    ("Réversion", "Fenêtre minimale 24 h", "Produit"),
                    ("Validation comportementale", "Fenêtre 7 jours", "Produit"),
                    ("Stockage", "PostgreSQL existant, pas de plateforme tierce", "Engineering"),
                    ("Restitution", "Grafana dashboard 26", "Produit/Engineering"),
                    ("Cohortes", "Datasource PostgreSQL read-only", "Engineering/Ops"),
                    ("Prometheus", "Labels bornés, aucune identité", "Engineering"),
                    ("Objectifs", "Après 4 semaines de baseline fiable", "Produit"),
                    ("Changement de définition", "Version et date d'effet obligatoires", "Produit/Data"),
                ],
                [46, 93, 34],
            ),
            h2("Cadence"),
            bullet("Hebdomadaire 30 min : scorecard L1, anomalies, décisions."),
            bullet("Mensuelle 60 min : cohortes, segments, coûts, fonctionnalités livrées."),
            bullet("Trimestrielle 90 min : objectifs, métriques obsolètes, stratégie produit."),
            h2("Références dépôt"),
            bullet("infrastructure/observability/grafana/dashboards/*.json - 25 dashboards existants."),
            bullet("infrastructure/observability/prometheus/recording_rules.yml - règles business existantes."),
            bullet("apps/api/src/infrastructure/observability/lifetime_metrics.py - pattern DB vers gauges Prometheus."),
            bullet("apps/api/src/infrastructure/observability/metrics_business.py - engagement, coût et abandon."),
            bullet("apps/api/src/infrastructure/observability/metrics_agents.py - orchestration, HITL et performance."),
            bullet("apps/api/src/infrastructure/observability/metrics_registry.py - drafts et feedback."),
            bullet("apps/api/src/domains/chat/models.py - coûts durables par run_id."),
            bullet("apps/api/src/domains/scheduled_actions/models.py - exécutions et échecs routines."),
            h2("Conclusion"),
            callout(
                "La bonne cible n'est pas un 26e dashboard technique. C'est un cockpit produit qui relie valeur, activation, qualité, rétention et coût, tout en donnant accès aux dashboards techniques existants pour l'explication. L'architecture proposée reste native à LIA : Grafana, Prometheus et PostgreSQL, sans plateforme analytics tierce.",
                colors.HexColor("#E9F8F2"),
            ),
        ]
    )

    return story


def build_pdf() -> None:
    """Build the final PDF."""
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    document = BaseDocTemplate(
        str(OUTPUT_PATH),
        pagesize=A4,
        rightMargin=17 * mm,
        leftMargin=17 * mm,
        topMargin=19 * mm,
        bottomMargin=16 * mm,
        title="LIA - Spécification Dashboard Grafana Produit",
        author="OpenAI Codex",
        subject="North Star, funnel, métriques produit et dashboard Grafana dédié",
        creator="ReportLab",
    )
    frame = Frame(
        document.leftMargin,
        document.bottomMargin,
        document.width,
        document.height,
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
        id="normal",
    )
    document.addPageTemplates(
        [
            PageTemplate(
                id="main",
                frames=[frame],
                onPage=on_page,
            )
        ]
    )
    document.build(build_story())


if __name__ == "__main__":
    build_pdf()
    print(OUTPUT_PATH.resolve())
