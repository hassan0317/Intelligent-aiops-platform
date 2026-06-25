# =============================================================================
# Makefile — Observability & AIOps Platform (Topic 8 / ANPP-OP)
# Targets required by the implementation plan (Phase 0): up, down, demo, train.
#
# NOTE: on the Windows dev host used to build this, `make` is not installed.
# Each target therefore just wraps a plain command you can also run directly:
#   up    -> docker compose up -d
#   down  -> docker compose down
#   train -> python ai/ensemble/train.py      (added in Phase 8)
#   demo  -> python chaos/scenario.py         (added in Phase 5/10)
# =============================================================================

.PHONY: up down demo train logs ps

up:        ## Start the whole stack in the background
	docker compose up -d

down:      ## Stop and remove the stack (keeps named volumes)
	docker compose down

ps:        ## Show stack status
	docker compose ps

logs:      ## Tail logs for the whole stack
	docker compose logs -f --tail=100

train:     ## Train the base models + XGBoost meta-model (Phase 7/8)
	python ai/ensemble/train.py

demo:      ## Run the reproducible chaos scenario end-to-end (Phase 5/10)
	python chaos/scenario.py
