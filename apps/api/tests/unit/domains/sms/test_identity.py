"""Identity is a projection, never a guessed phone-country or fuzzy merge."""

from src.domains.relations.identity import IdentityResolver


def test_contact_matches_take_priority_and_normalize_accents():
    from src.domains.sms.identity import ContactIdentity, IdentityBook

    book = IdentityBook(
        contacts=(ContactIdentity(name="Alice", numbers=("+33612345678",)),), complete=True
    )
    assert book.resolve("06 12 34 56 78").display_name == "Alice"
    assert book.resolve("ALÍCE").source == "contact"


def test_ambiguous_or_truncated_contacts_keep_literal_sender():
    from src.domains.sms.identity import ContactIdentity, IdentityBook

    contacts = (
        ContactIdentity(name="Alice", numbers=("12345",)),
        ContactIdentity(name="Bob", numbers=("12345",)),
    )
    assert IdentityBook(contacts=contacts, complete=True).resolve("12345").state == "ambiguous"
    assert (
        IdentityBook(contacts=contacts[:1], complete=False).resolve("12345").display_name == "12345"
    )


def test_manual_relation_alias_is_the_only_number_to_name_fallback():
    from src.domains.sms.identity import IdentityBook

    resolver = IdentityResolver.from_pairs([("0612345678", "alice")])
    book = IdentityBook(relations={"alice": "Alice"}, resolver=resolver)
    assert book.resolve("0612345678").source == "relation"
    assert book.resolve("0612345679").source == "raw"


def test_same_national_suffix_in_two_countries_stays_ambiguous():
    from src.domains.sms.identity import ContactIdentity, IdentityBook

    book = IdentityBook(
        contacts=(
            ContactIdentity(name="A", numbers=("+33612345678",)),
            ContactIdentity(name="B", numbers=("+44612345678",)),
        ),
        complete=True,
    )
    assert book.resolve("0612345678").state == "ambiguous"
    assert book.resolve("+33612345678").display_name == "A"


def test_alphanumeric_sender_is_never_coerced_to_its_digits():
    from src.domains.sms.identity import ContactIdentity, IdentityBook

    book = IdentityBook(
        contacts=(ContactIdentity(name="Person", numbers=("12345",)),), complete=True
    )
    assert book.resolve("Company12345").source == "raw"


def test_an_unnamed_duplicate_contact_cannot_turn_an_ambiguous_line_into_a_person():
    from src.domains.connectors.clients.contact_directory import ContactDirectory
    from src.domains.sms.identity import IdentityBook
    from src.domains.sms.identity_directory import project_directory

    directory = ContactDirectory(
        persons=[
            {"names": [], "phoneNumbers": [{"value": "+33612345678"}]},
            {"names": [{"displayName": "Alice"}], "phoneNumbers": [{"value": "+33612345678"}]},
        ],
        truncated=False,
        from_cache=True,
    )
    contacts, complete = project_directory(directory)
    resolved = IdentityBook(contacts=contacts, complete=complete).resolve("+33612345678")
    assert resolved.source == "raw" and resolved.state == "ambiguous"
