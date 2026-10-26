# Agent platform (Phase E, ADR-008). Offline targets need no cloud; cloud targets use declared cloud credentials.
#   make test              complete offline suite, including browser, policy, database, and Terraform checks
#   make test-policies     offline: RBAC / ValidatingAdmissionPolicy / Pod Security against a real local kube-apiserver
#   make onboard A=<agent> validate platform/agents/<agent>/agent.yaml and generate what the agent inherits
#   make onboard-check F=<manifest>  show every rule a manifest file breaks, one line each (renders nothing)
#   make agent-forward A=financial  port-forward an onboarded agent (Financial Agent: http://127.0.0.1:8081/)
#   make provider P=gemini render a provider profile (only active, owner-approved profiles render)
#   make plan | apply      Terraform for platform/clouds/gke (plan = cloud read, apply = cloud write)
#   make up | down         scale 0->1 + deploy + bootstrap  |  Postgres snapshot + scale to 0
#   make secrets           owner, once: generate platform Secrets (types the approval passphrase)
#   make port-forward      the only way in: http://127.0.0.1:8080/
#   make fault F=wedge|oom|crashloop|badimage   scripted fault on apps/fault-demo (owner identity)
#   make attack            live attack suite -> docs/evidence/attack-suite.json
#   make seed-demo         replace the demo user's expenses with the synthetic Sep/Oct 2026 seed (owner identity)
#   make inventory         read-only list of everything billable in the project
#   make demo-check        read-only readiness before a live session: one PASS/FAIL line per check, no secret values
#   make demo-reset        UP cluster only, asks first: reset fault-demo, restart the ops agent, re-seed, warm the redactor
#   make passphrase-check  owner, in a terminal: does the typed approval passphrase match Secret apps/app? prints {"match": ...}
#   make passphrase        owner, in a terminal: replace only the approval passphrase hash in apps/app (never --rotate)
#   make corpus-live       owner, after make up: the synthetic corpus through the real redactor (ids, categories, booleans only)
SHELL := /bin/bash
.ONESHELL:
.SHELLFLAGS := -Eeuo pipefail -c
PYTHON ?= python3
TOOLS ?= $(abspath .cache/platform-tools)
KUBECTL ?= $(TOOLS)/kubectl
TERRAFORM ?= $(TOOLS)/terraform
OPERATOR_PYTHON := $(abspath .cache/operator-venv/bin/python)
ENVTEST_DIR ?= .cache/envtest-v1.35.0
PY := PYTHONPATH=platform/core/src:platform/core/tests:platform/agents/financial:. $(PYTHON) -B
LIFECYCLE := PYTHONPATH=platform/core/src:. $(OPERATOR_PYTHON) -B platform/clouds/gke/lifecycle.py

.PHONY: test test-policies tools operator-env onboard onboard-check agent-forward provider plan apply up down port-forward fault attack inventory secrets seed-demo demo-check demo-reset passphrase-check passphrase corpus-live

tools:
	$(PYTHON) -B scripts/install-platform-tools.py

operator-env:
	$(PYTHON) -c 'import sys; assert sys.version_info[:2] == (3, 12), "Python 3.12 required"'
	if [[ ! -x "$(OPERATOR_PYTHON)" ]]; then $(PYTHON) -m venv .cache/operator-venv; fi
	$(OPERATOR_PYTHON) -m pip install --disable-pip-version-check --require-hashes -r requirements-platform.txt

test:
	bash scripts/test-offline.sh

test-policies: tools
	ENVTEST_BIN=$(abspath $(ENVTEST_DIR)) $(PY) -m unittest discover -s platform/core/tests -p test_envtest_policies.py -v

onboard:
	$(PY) -m agent_platform.onboarding render $(A)

onboard-check:
	$(PY) -m agent_platform.onboarding check-file $(F)

provider:
	$(PY) -m agent_platform.providers render $(P)

plan: tools operator-env
	$(LIFECYCLE) plan

apply: tools operator-env
	$(LIFECYCLE) apply

up: tools operator-env
	PATH="$(TOOLS):$$PATH" $(LIFECYCLE) up

down: tools operator-env
	$(LIFECYCLE) down

port-forward: tools operator-env
	$(LIFECYCLE) port-forward

agent-forward: tools operator-env
	$(LIFECYCLE) agent-forward $(A)

fault: tools operator-env
	$(LIFECYCLE) fault $(F)

attack: tools operator-env
	PATH="$(TOOLS):$$PATH" PYTHONPATH=platform/core/src:platform/core/tests:platform/agents/financial:. $(OPERATOR_PYTHON) -B platform/clouds/gke/attack_suite.py --out docs/evidence/attack-suite.json

corpus-live: tools operator-env
	PATH="$(TOOLS):$$PATH" PYTHONPATH=platform/core/src:platform/core/tests:platform/agents/financial:. $(OPERATOR_PYTHON) -B platform/clouds/gke/corpus_live.py

inventory: tools operator-env
	$(LIFECYCLE) inventory

demo-check: tools operator-env
	@PATH="$(TOOLS):$$PATH" PYTHONPATH=platform/core/src:. $(OPERATOR_PYTHON) -B platform/clouds/gke/demo_check.py

seed-demo: tools operator-env
	$(LIFECYCLE) seed-demo

demo-reset: tools operator-env
	@PATH="$(TOOLS):$$PATH" PYTHONPATH=platform/core/src:. $(OPERATOR_PYTHON) -B platform/clouds/gke/demo_reset.py

secrets: tools operator-env
	$(LIFECYCLE) secrets

passphrase-check: tools operator-env
	@PATH="$(TOOLS):$$PATH" PYTHONPATH=platform/core/src:. $(OPERATOR_PYTHON) -B platform/clouds/gke/passphrase.py check

passphrase: tools operator-env
	@PATH="$(TOOLS):$$PATH" PYTHONPATH=platform/core/src:. $(OPERATOR_PYTHON) -B platform/clouds/gke/passphrase.py replace
