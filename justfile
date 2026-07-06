set shell := ["bash", "-euo", "pipefail", "-c"]

export INFRA_HOST_UID := `scripts/host-id.sh uid`
export INFRA_HOST_GID := `scripts/host-id.sh gid`

# Show available commands
default:
    @just --list

# Fresh-checkout setup: build tools, create or clone values/, then show next files to edit
setup remote="":
    docker compose build infra
    @scripts/python.sh scripts/settings.py validate >/dev/null
    @selected_remote="$(scripts/discover-values-remote.sh "{{remote}}")"; \
    if [[ -d values ]]; then \
        scripts/values.sh check; \
    elif [[ -n "${selected_remote}" ]]; then \
        scripts/values.sh clone "${selected_remote}"; \
    else \
        scripts/values.sh init; \
    fi
    scripts/python.sh scripts/migrate-values.py
    docker compose run --rm infra python scripts/workspace-preflight.py --require-values
    @if [[ -t 0 && -t 1 ]]; then INFRA_COPY_SSH_KEYS=true docker compose run --rm infra bash scripts/bootstrap-pve-token.sh --if-needed; else printf 'Skipping Proxmox token bootstrap wizard because just setup is not interactive.\n'; fi
    @if [[ -t 0 && -t 1 ]]; then scripts/python.sh scripts/bootstrap-domain.py --if-needed; else printf 'Skipping domain wizard because just setup is not interactive.\n'; fi
    @printf '\nEdit these private values before running `just validate` and `just plan`:\n'
    @printf '  values/.env\n  values/terraform.tfvars\n  values/dns-records.local.json\n  values/ansible/inventory/local.yml\n'

# Show private values repo git status
[private]
status-values:
    scripts/values.sh status

# Verify values/ contains required files
[private]
check-values:
    scripts/values.sh check

# Migrate older private values layouts to the current schema
[private]
migrate-values: check-values
    scripts/python.sh scripts/migrate-values.py

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
validate-values: migrate-values
    scripts/validate-values.sh

# Validate public source and private values wiring
validate: validate-public validate-values

# Check upstream releases and update eligible pinned versions after the safety hold period
update:
    scripts/python.sh scripts/update.py

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
plan: migrate-values
    scripts/plan-infra.sh

# Apply reviewed infrastructure plan, then configure services with Ansible
apply: migrate-values
    scripts/apply-infra.sh
