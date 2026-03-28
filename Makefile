SHELL := /usr/bin/env bash

DEFAULT_PARAMETERS_FILE := infra/bicep/main.parameters.json
PARAMETERS_FILE ?= infra/bicep/main.parameters.json
DEPLOYMENT_NAME ?= offhours-scheduler-deploy
NO_PUBLISH ?= 0
VALIDATE ?= 1

DEPLOY_ARGS := --deployment-name $(DEPLOYMENT_NAME)

ifneq ($(PARAMETERS_FILE),$(DEFAULT_PARAMETERS_FILE))
DEPLOY_ARGS += --parameters-file $(PARAMETERS_FILE)
endif

ifeq ($(NO_PUBLISH),1)
DEPLOY_ARGS += --no-publish
endif

ifeq ($(VALIDATE),0)
DEPLOY_ARGS += --no-validate
endif

.PHONY: help deploy deploy-no-publish

help:
	@echo "Targets:"
	@echo "  make deploy"
	@echo "  make deploy PARAMETERS_FILE=infra/bicep/main.parameters.json"
	@echo "  make deploy NO_PUBLISH=1"
	@echo "  make deploy VALIDATE=0"

deploy:
	bash ./scripts/deploy_scheduler.sh $(DEPLOY_ARGS)

deploy-no-publish:
	bash ./scripts/deploy_scheduler.sh $(DEPLOY_ARGS) --no-publish
