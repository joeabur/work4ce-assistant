.PHONY: test serve demo-rest doctor
export PYTHONPATH := src

test:
	python -m unittest discover -s tests -v
serve:
	python -m work4ce_assistant serve
demo-rest:
	python -m work4ce_assistant.reference_servers rest --port 8766
doctor:
	python -m work4ce_assistant doctor
