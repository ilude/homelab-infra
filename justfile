set shell := ["bash", "-euo", "pipefail", "-c"]

export INFRA_HOST_UID := `scripts/host-id.sh uid`
export INFRA_HOST_GID := `scripts/host-id.sh gid`

# Show available commands
default:
    @just --list

# Fresh-checkout setup: build tools, verify BWS, and create or clone excluded private data
setup remote="":
    docker compose build infra
    @scripts/python.sh scripts/settings.py validate >/dev/null
    @if [[ -d values ]]; then \
        scripts/values.sh check; \
    elif [[ -n "{{remote}}" ]]; then \
        scripts/values.sh clone "{{remote}}"; \
        scripts/values.sh check; \
    else \
        scripts/values.sh init; \
    fi
    scripts/run-infra.sh python scripts/settings.py validate
    @printf '\nBWS configuration is ready. values/ is retained only for excluded backups and artifacts.\n'

# Show private values repo git status
[private]
status-values:
    scripts/values.sh status

# Verify values/ contains no obsolete BWS-managed configuration or state
[private]
check-values:
    scripts/values.sh check

# Validate public-safety rules for tracked source and scaffold templates
[private]
validate-public-safety:
    scripts/public-safety-check.sh

# Validate tracked public source only; does not require values/
[private]
validate-public: validate-public-safety
    scripts/validate-public.sh

# Validate only private values wiring and data shape
[private]
validate-values: check-values
    scripts/validate-values.sh

# Validate public source and private values wiring
validate: validate-public validate-values

# Check upstream releases and update eligible pinned versions after the safety hold period
[script]
update *selectors:
    #!/usr/bin/env bash
    set -euo pipefail
    BWS_WRITEBACK=1 scripts/run-infra.sh python scripts/update.py "$@"

# Show recent Forgejo Actions runs for the private values repo
[private]
actions-status limit="10":
    INFRA_COPY_SSH_KEYS=true scripts/run-infra.sh python scripts/forgejo-actions-monitor.py status --limit "{{limit}}"

# Watch a Forgejo Actions run until it reaches a terminal state
[private]
actions-watch run="latest":
    INFRA_COPY_SSH_KEYS=true scripts/run-infra.sh python scripts/forgejo-actions-monitor.py watch "{{run}}"

# Show redacted logs for a Forgejo Actions run
[private]
actions-logs run="latest" tail="200":
    INFRA_COPY_SSH_KEYS=true scripts/run-infra.sh python scripts/forgejo-actions-monitor.py logs "{{run}}" --tail "{{tail}}"

# Show Forgejo Actions runner registration and service status
[private]
actions-runners:
    INFRA_COPY_SSH_KEYS=true scripts/run-infra.sh python scripts/forgejo-actions-monitor.py runners

# Remove saved plan artifacts
[private]
clean-plans:
    rm -f tfplan tfplan.meta.json *.tfplan *.tfplan.meta.json

# Review infrastructure changes using private values; writes tfplan for `just apply`
plan:
    scripts/plan-infra.sh

# Apply reviewed infrastructure plan, then configure services with Ansible
apply:
    scripts/apply-infra.sh
