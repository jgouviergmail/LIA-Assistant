#!/bin/bash
#
# Exhaustive test runner for LIA
# Runs ALL tests including slow integration tests
#
# Usage:
#   ./scripts/run-tests-exhaustive.sh           # Run all tests
#   ./scripts/run-tests-exhaustive.sh --fast    # Run fast tests only (same as pre-commit)
#   ./scripts/run-tests-exhaustive.sh --slow    # Run slow tests only
#   ./scripts/run-tests-exhaustive.sh --unit    # Run unit tests only (all)
#   ./scripts/run-tests-exhaustive.sh --agents  # Run agent tests only
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo -e "\n${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}   $1${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}\n"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ️  $1${NC}"
}

# Navigate to API directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_DIR="$SCRIPT_DIR/../apps/api"
cd "$API_DIR"

# Detect Python binary
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    PYTEST_BIN=".venv/Scripts/python.exe -m pytest"
else
    PYTEST_BIN=".venv/bin/pytest"
fi

# Default: run all tests
MODE="${1:-all}"

case "$MODE" in
    --fast)
        print_header "FAST TESTS (excluding slow/integration)"
        print_info "Running fast unit tests only..."
        $PYTEST_BIN tests/unit/ -v --tb=short -m "not integration"
        ;;

    --slow)
        print_header "SLOW TESTS ONLY (DB/integration in unit/)"
        print_info "Running slow tests marked with @pytest.mark.integration..."
        $PYTEST_BIN tests/unit/ -v --tb=short -m "integration"
        ;;

    --unit)
        print_header "ALL UNIT TESTS"
        print_info "Running all unit tests (including slow ones)..."
        $PYTEST_BIN tests/unit/ -v --tb=short
        ;;

    --agents)
        print_header "AGENT TESTS"
        print_info "Running agent-specific tests..."
        $PYTEST_BIN tests/agents/ -v --tb=short
        ;;

    --integration)
        print_header "INTEGRATION TESTS"
        print_info "Running tests from tests/integration/..."
        $PYTEST_BIN tests/integration/ -v --tb=short
        ;;

    all|--all)
        print_header "EXHAUSTIVE TEST SUITE"
        print_info "This will run ALL tests including slow ones."
        print_info "Estimated time: 5-15 minutes depending on hardware\n"

        START_TIME=$(date +%s)

        echo -e "${YELLOW}[1/4] Running fast unit tests...${NC}"
        $PYTEST_BIN tests/unit/ -v --tb=short -m "not integration" || true

        echo -e "\n${YELLOW}[2/4] Running slow unit tests (DB/integration)...${NC}"
        $PYTEST_BIN tests/unit/ -v --tb=short -m "integration" || true

        echo -e "\n${YELLOW}[3/4] Running agent tests...${NC}"
        $PYTEST_BIN tests/agents/ -v --tb=short || true

        echo -e "\n${YELLOW}[4/4] Running integration tests...${NC}"
        $PYTEST_BIN tests/integration/ -v --tb=short || true

        END_TIME=$(date +%s)
        DURATION=$((END_TIME - START_TIME))

        print_header "TEST SUMMARY"
        echo -e "Total time: ${DURATION} seconds"

        # Final combined report with coverage
        print_info "Generating combined coverage report..."
        $PYTEST_BIN tests/ --cov=src --cov-report=term-missing --cov-report=html -q --tb=no || true

        print_success "Exhaustive test suite completed!"
        echo -e "\nCoverage report available at: ${API_DIR}/htmlcov/index.html"
        ;;

    --help|-h)
        echo "Exhaustive test runner for LIA"
        echo ""
        echo "Usage: $0 [OPTION]"
        echo ""
        echo "Options:"
        echo "  --fast         Run fast unit tests only (excludes @pytest.mark.integration)"
        echo "  --slow         Run only slow tests (marked with @pytest.mark.integration)"
        echo "  --unit         Run all unit tests (fast + slow)"
        echo "  --agents       Run agent tests only"
        echo "  --integration  Run tests from tests/integration/"
        echo "  --all, all     Run ALL tests (default)"
        echo "  --help, -h     Show this help message"
        echo ""
        echo "Examples:"
        echo "  $0              # Run all tests (exhaustive)"
        echo "  $0 --fast       # Quick check (same as pre-commit)"
        echo "  $0 --slow       # Run only slow DB tests"
        ;;

    *)
        print_error "Unknown option: $MODE"
        echo "Use --help for usage information"
        exit 1
        ;;
esac
