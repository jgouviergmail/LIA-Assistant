"""Local, fictional document fixtures for native gallery filming; no provider generation."""
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4

output = Path(__file__).resolve().parents[1] / "public" / "capture-v2" / "demo-files"
output.mkdir(parents=True, exist_ok=True)
documents = [
    ("synthese-atlas-demo.pdf", "Projet Atlas", "Synthèse de lancement", [
        "Périmètre du lancement validé.",
        "Date fournisseur : confirmation attendue entre le 19 et le 22 octobre.",
        "Prochaine étape : préparer un message pour validation par Alex.",
    ]),
    ("compte-rendu-demo.pdf", "Réunion Atlas", "Décisions et prochaines étapes", [
        "Conserver le périmètre et la checklist du lancement.",
        "Morgan prépare la checklist actualisée.",
        "Alex confirme la date avant de communiquer le planning.",
    ]),
]
for filename, title, subtitle, lines in documents:
    document = canvas.Canvas(str(output / filename), pagesize=A4)
    document.setTitle(f"{title} — Démonstration")
    document.setAuthor("LIA — fixture locale de démonstration")
    document.setFillColor(HexColor("#006497"))
    document.rect(0, 730, A4[0], 112, fill=1, stroke=0)
    document.setFillColor(HexColor("#ffffff"))
    document.setFont("Helvetica-Bold", 28)
    document.drawString(48, 782, title)
    document.setFont("Helvetica", 14)
    document.drawString(48, 753, subtitle)
    document.setFillColor(HexColor("#233744"))
    document.setFont("Helvetica-Bold", 14)
    document.drawString(48, 677, "À retenir")
    document.setFont("Helvetica", 11)
    for index, line in enumerate(lines):
        document.drawString(48, 637 - index * 36, line)
    document.setStrokeColor(HexColor("#cddce4"))
    document.line(48, 100, 547, 100)
    document.setFont("Helvetica", 9)
    document.drawString(48, 76, "Document local fictif pour présenter la galerie native de LIA.")
    document.drawString(48, 61, "Aucune génération par un fournisseur et aucune donnée privée.")
    document.save()
