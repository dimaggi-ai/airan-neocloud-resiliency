.PHONY: test ladder transports figures install validation

test: validation
	python3 -m unittest discover -s tests -v

validation:
	python3 validation.py

ladder:
	python3 -m resiliency.cli ladder --years 2000

transports:
	python3 -m resiliency.cli transports

figures:
	python3 run.py

install:
	pip install -e ".[figures]"
