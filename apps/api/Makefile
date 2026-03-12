# Makefile for LIA API
# Development and i18n management commands

.PHONY: help i18n-extract i18n-init i18n-update i18n-compile i18n-all

help:
	@echo "Available commands:"
	@echo "  make i18n-extract  - Extract translatable strings from source code"
	@echo "  make i18n-init     - Initialize new language catalogs (first time only)"
	@echo "  make i18n-update   - Update existing language catalogs with new strings"
	@echo "  make i18n-compile  - Compile .po files to .mo binaries"
	@echo "  make i18n-all      - Extract, update, and compile (full workflow)"

# Extract translatable strings from Python source
i18n-extract:
	@echo "Extracting translatable strings..."
	pybabel extract -F babel.cfg -o locales/messages.pot src/

# Initialize new language catalogs (run once per language)
i18n-init:
	@echo "Initializing language catalogs..."
	pybabel init -i locales/messages.pot -d locales -l fr
	pybabel init -i locales/messages.pot -d locales -l en
	pybabel init -i locales/messages.pot -d locales -l es
	pybabel init -i locales/messages.pot -d locales -l de
	pybabel init -i locales/messages.pot -d locales -l it

# Update existing catalogs with new strings
i18n-update:
	@echo "Updating language catalogs..."
	pybabel update -i locales/messages.pot -d locales -D messages

# Compile .po files to .mo binaries
i18n-compile:
	@echo "Compiling translations..."
	pybabel compile -d locales -D messages

# Full workflow: extract, update, compile
i18n-all: i18n-extract i18n-update i18n-compile
	@echo "i18n workflow complete!"
