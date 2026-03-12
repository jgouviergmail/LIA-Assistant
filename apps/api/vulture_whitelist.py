"""
Vulture Whitelist for Dead Code Detection

This file contains intentional unused code that should not be flagged:
- Callback method parameters required by LangChain interface
- Logging decorator parameters required by structlog
- PII filter decorator parameters

See: https://github.com/jendrikseipp/vulture#ignoring-files
"""

# LangChain callback interface parameters (required by abstract base class)
# These parameters are part of the BaseCallbackHandler interface contract
serialized = None
prompts = None
parent_run_id = None
tags = None

# Decorator parameters (required by signature but not used in wrapper)
method_name = None
