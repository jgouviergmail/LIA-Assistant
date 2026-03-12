"""
Non-regression tests for Issue #40: Array bounds validation.

Phase 2.4 - Issue #40: Validate that the Planner generates valid plans
and that the ReferenceValidator detects out-of-bounds references.

Tests covered:
1. Runtime validation with out-of-bounds indices (must fail)
2. Runtime validation with valid indices (must pass)
3. Complete Issue #40 scenario (multi-domain query)
4. agent_results context injection into Planner
"""

from __future__ import annotations

import pytest

from src.domains.agents.orchestration.reference_validator import ReferenceValidator
from src.domains.agents.tools.common import ToolErrorCode


class TestArrayBoundsValidation:
    """Tests de validation des limites d'array dans les références $steps."""

    @pytest.fixture
    def validator(self) -> ReferenceValidator:
        """Create ReferenceValidator instance."""
        return ReferenceValidator()

    @pytest.fixture
    def step_results_contacts(self) -> dict:
        """
        Simule les résultats d'un step de recherche de contacts.
        Scénario: search_contacts a trouvé 2 contacts (indices 0-1 valides).
        """
        return {
            "search_contacts_hua": {
                "data": {
                    "contacts": [
                        {
                            "resource_name": "people/c1234",
                            "names": [{"displayName": "John jean"}],
                            "emailAddresses": [{"value": "john.jean@example.com"}],
                        },
                        {
                            "resource_name": "people/c5678",
                            "names": [{"displayName": "Jane jean"}],
                            "emailAddresses": [{"value": "jane.jean@example.com"}],
                        },
                    ]
                }
            }
        }

    def test_runtime_validation_out_of_bounds_error(
        self, validator: ReferenceValidator, step_results_contacts: dict
    ):
        """
        Test Case 1: Validation runtime avec indices hors limites.

        Scénario:
        - search_contacts a trouvé 2 contacts (indices 0-1 valides)
        - get_contacts_details référence contacts[0] à contacts[4] (5 références)
        - Expected: 3 erreurs pour indices 2, 3, 4 (hors limites)

        Phase 2.4 - Issue #40: Test du cas racine de l'issue.
        """
        # Step parameters with out-of-bounds references
        parameters = {
            "resource_names": [
                "$steps.search_contacts_hua.contacts[0].resource_name",  # OK
                "$steps.search_contacts_hua.contacts[1].resource_name",  # OK
                "$steps.search_contacts_hua.contacts[2].resource_name",  # OUT OF BOUNDS
                "$steps.search_contacts_hua.contacts[3].resource_name",  # OUT OF BOUNDS
                "$steps.search_contacts_hua.contacts[4].resource_name",  # OUT OF BOUNDS
            ]
        }

        # Validation
        errors = validator.validate_runtime_array_bounds(
            step_id="get_contacts_details",
            step_index=1,
            parameters=parameters,
            step_results=step_results_contacts,
        )

        # Assertions
        assert len(errors) == 3, f"Expected 3 errors (indices 2, 3, 4), got {len(errors)}"

        # Verify detected indices
        detected_indices = []
        for err in errors:
            assert err.code == ToolErrorCode.INVALID_INPUT
            assert "Array index out of bounds" in err.message
            assert "contacts" in err.message
            assert "only 2 element(s) available" in err.message
            # Extract index from message (e.g., "contacts[2]")
            if "[2]" in err.message:
                detected_indices.append(2)
            elif "[3]" in err.message:
                detected_indices.append(3)
            elif "[4]" in err.message:
                detected_indices.append(4)

        assert set(detected_indices) == {2, 3, 4}, "Should detect indices 2, 3, 4 as out of bounds"

    def test_runtime_validation_within_bounds_success(
        self, validator: ReferenceValidator, step_results_contacts: dict
    ):
        """
        Test Case 2: Validation runtime avec indices valides.

        Scénario:
        - search_contacts a trouvé 2 contacts (indices 0-1 valides)
        - get_contacts_details référence SEULEMENT contacts[0] et contacts[1]
        - Expected: Aucune erreur

        Phase 2.4 - Issue #40: Test du comportement attendu (plan correct).
        """
        # Step parameters with valid references
        parameters = {
            "resource_names": [
                "$steps.search_contacts_hua.contacts[0].resource_name",  # OK
                "$steps.search_contacts_hua.contacts[1].resource_name",  # OK
            ]
        }

        # Validation
        errors = validator.validate_runtime_array_bounds(
            step_id="get_contacts_details",
            step_index=1,
            parameters=parameters,
            step_results=step_results_contacts,
        )

        # Assertions
        assert (
            len(errors) == 0
        ), f"Expected no errors, got {len(errors)}: {[e.message for e in errors]}"

    def test_runtime_validation_nested_arrays(self, validator: ReferenceValidator):
        """
        Test Case 3: Validation avec arrays imbriqués.

        Scénario:
        - contacts[0].emailAddresses[2] où emailAddresses a seulement 1 élément
        - Expected: 1 erreur pour emailAddresses[2]

        Phase 2.4 - Issue #40: Test des arrays imbriqués (générique).
        """
        step_results = {
            "search_contacts": {
                "data": {
                    "contacts": [
                        {
                            "resource_name": "people/c1234",
                            "emailAddresses": [
                                {"value": "john@example.com"}  # Seulement 1 email (indice 0)
                            ],
                        }
                    ]
                }
            }
        }

        parameters = {
            "email": "$steps.search_contacts.contacts[0].emailAddresses[2].value"  # OUT OF BOUNDS
        }

        errors = validator.validate_runtime_array_bounds(
            step_id="send_email",
            step_index=2,
            parameters=parameters,
            step_results=step_results,
        )

        assert len(errors) == 1
        assert "emailAddresses[2]" in errors[0].message or "emailAddresses" in errors[0].message
        assert "only 1 element(s) available" in errors[0].message

    def test_runtime_validation_empty_array(self, validator: ReferenceValidator):
        """
        Test Case 4: Validation avec array vide.

        Scénario:
        - contacts[0] où contacts = [] (array vide)
        - Expected: 1 erreur pour contacts[0]

        Phase 2.4 - Issue #40: Test du cas edge (array vide).
        """
        step_results = {"search_contacts": {"data": {"contacts": []}}}  # Array vide

        parameters = {"resource_name": "$steps.search_contacts.contacts[0].resource_name"}

        errors = validator.validate_runtime_array_bounds(
            step_id="get_contact_details",
            step_index=1,
            parameters=parameters,
            step_results=step_results,
        )

        assert len(errors) == 1
        assert "contacts[0]" in errors[0].message
        assert "0 element(s) available" in errors[0].message or "empty" in errors[0].message.lower()

    def test_runtime_validation_multiple_references_same_param(self, validator: ReferenceValidator):
        """
        Test Case 5: Validation avec plusieurs références dans un même paramètre.

        Scénario:
        - query contient "from:$steps.X.contacts[0] AND from:$steps.X.contacts[2]"
        - contacts a seulement 1 élément
        - Expected: 1 erreur pour contacts[2]

        Phase 2.4 - Issue #40: Test des embedded references.
        """
        step_results = {
            "search_contacts": {
                "data": {
                    "contacts": [
                        {"emailAddresses": [{"value": "john@example.com"}]}
                        # Seulement 1 contact (indice 0)
                    ]
                }
            }
        }

        parameters = {
            "query": (
                "from:$steps.search_contacts.contacts[0].emailAddresses[0].value "
                "OR from:$steps.search_contacts.contacts[2].emailAddresses[0].value"
            )
        }

        errors = validator.validate_runtime_array_bounds(
            step_id="search_emails",
            step_index=2,
            parameters=parameters,
            step_results=step_results,
        )

        assert len(errors) == 1
        assert "contacts[2]" in errors[0].message
        assert "only 1 element(s) available" in errors[0].message

    @pytest.mark.parametrize(
        "contacts_count,references_count,expected_errors_count",
        [
            (0, 1, 1),  # 0 contacts, 1 référence → 1 erreur
            (1, 1, 0),  # 1 contact, 1 référence → 0 erreur
            (1, 2, 1),  # 1 contact, 2 références → 1 erreur (index 1 hors limites)
            (2, 2, 0),  # 2 contacts, 2 références → 0 erreur
            (2, 5, 3),  # 2 contacts, 5 références → 3 erreurs (indices 2, 3, 4)
            (5, 5, 0),  # 5 contacts, 5 références → 0 erreur
            (3, 10, 7),  # 3 contacts, 10 références → 7 erreurs (indices 3-9)
        ],
    )
    def test_runtime_validation_parametric(
        self,
        validator: ReferenceValidator,
        contacts_count: int,
        references_count: int,
        expected_errors_count: int,
    ):
        """
        Test Case 6: Tests paramétriques pour différentes combinaisons.

        Phase 2.4 - Issue #40: Test exhaustif des combinaisons count vs references.
        """
        # Build step_results with contacts_count contacts
        contacts = [
            {"resource_name": f"people/c{i}", "names": [{"displayName": f"Contact {i}"}]}
            for i in range(contacts_count)
        ]
        step_results = {"search_contacts": {"data": {"contacts": contacts}}}

        # Build parameters with references_count references
        parameters = {
            "resource_names": [
                f"$steps.search_contacts.contacts[{i}].resource_name"
                for i in range(references_count)
            ]
        }

        # Validation
        errors = validator.validate_runtime_array_bounds(
            step_id="get_contacts_details",
            step_index=1,
            parameters=parameters,
            step_results=step_results,
        )

        # Assertions
        assert (
            len(errors) == expected_errors_count
        ), f"Contacts={contacts_count}, Refs={references_count}: expected {expected_errors_count} errors, got {len(errors)}"


class TestIssue40Scenario:
    """
    Tests spécifiques pour le scénario complet de l'Issue #40.

    Requête utilisateur: "recherche les détails des contacts jean et recherche
    pour chacun les 2 derniers emails qu'ils m'ont envoyés"

    Scénario:
    1. Tour 2: search_contacts_hua (max_results=5) → 2 contacts trouvés
    2. Tour 6: Planner génère plan avec get_contacts_details + 2 email searches
    3. get_contacts_details référence contacts[0] à contacts[4] (BUG: 5 au lieu de 2)
    4. Validation runtime détecte 3 erreurs (indices 2, 3, 4 hors limites)
    """

    @pytest.fixture
    def agent_results_issue_40(self) -> dict:
        """
        Simule agent_results du tour 2 (2 contacts trouvés).

        Structure réelle extraite des logs Docker (SESSION_24_ISSUE_40_ANALYSIS_COMPLETE.md).
        """
        return {
            "search_contacts_hua": {
                "data": {
                    "contacts": [
                        {
                            "resource_name": "people/c7167216827806720",
                            "names": [{"displayName": "jean Contact 1"}],
                            "emailAddresses": [{"value": "hua1@example.com"}],
                        },
                        {
                            "resource_name": "people/c2917579273732096",
                            "names": [{"displayName": "jean Contact 2"}],
                            "emailAddresses": [{"value": "hua2@example.com"}],
                        },
                    ]
                },
                "success": True,
            }
        }

    def test_issue_40_get_contacts_details_validation_error(self, agent_results_issue_40: dict):
        """
        Test Case: Issue #40 - get_contacts_details avec références hors limites.

        Scénario exact de l'Issue #40:
        - Planner génère plan avec resource_names[0-4] (5 références)
        - agent_results contient seulement 2 contacts (indices 0-1 valides)
        - Expected: 3 erreurs pour indices 2, 3, 4

        Phase 2.4 - Issue #40: Reproduction exacte du bug détecté.
        """
        validator = ReferenceValidator()

        # Plan généré par le Planner (BUG: 5 références au lieu de 2)
        parameters = {
            "resource_names": [
                "$steps.search_contacts_hua.contacts[0].resource_name",
                "$steps.search_contacts_hua.contacts[1].resource_name",
                "$steps.search_contacts_hua.contacts[2].resource_name",  # BUG: hors limites
                "$steps.search_contacts_hua.contacts[3].resource_name",  # BUG: hors limites
                "$steps.search_contacts_hua.contacts[4].resource_name",  # BUG: hors limites
            ]
        }

        # Validation runtime
        errors = validator.validate_runtime_array_bounds(
            step_id="get_contacts_details",
            step_index=1,
            parameters=parameters,
            step_results=agent_results_issue_40,
        )

        # Assertions
        assert len(errors) == 3, f"Expected 3 errors (Issue #40), got {len(errors)}"
        for err in errors:
            assert err.code == ToolErrorCode.INVALID_INPUT
            assert "contacts" in err.message
            assert "only 2 element(s) available" in err.message
            assert err.step_id == "get_contacts_details"

    def test_issue_40_corrected_plan_success(self, agent_results_issue_40: dict):
        """
        Test Case: Issue #40 - Plan corrigé avec seulement 2 références.

        Scénario:
        - Planner génère plan CORRECT avec resource_names[0-1] (2 références)
        - agent_results contient 2 contacts (indices 0-1 valides)
        - Expected: 0 erreur

        Phase 2.4 - Issue #40: Test du fix (plan correct après injection contexte).
        """
        validator = ReferenceValidator()

        # Plan corrigé (2 références seulement)
        parameters = {
            "resource_names": [
                "$steps.search_contacts_hua.contacts[0].resource_name",
                "$steps.search_contacts_hua.contacts[1].resource_name",
            ]
        }

        # Validation runtime
        errors = validator.validate_runtime_array_bounds(
            step_id="get_contacts_details",
            step_index=1,
            parameters=parameters,
            step_results=agent_results_issue_40,
        )

        # Assertions
        assert len(errors) == 0, f"Expected 0 errors (corrected plan), got {len(errors)}"
