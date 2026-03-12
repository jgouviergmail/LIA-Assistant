# Checklist: Adding a New Connector

**Service Name**: _________________________ (e.g., Gmail, Calendar, Drive)
**Developer**: _________________________
**Date Started**: _________________________
**Estimated Time**: 6-9h with templates

---

## 📋 Pre-Work (30 min)

### Planning
- [ ] **Identify service** and API documentation
  - Service: _________________________
  - API Docs URL: _________________________
  - API Version: _________________________

- [ ] **List tools to implement**
  1. _________________________ (category: read/write)
  2. _________________________ (category: read/write)
  3. _________________________ (category: read/write)

- [ ] **Define OAuth scopes needed**
  - Scope 1: _________________________
  - Scope 2: _________________________
  - Scope 3: _________________________

- [ ] **Choose connector type**
  - Google service: `GOOGLE_*`
  - Microsoft service: `MICROSOFT_*`
  - Other: `SERVICE_NAME`

---

## 🔧 Phase 1: API Client Implementation (2-3h)

### Step 1.1: Create Client File

- [ ] Copy template to: `apps/api/src/domains/connectors/clients/{service}_client.py`
  ```bash
  cp docs/templates/connector_client_template.py apps/api/src/domains/connectors/clients/{service}_client.py
  ```

- [ ] Rename class: `YourServiceClient` → `{Service}Client`
- [ ] Set `BASE_URL` to API base URL
- [ ] Update docstring with service description and API docs link

**API Base URL**: _________________________

### Step 1.2: Implement Core Methods

- [ ] Implement `_get_headers()` with required headers
  - [ ] Authorization header
  - [ ] Accept header
  - [ ] API version header (if needed)
  - [ ] User-Agent (if needed)

- [ ] Implement `_is_token_expired()` logic
  - [ ] Parse `expires_at` from credentials
  - [ ] Add 60s buffer for refresh

- [ ] Implement `_refresh_token()` using connector_service
  - [ ] Call `connector_service.refresh_oauth_token()`
  - [ ] Update `self.credentials`

### Step 1.3: Implement Business Methods

For each tool:
- [ ] **Tool 1**: _________________________ method
  - [ ] Method signature defined
  - [ ] Docstring complete
  - [ ] API call implemented with `_make_request()`
  - [ ] Response parsing
  - [ ] Error handling
  - [ ] Logging

- [ ] **Tool 2**: _________________________ method
  - [ ] Method signature defined
  - [ ] Docstring complete
  - [ ] API call implemented
  - [ ] Response parsing
  - [ ] Error handling
  - [ ] Logging

- [ ] **Tool 3**: _________________________ method
  - [ ] Method signature defined
  - [ ] Docstring complete
  - [ ] API call implemented
  - [ ] Response parsing
  - [ ] Error handling
  - [ ] Logging

### Step 1.4: Update ConnectorType Enum

- [ ] Open `apps/api/src/domains/connectors/models.py`
- [ ] Add new enum value:
  ```python
  GOOGLE_{SERVICE} = "google_{service}"  # Example
  ```
- [ ] ConnectorType added: `_________________________`

### Step 1.5: Configure OAuth in ConnectorService

- [ ] Open `apps/api/src/domains/connectors/service.py`
- [ ] Add OAuth scopes mapping for new connector type
- [ ] Add credentials retrieval logic (if custom)

**Test API Client**:
- [ ] Manual test: Create client instance
- [ ] Manual test: Call each method
- [ ] Verify OAuth token refresh works

---

## 🛠️ Phase 2: Tool Implementation (1-2h)

### Step 2.1: Create Tool File

- [ ] Copy template to: `apps/api/src/domains/agents/tools/{service}_tools.py`
  ```bash
  cp docs/templates/connector_tool_template.py apps/api/src/domains/agents/tools/{service}_tools.py
  ```

### Step 2.2: Define Constants

- [ ] Open `apps/api/src/domains/agents/constants.py`
- [ ] Add agent constant:
  ```python
  AGENT_{SERVICE} = "{service}"
  ```
- [ ] Add context domain constant:
  ```python
  CONTEXT_DOMAIN_{SERVICE} = "{service}"
  ```

**Constants added**:
- `AGENT_{SERVICE}`: _________________________
- `CONTEXT_DOMAIN_{SERVICE}`: _________________________

### Step 2.3: Define Context Item Schema

- [ ] Create `{Service}Item` Pydantic model
  - [ ] Primary ID field defined
  - [ ] Display name field defined
  - [ ] Reference fields for fuzzy matching
  - [ ] All relevant fields added

- [ ] Register with `ContextTypeRegistry`
  - [ ] `domain` set to context domain
  - [ ] `agent_name` set to agent constant
  - [ ] `item_schema` set to Item model
  - [ ] `primary_id_field` specified
  - [ ] `display_name_field` specified
  - [ ] `reference_fields` list defined
  - [ ] `icon` emoji chosen

**Context Item Fields**:
- Primary ID: _________________________
- Display name: _________________________
- Reference fields: _________________________

### Step 2.4: Implement Tool Classes

For each tool:

**Tool 1**: _________________________

- [ ] Class name: `{Tool}Tool`
- [ ] Set `connector_type` to `ConnectorType.{SERVICE}`
- [ ] Set `client_class` to `{Service}Client`
- [ ] Set `tool_name` in `__init__`
- [ ] Set `operation` in `__init__`
- [ ] Implement `execute_api_call()`:
  - [ ] Extract parameters from `kwargs`
  - [ ] Call client method
  - [ ] Track timing metrics
  - [ ] Track success metrics
  - [ ] Log result
  - [ ] Return result dict
- [ ] Optional: Override `format_response()` if custom formatting needed
- [ ] Create tool instance: `_tool_instance = {Tool}Tool()`
- [ ] Apply `@connector_tool` decorator:
  - [ ] `name` set (snake_case)
  - [ ] `agent_name` set to agent constant
  - [ ] `context_domain` set to context domain
  - [ ] `category` set ("read" or "write")
- [ ] Define tool function:
  - [ ] Parameters with type hints
  - [ ] Docstring complete (LLM-readable)
  - [ ] `runtime` parameter with `InjectedToolArg`
  - [ ] Delegate to `_tool_instance.execute()`

**Tool 2**: _________________________

- [ ] Class name: `{Tool}Tool`
- [ ] Set `connector_type`
- [ ] Set `client_class`
- [ ] Implement `execute_api_call()`
- [ ] Create instance
- [ ] Apply decorator
- [ ] Define function

**Tool 3**: _________________________

- [ ] Class name: `{Tool}Tool`
- [ ] Set `connector_type`
- [ ] Set `client_class`
- [ ] Implement `execute_api_call()`
- [ ] Create instance
- [ ] Apply decorator
- [ ] Define function

---

## 📊 Phase 3: Metrics (Optional but Recommended) (30 min)

### Step 3.1: Define Prometheus Metrics

- [ ] Open `apps/api/src/infrastructure/observability/metrics_agents.py`
- [ ] Add API call counter:
  ```python
  {service}_api_calls = Counter(
      "{service}_api_calls_total",
      "Total API calls to {Service}",
      ["operation", "status"],
  )
  ```
- [ ] Add API latency histogram:
  ```python
  {service}_api_latency = Histogram(
      "{service}_api_latency_seconds",
      "Latency of {Service} API calls",
      ["operation"],
  )
  ```
- [ ] Add results count histogram (if applicable):
  ```python
  {service}_results_count = Histogram(
      "{service}_results_count",
      "Number of results returned",
      ["operation"],
  )
  ```

### Step 3.2: Integrate Metrics in Tools

- [ ] Import metrics in tool file
- [ ] Track API calls in `execute_api_call()`:
  - [ ] Start timing
  - [ ] Execute API call
  - [ ] End timing
  - [ ] Observe latency
  - [ ] Increment counter (success/error)

---

## 🧪 Phase 4: Testing (2-3h)

### Step 4.1: Unit Tests for Client

- [ ] Create `tests/connectors/clients/test_{service}_client.py`
- [ ] Test `_get_headers()`
- [ ] Test `_is_token_expired()`
- [ ] Test `_refresh_token()`
- [ ] Test each business method with mocked responses
- [ ] Test error handling (HTTP errors, network errors)

**Tests passing**: _____ / _____

### Step 4.2: Unit Tests for Tools

- [ ] Create `tests/agents/tools/test_{service}_tools.py`
- [ ] Test each tool with mocked client
- [ ] Test parameter validation
- [ ] Test error responses
- [ ] Test context item registration

**Tests passing**: _____ / _____

### Step 4.3: Integration Tests

- [ ] Create `tests/integration/test_{service}_integration.py`
- [ ] Test OAuth flow end-to-end (with test account)
- [ ] Test each tool with real API calls (staging/sandbox if available)
- [ ] Test token refresh flow
- [ ] Test error scenarios

**Tests passing**: _____ / _____

---

## 📝 Phase 5: Documentation (1h)

### Step 5.1: Code Documentation

- [ ] All classes have docstrings
- [ ] All methods have docstrings with:
  - [ ] Description
  - [ ] Args
  - [ ] Returns
  - [ ] Raises
  - [ ] Examples
- [ ] All parameters have type hints
- [ ] TODOs removed from templates

### Step 5.2: User Documentation

- [ ] Create `docs/connectors/{service}.md` with:
  - [ ] Service description
  - [ ] OAuth setup instructions
  - [ ] Available tools list
  - [ ] Usage examples
  - [ ] Troubleshooting

### Step 5.3: Developer Documentation

- [ ] Update `docs/architecture/CONNECTORS.md` with new connector
- [ ] Update `docs/architecture/TOOLS.md` with new tools
- [ ] Add entry to `docs/optim/PHASE_5_GENERALIZATION_ANALYSIS.md` examples section

---

## ✅ Phase 6: Validation & Deployment (30 min)

### Step 6.1: Code Quality

- [ ] Run `ruff check apps/api/src/domains/connectors/clients/{service}_client.py`
- [ ] Run `ruff check apps/api/src/domains/agents/tools/{service}_tools.py`
- [ ] Run `mypy` on new files
- [ ] Fix all linter warnings
- [ ] Format code with `ruff format`

### Step 6.2: Final Testing

- [ ] Run full test suite: `pytest tests/ -v`
- [ ] All tests passing (0 regressions)
- [ ] Manual test in dev environment
- [ ] Verify metrics in Prometheus/Grafana

**Test Results**:
- Total tests: _____
- Passing: _____
- Failing: _____
- Regressions: _____

### Step 6.3: Git Commit

- [ ] Stage changes: `git add .`
- [ ] Commit with descriptive message:
  ```bash
  git commit -m "feat: add {Service} connector with {N} tools

  - Add {Service}Client with OAuth support
  - Add tools: {tool1}, {tool2}, {tool3}
  - Add context type registration for {service} items
  - Add Prometheus metrics tracking
  - Add unit and integration tests (X passing)

  Estimated time savings: 6-9h using connector templates

  Co-Authored-By: Claude <noreply@anthropic.com>"
  ```

- [ ] Push to remote (if applicable)

---

## 📊 Summary Statistics

**Time Tracking**:
- Phase 1 (API Client): _____ hours
- Phase 2 (Tools): _____ hours
- Phase 3 (Metrics): _____ hours
- Phase 4 (Testing): _____ hours
- Phase 5 (Documentation): _____ hours
- Phase 6 (Validation): _____ hours
- **TOTAL**: _____ hours

**Expected**: 6-9h with templates
**Actual**: _____ hours
**Variance**: _____ hours (_____ %)

**Code Statistics**:
- Lines of client code: _____
- Lines of tool code: _____
- Lines of test code: _____
- Total lines: _____

**Reduction from templates**: ~70-80% less code than without ConnectorTool pattern

---

## 🎉 Completion Checklist

- [ ] All phases complete
- [ ] All tests passing
- [ ] Documentation complete
- [ ] Code committed
- [ ] Ready for code review
- [ ] Ready for deployment

**Status**: ❌ In Progress / ✅ Complete
**Date Completed**: _________________________

---

## 💡 Notes & Lessons Learned

**What went well**:


**Challenges encountered**:


**Improvements for next connector**:


---

**Connector**: _________________________
**Developer**: _________________________
**Date**: _________________________
