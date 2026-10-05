"""Conservative commercial-content signals for editorial source readers.

An advertising label or a direct sales pitch is evidence; an economic price,
scientific partnership or professional promotion is not. The whole body is
inspected paragraph by paragraph to remove advertising inserts without dropping
an otherwise useful newsletter, invoice or appointment. No model runs here.
"""

from __future__ import annotations

import html
import re
import unicodedata
from collections.abc import Iterable, Mapping
from typing import Final

_TAGS: Final = re.compile(r"<[A-Za-z/!][^<>]*>")
_BLOCKS: Final = re.compile(r"</(?:p|div|li|h[1-6]|blockquote)>|<br\s*/?>", re.I)
_SPACE: Final = re.compile(r"\s+")


def _fold(text: str) -> str:
    value = unicodedata.normalize("NFKD", html.unescape(_TAGS.sub(" ", text)).casefold())
    return _SPACE.sub(" ", "".join(c for c in value if not unicodedata.combining(c))).strip()


# Disclosures must be attached to the content, not mentioned in an article.
_DISCLOSURE: Final = re.compile(
    r"^\s*(?:[\[({]\s*(?:advertisement|publicite|publicidad|pubblicita|werbung|anzeige|sponsored)\s*[\])}]|"
    r"(?:advertisement|publicite|publicidad|pubblicita|werbung|anzeige)\s*$|"
    r"(?:advertorial|sponsored (?:content|post|article)|sponsored by|sponsorise par|"
    r"contenu partenaire|contenido de socios|patrocinado por|contenuto partner|sponsorizzato da|"
    r"partnerinhalt|gesponsert von|"
    r"paid (?:content|partnership)|commercial partnership|partner content|"
    r"publireportage|contenu sponsorise|article sponsorise|"
    r"partenariat commercial|en partenariat commercial avec|"
    r"publirreportaje|contenido patrocinado|colaboracion pagada|"
    r"contenuto sponsorizzato|partnership commerciale|"
    r"gesponsert|bezahlte partnerschaft)(?:\b|[\]:：)]))|"
    r"^\s*[【\[]?(?:广告|廣告|商业推广|商業推廣|赞助内容|贊助內容)[】\]:：\s]|"
    r"^\s*(?:由.+(?:商业赞助|商業贊助)|合作推广|合作推廣)"
)
_AD_LABEL: Final = re.compile(
    r"^(?:advertisement|publicite|publicidad|pubblicita|werbung|anzeige)\s*[:：—–-]"
)
_AD_INVITATION: Final = re.compile(
    r"\b(?:discover|decouvrez|decubre|descubre|scopri|entdecken|learn about|explore|"
    r"our (?:new|latest)|notre (?:nouvelle|nouveau)|nuestra nueva|nostra nuova)\b"
)
_COMMERCIAL_CATEGORIES: Final = frozenset(
    {
        "advertisement",
        "advertorial",
        "sponsored",
        "sponsored content",
        "paid partnership",
        "publicite",
        "publireportage",
        "contenu sponsorise",
        "partenariat commercial",
        "publicidad",
        "contenido patrocinado",
        "pubblicita",
        "contenuto sponsorizzato",
        "werbung",
        "anzeige",
        "gesponsert",
        "广告",
        "廣告",
        "商业推广",
        "商業推廣",
    }
)
_DEALS_HEADING: Final = re.compile(
    r"^(?:bon(?:s)? plan(?:s)?|soldes|vente flash|offre(?:s)? commerciale(?:s)?|"
    r"offre(?:s)? exclusive(?:s)?|black friday|cyber monday|coupon(?:s)?|"
    r"deal(?:s)?|special offer(?:s)?|(?:summer |winter |flash )?sale|rebajas|oferta(?:s)? exclusiva(?:s)?|"
    r"saldi|offert[ae] speciale|sonderangebot[esn]*|schnappchen)\s*[:：!\-]|"
    r"^(?:限时优惠|限時優惠|限时特惠|限時特惠|优惠券|優惠券|促销|促銷)[：:!！\s]"
)
_DISCOUNT_HEADING: Final = re.compile(
    r"^(?:(?:up to|jusqu['’]a|fino a|hasta|bis zu)\s*)?[-−]?\d+(?:[.,]\d+)?\s*%\s*"
    r"(?:off\b|de (?:remise|descuento)\b|(?:di )?sconto\b|rabatt\b)|"
    r"^[-−]\d+\s*%\s+(?:sur tout|on all|su tutto|en todo)\b|"
    r"^(?:全场|全場)(?:[一二三四五六七八九\d]折|特惠|半价|半價)"
)
_SALES_TERMS: Final = re.compile(
    r"\b(?:code promo|code de reduction|promo code|coupon code|discount code|"
    r"codigo (?:promocional|descuento)|codice sconto|gutscheincode|rabattcode)\b|"
    r"(?:优惠码|優惠碼|折扣码|折扣碼)|"
    r"\b(?:soldes|reduction|remise|discount|sale|offre|offer|descuento|rebajas|"
    r"sconto|saldi|rabatt|sonderangebot)\b|(?:优惠|優惠|折扣|促销|促銷)"
)
_BUY: Final = re.compile(
    r"\b(?:achetez|commandez|profitez|economisez|shop now|buy now|order now|"
    r"save now|grab (?:your|this)|use (?:the |your |our )?(?:code|coupon)|"
    r"utilisez (?:le |votre |notre )?code|compra (?:ya|ahora)|compralo|"
    r"aprovecha|usa (?:el )?codigo|acquista|approfitta|usa (?:il )?codice|"
    r"jetzt (?:kaufen|bestellen|sparen)|sichern sie|nutze[n]? (?:den )?code)\b|"
    r"(?:立即购买|立即購買|立即下单|立即下單|马上抢购|馬上搶購|使用优惠码|使用優惠碼)"
)
_COUPON_OFFER: Final = re.compile(
    r"\b(?:avec|with|mit|con) (?:le |notre |votre |the |our |your |dem |il |el )?"
    r"(?:code promo|promo code|discount code|coupon code|rabattcode|codice sconto|codigo promocional)\b"
)
_FUTURE_PURCHASE: Final = re.compile(
    r"\b(?:prochaine? (?:commande|reservation|achat|sejour)|next (?:order|booking|purchase|stay)|"
    r"prossimo (?:ordine|acquisto|soggiorno)|proxima (?:compra|reserva)|"
    r"nachste[n]? (?:bestellung|buchung|einkauf))\b|(?:下次(?:购买|購買|订单|訂單|预订|預訂))"
)
_FOOTER: Final = re.compile(
    r"^(?:pour vous desabonner|se desabonner|unsubscribe(?: from)?|manage your (?:email )?preferences|"
    r"darse de baja|cancelar suscripcion|annulla (?:la )?iscrizione|abmelden|取消订阅|取消訂閱)\b"
)
_USEFUL_MAIL_SUBJECT: Final = re.compile(
    r"\b(?:facture|invoice|receipt|recu|commande|order (?:confirmation|shipped|tracking)|"
    r"shipment|delivery|livraison|suivi (?:de votre|de la|de commande)|"
    r"rendez-vous|appointment|reservation|booking|billet|ticket|"
    r"factura|recibo|pedido|cita|fattura|ricevuta|ordine|appuntamento|"
    r"rechnung|quittung|bestellung|termin|livraison|"
    r"actualites|news(?:letter)? (?:briefing|digest)|daily briefing|"
    r"noticias|actualidad|notizie|nachrichten|partenariat scientifique|"
    r"scientific partnership|promotion professionnelle|professional promotion)\b|"
    r"(?:发票|發票|订单|訂單|预约|預約|收据|收據|新闻简报|新聞簡報)"
)


def _pitch(text: str) -> bool:
    return bool(_SALES_TERMS.search(text) and _BUY.search(text))


def is_commercial_content(
    title: str,
    *,
    summary: str = "",
    body: str = "",
    categories: Iterable[str] = (),
    email: bool = False,
) -> bool:
    """Whether this item's primary content has explicit commercial evidence.

    A body's later advertisement cannot classify the editorial item as an ad.
    Its inserts are removed separately by :func:`editorial_excerpt`. A mail's
    transaction or news subject survives even a provider promotion category.
    """
    headline = _fold(title)
    labels = {_fold(category) for category in categories}
    if _commercial_title(headline):
        return True
    if email and _future_promotional_purchase(headline, labels):
        return True
    if _has_disclosed_lead(summary, body):
        return True
    if email and _USEFUL_MAIL_SUBJECT.search(headline):
        return False
    if labels & _COMMERCIAL_CATEGORIES or (email and "category_promotions" in labels):
        return True
    # Look at the lead paragraph, never a footer hidden after the real story.
    return _commercial_lead(summary) or _commercial_lead(body)


def _future_promotional_purchase(headline: str, labels: set[str]) -> bool:
    return bool(
        _FUTURE_PURCHASE.search(headline)
        and _SALES_TERMS.search(headline)
        and ("category_promotions" in labels or re.search(r"\d+(?:[.,]\d+)?\s*%", headline))
    )


def _commercial_title(headline: str) -> bool:
    return bool(_commercial_heading(headline) or _pitch(headline) or _COUPON_OFFER.search(headline))


def _commercial_lead(text: str) -> bool:
    lead = next((line for line in _paragraphs(text) if line.strip()), "")
    folded = _fold(lead)
    return _commercial_heading(folded) or _pitch(folded)


def _has_disclosed_lead(*texts: str) -> bool:
    return any(
        _DISCLOSURE.search(_fold(next((line for line in _paragraphs(text) if line.strip()), "")))
        for text in texts
    )


def _commercial_heading(text: str) -> bool:
    return bool(
        _DISCLOSURE.search(text)
        or _DEALS_HEADING.search(text)
        or _DISCOUNT_HEADING.search(text)
        or (_AD_LABEL.search(text) and _AD_INVITATION.search(text))
    )


def _paragraphs(text: str) -> list[str]:
    unescaped = html.unescape(_TAGS.sub(" ", _BLOCKS.sub("\n", text)))
    return [re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in unescaped.splitlines()]


def editorial_excerpt(text: str) -> str:
    """Keep editorial paragraphs, dropping disclosed ads, sales pitches and footers.

    No substring is cut out of a sentence: an insert must be its own paragraph.
    The writer and checker retain the semantic policy for mixed paragraphs.
    """
    return "\n".join(
        line
        for line in _paragraphs(text)
        if line
        and not (
            _commercial_heading(_fold(line)) or _FOOTER.search(_fold(line)) or _pitch(_fold(line))
        )
    )


def commercial_mail(message: Mapping[str, object]) -> bool:
    """Use the shipped providers' normalized subject/body/snippet/labelIds shape."""
    labels = message.get("labelIds")
    categories = (
        [value for value in labels if isinstance(value, str)] if isinstance(labels, list) else []
    )
    return is_commercial_content(
        str(message.get("subject") or ""),
        summary=str(message.get("snippet") or ""),
        body=str(message.get("body") or ""),
        categories=categories,
        email=True,
    )


__all__ = ["commercial_mail", "editorial_excerpt", "is_commercial_content"]
