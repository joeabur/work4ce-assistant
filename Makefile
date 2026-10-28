.PHONY: test test-postgres serve demo-rest doctor migrate
export PYTHONPATH := src

test:
	python -m unittest discover -s tests -v
test-postgres:
	python scripts/test_postgres.py
migrate:
	python -m work4ce_assistant database migrate
serve:
	python -m work4ce_assistant serve
demo-rest:
	python -m work4ce_assistant.reference_servers rest --port 8766
doctor:
	python -m work4ce_assistant doctor
