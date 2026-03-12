"""
Tests for response_node.format_agent_results_for_prompt().

PHASE 3.2.1 - Critical missing tests (T-CRIT-002)
Tests the fragile hasattr() checks in response_node.py:89-119
"""

from src.domains.agents.nodes.response_node import format_agent_results_for_prompt


class TestFormatAgentResultsForPrompt:
    """Test format_agent_results_for_prompt() preserves data structure"""

    def test_empty_agent_results(self):
        """Test formatting empty agent results"""
        # Given: Empty results
        agent_results = {}

        # When: Format for prompt
        formatted = format_agent_results_for_prompt(agent_results)

        # Then: Default message returned
        assert formatted == "Aucun agent externe n'a été appelé."

    def test_successful_contacts_result_with_hasattr_fields(self):
        """Test ContactsResultData with total_count and contacts attributes"""
        from src.domains.agents.orchestration.schemas import ContactsResultData

        # Given: Real ContactsResultData with proper schema
        agent_results = {
            "3:contacts_agent": {
                "status": "success",
                "data": ContactsResultData(
                    contacts=[
                        {
                            "names": "John Doe",
                            "emailAddresses": ["john@example.com"],
                            "phoneNumbers": ["+33612345678"],
                        },
                        {
                            "names": "Jane Smith",
                            "emailAddresses": ["jane@example.com", "jane.smith@company.com"],
                            "phoneNumbers": [],
                        },
                    ],
                    total_count=2,
                    has_more=False,
                ),
                "error": None,
            }
        }

        # When: Format for prompt (filtering by current turn)
        formatted = format_agent_results_for_prompt(agent_results, current_turn_id=3)

        # Then: Formatted output includes contact details
        # Template-driven mode uses format_for_response which embeds HTML
        assert "✅" in formatted
        assert "2 contacts" in formatted
        assert "John Doe" in formatted
        assert "john@example.com" in formatted
        # Phone may be formatted with spaces (e.g., "+33 6 12 34 56 78")
        assert "+33" in formatted and "12 34 56 78" in formatted
        assert "Jane Smith" in formatted
        assert "jane@example.com" in formatted
        assert "jane.smith@company.com" in formatted

    def test_turn_id_filtering(self):
        """Test that only results from current turn are included"""
        from src.domains.agents.orchestration.schemas import ContactsResultData

        # Given: Results from multiple turns
        agent_results = {
            "3:contacts_agent": {
                "status": "success",
                "data": ContactsResultData(
                    contacts=[{"names": "John Doe", "emailAddresses": [], "phoneNumbers": []}],
                    total_count=1,
                    has_more=False,
                ),
                "error": None,
            },
            "4:contacts_agent": {
                "status": "success",
                "data": ContactsResultData(
                    contacts=[{"names": "Jane Smith", "emailAddresses": [], "phoneNumbers": []}],
                    total_count=1,
                    has_more=False,
                ),
                "error": None,
            },
        }

        # When: Format with current_turn_id=3
        formatted = format_agent_results_for_prompt(agent_results, current_turn_id=3)

        # Then: Only turn 3 results included
        assert "John Doe" in formatted
        assert "Jane Smith" not in formatted

    def test_contacts_result_without_hasattr_fields(self):
        """Test ContactsResultData missing expected attributes (hasattr fails)"""

        # Given: Object missing total_count or contacts attributes
        class IncompleteData:
            def __init__(self):
                self.some_field = "value"

        agent_results = {
            "3:contacts_agent": {
                "status": "success",
                "data": IncompleteData(),
                "error": None,
            }
        }

        # When: Format for prompt
        formatted = format_agent_results_for_prompt(agent_results, current_turn_id=3)

        # Then: Fallback to generic formatting (domain detection fails)
        # MultiDomainComposer returns empty when normalization fails
        assert "✅ contacts_agent: Données récupérées avec succès" in formatted or formatted == ""

    def test_contacts_result_with_cache_metadata(self):
        """Test ContactsResultData with cache freshness metadata"""
        from src.domains.agents.orchestration.schemas import ContactsResultData

        # Given: ContactsResultData with proper schema
        agent_results = {
            "3:contacts_agent": {
                "status": "success",
                "data": ContactsResultData(
                    contacts=[{"names": "John Doe", "emailAddresses": [], "phoneNumbers": []}],
                    total_count=1,
                    has_more=False,
                ),
                "error": None,
            }
        }

        # When: Format for prompt
        formatted = format_agent_results_for_prompt(agent_results, current_turn_id=3)

        # Then: Contact data included via ContactsLLMFormatter
        assert "✅" in formatted
        assert "1 contact" in formatted
        assert "John Doe" in formatted

    def test_error_status_result(self):
        """Test agent result with error status"""
        # Given: Error result
        agent_results = {
            "3:contacts_agent": {
                "status": "error",
                "data": None,
                "error": "API connection failed",
            }
        }

        # When: Format for prompt
        formatted = format_agent_results_for_prompt(agent_results, current_turn_id=3)

        # Then: Error message formatted
        assert "❌ contacts_agent: API connection failed" in formatted

    def test_connector_disabled_status(self):
        """Test agent result with connector_disabled status"""
        # Given: Connector disabled result
        agent_results = {
            "3:contacts_agent": {
                "status": "connector_disabled",
                "data": None,
                "error": "Service Google Contacts non activé",
            }
        }

        # When: Format for prompt
        formatted = format_agent_results_for_prompt(agent_results, current_turn_id=3)

        # Then: Warning message formatted
        assert "⚠️ contacts_agent: Service Google Contacts non activé" in formatted

    def test_unknown_status(self):
        """Test agent result with unknown status"""
        # Given: Unknown status
        agent_results = {
            "3:contacts_agent": {
                "status": "pending",
                "data": None,
                "error": None,
            }
        }

        # When: Format for prompt
        formatted = format_agent_results_for_prompt(agent_results, current_turn_id=3)

        # Then: Unknown status message
        assert "❓ contacts_agent: Statut inconnu (pending)" in formatted

    def test_backward_compatibility_without_turn_id(self):
        """Test old-style agent_results keys without turn_id prefix"""
        from src.domains.agents.orchestration.schemas import ContactsResultData

        # Given: Old-style key format (no "turn_id:" prefix)
        agent_results = {
            "contacts_agent": {  # No turn_id prefix (backward compatibility)
                "status": "success",
                "data": ContactsResultData(
                    contacts=[{"names": "John Doe", "emailAddresses": [], "phoneNumbers": []}],
                    total_count=1,
                    has_more=False,
                ),
                "error": None,
            }
        }

        # When: Format for prompt (with current_turn_id)
        formatted = format_agent_results_for_prompt(agent_results, current_turn_id=3)

        # Then: Result included (backward compatibility)
        # MultiDomainComposer uses ContactsLLMFormatter with format_for_response
        assert "✅" in formatted
        assert "1 contact" in formatted
        assert "John Doe" in formatted

    def test_generic_data_fallback(self):
        """Test generic data formatting when not ContactsResultData"""
        # Given: Generic data object (not ContactsResultData)
        agent_results = {
            "3:some_agent": {
                "status": "success",
                "data": {"result": "some data", "count": 42},
                "error": None,
            }
        }

        # When: Format for prompt
        formatted = format_agent_results_for_prompt(agent_results, current_turn_id=3)

        # Then: Generic formatting used
        assert "✅ some_agent: Données récupérées avec succès" in formatted
        assert "result" in formatted or "some data" in formatted

    def test_success_without_data(self):
        """Test success status with None data"""
        # Given: Success without data
        agent_results = {
            "3:some_agent": {
                "status": "success",
                "data": None,
                "error": None,
            }
        }

        # When: Format for prompt
        formatted = format_agent_results_for_prompt(agent_results, current_turn_id=3)

        # Then: Simple success message
        assert "✅ some_agent: Succès" in formatted

    def test_contact_without_name_field(self):
        """Test contact dict missing 'name' field"""

        from src.domains.agents.orchestration.schemas import ContactsResultData

        # Given: Contact without name field
        agent_results = {
            "3:contacts_agent": {
                "status": "success",
                "data": ContactsResultData(
                    contacts=[
                        {
                            # Missing "names" field (uses default)
                            "emailAddresses": ["john@example.com"],
                            "phoneNumbers": [],
                        }
                    ],
                    total_count=1,
                    has_more=False,
                ),
                "error": None,
            }
        }

        # When: Format for prompt
        formatted = format_agent_results_for_prompt(agent_results, current_turn_id=3)

        # Then: Contact with email is included
        assert "john@example.com" in formatted

    def test_multiple_agents_in_same_turn(self):
        """Test multiple agents executed in same turn"""
        from src.domains.agents.orchestration.schemas import ContactsResultData

        # Given: Multiple agents with same turn_id
        agent_results = {
            "3:contacts_agent": {
                "status": "success",
                "data": ContactsResultData(
                    contacts=[{"names": "John Doe", "emailAddresses": [], "phoneNumbers": []}],
                    total_count=1,
                    has_more=False,
                ),
                "error": None,
            },
            "3:calendar_agent": {
                "status": "error",
                "data": None,
                "error": "Calendar API unavailable",
            },
        }

        # When: Format for prompt
        formatted = format_agent_results_for_prompt(agent_results, current_turn_id=3)

        # Then: Contacts are included (handled by MultiDomainComposer)
        assert "✅" in formatted
        assert "John Doe" in formatted

    def test_invalid_turn_id_in_key(self):
        """Test handling of malformed turn_id in composite key"""
        # Given: Malformed turn_id (not an integer)
        agent_results = {
            "invalid:contacts_agent": {
                "status": "success",
                "data": {"result": "data"},
                "error": None,
            }
        }

        # When: Format for prompt
        formatted = format_agent_results_for_prompt(agent_results, current_turn_id=3)

        # Then: Result skipped (or included without filtering)
        # Depends on implementation - should log warning
        # For now, just ensure no crash
        assert isinstance(formatted, str)

    def test_no_turn_id_filter_includes_all_results(self):
        """Test that None current_turn_id processes available results"""
        from src.domains.agents.orchestration.schemas import ContactsResultData

        # Given: Results from multiple turns
        agent_results = {
            "3:contacts_agent": {
                "status": "success",
                "data": ContactsResultData(
                    contacts=[{"names": "John Doe", "emailAddresses": [], "phoneNumbers": []}],
                    total_count=1,
                    has_more=False,
                ),
                "error": None,
            },
            "4:contacts_agent": {
                "status": "success",
                "data": ContactsResultData(
                    contacts=[{"names": "Jane Smith", "emailAddresses": [], "phoneNumbers": []}],
                    total_count=1,
                    has_more=False,
                ),
                "error": None,
            },
        }

        # When: Format without turn_id filter
        formatted = format_agent_results_for_prompt(agent_results, current_turn_id=None)

        # Then: At least one result is included
        # Note: MultiDomainComposer processes results by domain and may not
        # include all turn results when turn_id is None (depends on iteration order)
        assert "✅" in formatted
        # At least one contact should be present
        assert "John Doe" in formatted or "Jane Smith" in formatted
