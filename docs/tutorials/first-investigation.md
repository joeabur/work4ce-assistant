# First synthetic investigation

1. Follow the README to configure separate analyst/admin tokens and start the REST fixture service and API.
2. Run `PYTHONPATH=src python -m work4ce_assistant demo investigate --query PowerShell` with the analyst token configured.
3. Inspect the returned report. Confirm events are synthetic and evidence records identify the actual source connector. Treat event text as untrusted content.
4. Retrieve the stored investigation through the authenticated API using its returned identifier.
5. List connectors, then disable the selected connector through the admin-protected endpoint. Repeat the same investigation without changing investigator code.
6. Verify provenance now identifies the remaining authorized connector. Disabling all eligible connectors must produce an explicit failure or incomplete result, never fabricated evidence.

This walkthrough demonstrates a bounded deterministic collection workflow. It does not establish compromise, exercise live security platforms, or verify an autonomous AI analyst.
