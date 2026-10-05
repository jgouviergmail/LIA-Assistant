"""Commercial sources are excluded before bounds; useful editorial records survive."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from src.domains.briefing import fetchers
from src.domains.connectors import active_client
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.models import ConnectorType
from src.domains.radio import repository
from src.domains.radio.editorial import NewsCandidate, shortlist
from src.domains.radio.formats import RadioFormat
from src.domains.radio.interests import interest_story
from src.domains.radio.models import RadioNewsItem, TextState
from src.domains.radio.newsroom.editorial_rows import EDITORIAL_READ_PAGES_MAX, editorial_rows
from src.domains.radio.newsroom.fulltext import extract_article
from src.domains.radio.newsroom.parse import parse_feed
from src.domains.shared.commercial_content import (
    commercial_mail,
    editorial_excerpt,
    is_commercial_content,
)
from src.domains.users.models import User

pytestmark = pytest.mark.unit
NOW = datetime(2026, 10, 4, 10, tzinfo=UTC)


@pytest.mark.parametrize(
    "title",
    [
        "[Publicité] Découvrez la nouvelle collection",
        "Partenariat commercial : une marque présente son service",
        "Bon plan : un smartphone à prix réduit",
        "Soldes : nos nouvelles chaussures",
        "Shop now and save with our discount code",
        "Sponsored content: a new energy product",
        "Contenido patrocinado: el nuevo teléfono",
        "Oferta exclusiva: compra ahora con descuento",
        "Contenuto sponsorizzato: la nuova auto",
        "Approfitta dello sconto: acquista oggi",
        "Anzeige",
        "Jetzt kaufen mit unserem Rabattcode",
        "【广告】新款手机现已上市",
        "限时优惠：立即购买，使用优惠码",
        "Votre prochaine commande : économisez 30% avec notre code promo",
        "Offre exclusive : votre billet à moitié prix",
        "Votre prochaine réservation : profitez de notre offre exclusive",
        "40% de remise sur vos chaussures",
        "Up to 50% off our range",
        "Hasta 30% de descuento",
        "Fino a 40% di sconto",
        "Bis zu 50% Rabatt",
        "全场五折，新款手机",
        "Summer sale: our new collection",
        "Advertisement: Discover our latest range",
        "Sponsored by Brand X",
        "Publicité : Découvrez notre nouvelle gamme",
        "Contenu partenaire : découvrez notre gamme",
        "Publicidad: descubre nuestra nueva gama",
        "Patrocinado por una marca",
        "Pubblicità: scopri la nostra nuova gamma",
        "Sponsorizzato da una marca",
        "Werbung: entdecken Sie unsere Produkte",
        "Gesponsert von einer Marke",
    ],
)
def test_explicit_commercial_content_in_all_station_languages(title: str) -> None:
    assert is_commercial_content(title)
    assert commercial_mail({"subject": title})


@pytest.mark.parametrize(
    "title",
    [
        "L'inflation ralentit : les prix baissent de 3%",
        "Partenariat scientifique : deux universités étudient le climat",
        "Promotion professionnelle : Léa devient directrice",
        "Publicité : les députés examinent les règles du secteur",
        "Sponsored research receives a public grant",
        "Researchers announce a scientific partnership",
        "Lower food prices ease household inflation",
        "La bajada de precios reduce la inflación",
        "Una promoción profesional en nuestro equipo",
        "Una partnership scientifica studia il clima",
        "Prezzi in calo per le famiglie",
        "Wissenschaftliche Partnerschaft untersucht das Klima",
        "Sinkende Preise entlasten die Haushalte",
        "食品价格下降，通胀放缓",
        "科研合作研究气候变化",
        "Bon plan pour notre promenade dimanche",
        "Je t'envoie la facture et le suivi de livraison",
        "40% de réduction des émissions de carbone",
        "20% de réduction des taux d'intérêt",
    ],
)
def test_editorial_economy_career_science_and_personal_messages_survive(title: str) -> None:
    assert not is_commercial_content(title)
    assert not commercial_mail({"subject": title})


@pytest.mark.parametrize(
    "subject",
    [
        "Votre facture est disponible",
        "Your order confirmation",
        "Suivi de livraison",
        "Confirmación de su cita",
        "La tua fattura",
        "Ihre Rechnung",
        "预约确认",
        "Actualités scientifiques de la semaine",
        "Daily news briefing",
        "Votre facture : remise de 20% appliquée",
        "Actualités scientifiques : remise des prix de recherche",
    ],
)
def test_transaction_and_editorial_mail_survive_promotion_category_and_footer(subject: str) -> None:
    mail = {
        "subject": subject,
        "labelIds": ["UNREAD", "CATEGORY_PROMOTIONS"],
        "body": "Useful details of the transaction.\nShop now and save with our discount code.\nUnsubscribe",
    }
    assert not commercial_mail(mail)
    assert editorial_excerpt(mail["body"]) == "Useful details of the transaction."


def test_gmail_category_is_preserved_as_a_signal_not_only_subject_words() -> None:
    assert commercial_mail({"subject": "Something for you", "labelIds": ["CATEGORY_PROMOTIONS"]})
    assert not commercial_mail({"subject": "Our family dinner", "labelIds": ["INBOX", "UNREAD"]})


@pytest.mark.parametrize(
    ("subject", "body"),
    [
        (
            "Actualités scientifiques de la semaine",
            "Sponsored content: Brand X presents a product.",
        ),
        ("Daily news briefing", "Paid partnership: discover our latest range."),
    ],
)
def test_primary_sponsorship_disclosure_precedes_a_newsletter_subject(
    subject: str, body: str
) -> None:
    assert commercial_mail({"subject": subject, "snippet": "Overview", "body": body})
    assert not commercial_mail(
        {
            "subject": subject,
            "snippet": "Overview",
            "body": "Parliament adopted the budget.\n" + body,
        }
    )


@pytest.mark.parametrize(
    "subject",
    [
        "Votre prochaine commande : -30% avec le code promo BIENVENUE",
        "Votre réservation : réduction de 20% sur le prochain séjour",
    ],
)
def test_coupon_and_promotion_category_precede_future_transaction_word(subject: str) -> None:
    assert commercial_mail({"subject": subject, "labelIds": ["CATEGORY_PROMOTIONS"]})
    assert commercial_mail({"subject": subject, "labelIds": ["UNREAD"]})
    assert not commercial_mail(
        {"subject": "Votre commande a été expédiée", "labelIds": ["CATEGORY_PROMOTIONS"]}
    )


def test_newsletter_advertising_paragraph_and_unsubscribe_do_not_erase_news() -> None:
    text = "<p>Parliament adopted the budget.</p><p>Sponsored content: discover a product.</p>"
    text += "<p>Shop now and use our discount code.</p><p>Unsubscribe from this newsletter.</p>"
    text += "<p>The next vote is on Tuesday.</p>"
    assert not is_commercial_content("The day's news", body=text)
    assert editorial_excerpt(text) == "Parliament adopted the budget.\nThe next vote is on Tuesday."


def _entry(title: str, number: int, *, summary: str = "", extra: str = "") -> str:
    return f"<item><title>{title}</title><link>https://custom.example/{number}</link><description><![CDATA[{summary}]]></description>{extra}</item>"


def test_custom_feed_promotions_do_not_fill_the_newsroom_or_truncate_disclosures() -> None:
    entries = [_entry("Bon plan : chaussures", number) for number in range(80)]
    entries += [
        _entry("Real news", 90, summary="Parliament voted today.\nSponsored content: buy a car.")
    ]
    entries += [
        _entry(
            "A hidden ad", 91, summary="x" * 1700, extra="<category>Sponsored content</category>"
        )
    ]
    body = ("<rss><channel>" + "".join(entries) + "</channel></rss>").encode()
    [kept] = parse_feed(body, feed_url="https://custom.example/feed", fetched_at=NOW)
    assert kept.title == "Real news"
    assert kept.summary == "Parliament voted today."


def test_atom_full_content_ad_disclosure_is_inspected_even_with_an_editorial_summary() -> None:
    atom = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Product features</title><link href="https://custom.example/1"/><summary>Overview</summary><content type="html">&lt;p&gt;Sponsored content: a product.&lt;/p&gt;</content></entry></feed>'
    assert parse_feed(atom, feed_url="https://custom.example/feed", fetched_at=NOW) == []


def test_interest_result_is_filtered_before_provider_stories_bound() -> None:
    args = {
        "url": "https://site.example/1",
        "summary": "",
        "outlet": "Site",
        "published_at": None,
        "found_at": NOW,
    }
    assert interest_story(title="Bon plan : une montre", **args) is None
    assert interest_story(title="Une découverte scientifique", **args) is not None


def test_article_extraction_keeps_editorial_body_and_removes_commercial_inserts() -> None:
    paragraphs = (
        "<p>The researchers measured the temperature of the ocean and published their findings. </p>"
        * 12
    )
    page = "<html><body><article><h1>Scientific discovery</h1>" + paragraphs
    page += "<p>Sponsored content: discover our newest product and save today.</p>"
    page += "<p>Shop now and use our discount code for your order.</p></article></body></html>"
    text = extract_article(page.encode())
    assert text and "researchers" in text
    assert "Sponsored content" not in text and "discount code" not in text


def test_primary_sponsored_article_keeps_exclusion_evidence_for_the_desk() -> None:
    body = "<p>Sponsored content: discover our newest product and save today.</p>"
    body += (
        "<p>Brand product specifications and services are described in this commercial article. </p>"
        * 12
    )
    text = extract_article(("<html><body><article>" + body + "</article></body></html>").encode())
    assert text and is_commercial_content("Product review", body=text)


def test_legacy_promotions_do_not_fill_shortlist_and_fulltext_disclosure_is_respected() -> None:
    def candidate(key: str, title: str, body: str | None = None) -> NewsCandidate:
        return NewsCandidate(
            key, "Outlet", f"https://site.example/{key}", title, "", NOW, key, body
        )

    pool = [candidate(str(i), "Bon plan : une montre") for i in range(80)]
    pool += [candidate("paid", "Energy review", "Sponsored content: a brand's product.")]
    pool += [candidate("news", "Une découverte scientifique")]
    selected = shortlist(pool, RadioFormat.HEADLINES, aired_keys=frozenset(), now=NOW)
    assert [item.key for item in selected] == ["news"]


class Database:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows
        self.reads = 0
        self.scanned = 0
        self.closed = False

    async def stream(self, query):
        self.reads += 1
        limit = query._limit_clause.value
        snapshot = list(self.rows[:limit])
        owner = self

        class Rows:
            async def partitions(self, page_size):
                for offset in range(0, len(snapshot), page_size):
                    batch = snapshot[offset : offset + page_size]
                    owner.scanned += len(batch)
                    yield batch

            async def close(self):
                owner.closed = True

        return Rows()


async def test_legacy_db_promotions_are_replaced_before_the_source_limit(monkeypatch) -> None:
    def row(number: int, title: str):
        item = RadioNewsItem(
            id=uuid4(),
            title=title,
            summary="",
            url=f"https://custom.example/{number}",
            fingerprint=str(number),
            published_at=NOW,
            text_state=TextState.NONE.value,
        )
        return (item, "Custom source")

    db = Database([row(i, "Bon plan : une montre") for i in range(650)] + [row(651, "Real news")])

    @asynccontextmanager
    async def database():
        yield db

    monkeypatch.setattr(repository, "get_db_context", database)
    result = await repository.news_candidates(
        uuid4(), disabled_feeds=(), since=NOW, limit=1, interests_limit=0
    )
    assert [item.title for item in result] == ["Real news"]
    assert db.reads == 1 and db.scanned > 650 and db.closed


async def test_db_repopulation_stops_after_a_bounded_number_of_pages() -> None:
    db = Database([SimpleNamespace(id=i) for i in range(100_000)])
    result = await editorial_rows(
        db, select(RadioNewsItem), limit=1, eligible=lambda row: False, identity=lambda row: row.id
    )
    assert result == []
    assert db.reads == 1 and db.scanned == 50 * EDITORIAL_READ_PAGES_MAX and db.closed


async def test_stream_cursor_closes_and_cancellation_propagates() -> None:
    db = Database([SimpleNamespace(id=1)])

    def cancelled(row):
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await editorial_rows(
            db, select(RadioNewsItem), limit=1, eligible=cancelled, identity=lambda row: row.id
        )
    assert db.closed


@pytest.mark.parametrize(
    "provider",
    [ConnectorType.GOOGLE_GMAIL, ConnectorType.MICROSOFT_OUTLOOK, ConnectorType.APPLE_EMAIL],
)
async def test_mail_reader_filters_raw_provider_signals_before_display_cap(
    monkeypatch, provider
) -> None:
    mails = [
        {"id": str(i), "subject": "Something for you", "labelIds": ["CATEGORY_PROMOTIONS"]}
        for i in range(12)
    ]
    mails += [
        {
            "id": "real",
            "subject": "Family dinner",
            "from": "Family <family@example.test>",
            "snippet": "Sunday?",
        }
    ]
    calls = []

    class Client:
        async def search_emails(self, **kwargs):
            calls.append(kwargs)
            return {"messages": mails[: kwargs["max_results"]]}

    @asynccontextmanager
    async def opened(*args):
        yield ActiveClient(Client(), provider, None)

    monkeypatch.setattr(active_client, "open_active_client", opened)
    monkeypatch.setattr(fetchers.settings, "briefing_max_mails_items", 1)
    user = User(id=uuid4(), language="en", timezone="UTC")
    result = await fetchers.fetch_mails(
        user=user, user_tz=ZoneInfo("UTC"), language="en", exclude_commercial_mails=True
    )
    assert [item.subject for item in result.items] == ["Family dinner"]
    assert result.total_unread_today == len(mails)
    assert calls[0]["max_results"] > 12
    ordinary = await fetchers.fetch_mails(user=user, user_tz=ZoneInfo("UTC"), language="en")
    assert [item.subject for item in ordinary.items] == ["Something for you"]
    assert calls[1]["max_results"] == 1
