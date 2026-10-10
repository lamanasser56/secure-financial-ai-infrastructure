# Agent platform (Phase E, ADR-008). Offline targets need no cloud; cloud targets run on the owner's laptop.
#   make test              offline: unit tests, provider drift, manifest invariants, terraform validate
#   make test-policies     offline: RBAC / ValidatingAdmissionPolicy / Pod Security against a real local kube-apiserver
#   make provider P=gemini render a provider profile (only active, owner-approved profiles render)
#   make plan | apply      Terraform for platform/clouds/gke (plan = cloud read, apply = cloud write)
#   make up | down         scale 0->1 + deploy + bootstrap  |  Postgres snapshot + scale to 0
#   make port-forward      the only way in: http://127.0.0.1:8080/
#   make fault F=oom|crashloop|badimage   scripted fault on apps/fault-demo (owner identity)
#   make attack            live attack suite -> docs/evidence/attack-suite.json
#   make inventory         read-only list of everything billable in the project
SHELL := /bin/bash
.ONESHELL:
.SHELLFLAGS := -Eeuo pipefail -c
PYTHON ?= python3
TOOLS ?= $(HOME)/portfolio-sdp-us-east1-401f097/tools
KUBECTL ?= $(TOOLS)/kubectl
TERRAFORM ?= $(TOOLS)/terraform
ENVTEST_DIR ?= .cache/envtest-v1.35.0
ENVTEST_URL := https://github.com/kubernetes-sigs/controller-tools/releases/download/envtest-v1.35.0/envtest-v1.35.0-linux-amd64.tar.gz
ENVTEST_SHA512 := 130369c16f076e724d089189afaede960316f5f5dea6cf57be7a4fc6f09c77342893192509790e4056e116e232dff832ed863f5bd55dcb55d38f3ab834828a11
PY := PYTHONPATH=platform/core/src:platform/core/tests:. $(PYTHON) -B
LIFECYCLE := PYTHONPATH=platform/core/src:. $(PYTHON) -B platform/clouds/gke/lifecycle.py

.PHONY: test test-policies provider plan apply up down port-forward fault attack inventory secrets

test:
	PATH="$(TOOLS):$$PATH" $(PY) -m unittest discover -s platform/core/tests -p 'test_*.py'
	$(PY) -m agent_platform.providers check gemini
	$(TERRAFORM) -chdir=platform/clouds/gke/terraform/root init -backend=false -input=false -lockfile=readonly >/dev/null
	$(TERRAFORM) -chdir=platform/clouds/gke/terraform/root validate -no-color
	$(TERRAFORM) fmt -check -recursive platform/clouds/gke/terraform

test-policies: $(ENVTEST_DIR)/kube-apiserver
	ENVTEST_BIN=$(abspath $(ENVTEST_DIR)) $(PY) -m unittest discover -s platform/core/tests -p test_envtest_policies.py -v

$(ENVTEST_DIR)/kube-apiserver:
	mkdir -p $(ENVTEST_DIR)
	curl -fsSL -o $(ENVTEST_DIR)/envtest.tgz $(ENVTEST_URL)
	echo "$(ENVTEST_SHA512)  $(ENVTEST_DIR)/envtest.tgz" | sha512sum -c -
	tar -xzf $(ENVTEST_DIR)/envtest.tgz -C $(ENVTEST_DIR) --strip-components=2
	rm $(ENVTEST_DIR)/envtest.tgz

provider:
	$(PY) -m agent_platform.providers render $(P)

plan:
	$(LIFECYCLE) plan

apply:
	$(LIFECYCLE) apply

up:
	PATH="$(TOOLS):$$PATH" $(LIFECYCLE) up

down:
	$(LIFECYCLE) down

port-forward:
	$(LIFECYCLE) port-forward

fault:
	$(LIFECYCLE) fault $(F)

attack:
	PATH="$(TOOLS):$$PATH" $(PY) platform/clouds/gke/attack_suite.py --out docs/evidence/attack-suite.json

inventory:
	$(LIFECYCLE) inventory
