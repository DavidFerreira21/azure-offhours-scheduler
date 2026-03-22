SHELL := /usr/bin/env bash

PARAMETERS_FILE ?= infra/bicep/main.parameters.json
DEPLOYMENT_NAME ?= offhours-scheduler-deploy
NO_PUBLISH ?= 0

DEPLOY_ARGS := --parameters-file $(PARAMETERS_FILE) --deployment-name $(DEPLOYMENT_NAME)

ifeq ($(NO_PUBLISH),1)
DEPLOY_ARGS += --no-publish
endif

.PHONY: help deploy deploy-no-publish

help:
	@echo "Targets:"
	@echo "  make deploy"
	@echo "  make deploy PARAMETERS_FILE=infra/bicep/main.parameters.json"
	@echo "  make deploy NO_PUBLISH=1"

deploy:
	bash ./scripts/deploy_scheduler.sh $(DEPLOY_ARGS)

deploy-no-publish:
	bash ./scripts/deploy_scheduler.sh --parameters-file $(PARAMETERS_FILE) --deployment-name $(DEPLOYMENT_NAME) --no-publish
