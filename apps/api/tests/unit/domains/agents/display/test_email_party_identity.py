"""An email recipient's address is visible once when it is also the identity."""

import pytest

from src.domains.agents.display.components.email_parties import render_email_parties

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "value",
    [
        {"email": "team@example.test"},
        {"name": "", "email": "team@example.test"},
        {"name": "team@example.test", "email": "team@example.test"},
        "team@example.test",
    ],
    ids=["missing-name", "empty-name", "identical-name", "bare-address"],
)
def test_address_only_identity_keeps_one_visible_address_and_its_mail_link(value: object) -> None:
    html = render_email_parties(value)
    assert html.count('href="mailto:team@example.test"') == 1
    assert html.count(">team@example.test<") == 1
    assert 'class="lia-part-item__email"' not in html


@pytest.mark.parametrize(
    "value",
    [
        {"name": "Garden Team", "email": "team@example.test"},
        '"Garden Team" <team@example.test>',
    ],
)
def test_distinct_recipient_name_and_address_both_remain_visible(value: object) -> None:
    html = render_email_parties(value)
    assert '<a href="mailto:team@example.test">Garden Team</a>' in html
    assert '<span class="lia-part-item__email">team@example.test</span>' in html
