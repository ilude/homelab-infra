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

# Validate public-safety rules for tracked source and scaffold templates
[private]
validate-public-safety:
    scripts/public-safety-check.sh

# Validate tracked public source only; does not require values/
[private]
validate-public: validate-public-safety
    docker compose config >/dev/null
    docker compose run --rm infra rm -rf infra/opentofu/.terraform
    docker compose run --rm infra python scripts/workspace-preflight.py
    docker compose run --rm infra tofu -chdir=infra/opentofu init -backend=false
    docker compose run --rm infra tofu fmt -check -recursive infra/opentofu scaffold/terraform.tfvars
    docker compose run --rm infra tofu -chdir=infra/opentofu validate
    docker compose run --rm infra tflint --chdir=infra/opentofu --minimum-failure-severity=error
    docker compose run --rm infra shellcheck scripts/*.sh tools/docker-entrypoint.sh
    docker compose run --rm infra python -m py_compile infra/opentofu/scripts/apply-technitium-dns.py scripts/parse-env.py scripts/public-safety-check.py scripts/settings.py scripts/tfplan-metadata.py scripts/update.py scripts/workspace-preflight.py tests/test_apply_technitium_dns.py tests/test_parse_env.py tests/test_public_safety_check.py tests/test_run_infra.py tests/test_settings.py tests/test_tfplan_metadata.py tests/test_update.py tests/test_workspace_preflight.py
    docker compose run --rm infra python infra/opentofu/scripts/apply-technitium-dns.py --check scaffold/dns-records.local.json
    docker compose run --rm infra python scripts/parse-env.py --env-file scaffold/.env.example >/dev/null
    docker compose run --rm infra python scripts/settings.py --settings settings.example.json validate >/dev/null
    docker compose run --rm infra python -m unittest discover -s tests -p 'test_*.py'
    docker compose run --rm infra ansible-playbook -i scaffold/ansible/inventory/local.yml --syntax-check infra/ansible/playbooks/site.yml
    docker compose run --rm infra ansible-lint infra/ansible

# Validate only private values wiring and data shape
[private]
validate-values: check-values
    scripts/run-infra.sh python scripts/workspace-preflight.py --require-values
    scripts/python.sh scripts/settings.py validate >/dev/null
    scripts/run-infra.sh python infra/opentofu/scripts/apply-technitium-dns.py --check values/dns-records.local.json
    scripts/run-infra.sh ansible-inventory -i values/ansible/inventory/local.yml --list >/dev/null
    @while IFS= read -r playbook; do playbook="$(printf '%s' "${playbook}" | tr -d '\r')"; scripts/run-infra.sh ansible-playbook -i values/ansible/inventory/local.yml --syntax-check "$playbook"; done < <(scripts/python.sh scripts/settings.py ansible-playbooks)

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
    docker compose run --rm infra rm -f tfplan tfplan.meta.json *.tfplan *.tfplan.meta.json

# Review infrastructure changes using private values; writes tfplan for `just apply`
plan: check-values clean-plans
    scripts/run-infra.sh python scripts/workspace-preflight.py --require-values
    scripts/run-infra.sh rm -rf infra/opentofu/.terraform
    scripts/run-infra.sh tofu -chdir=infra/opentofu init
    enabled_services="$(scripts/python.sh scripts/settings.py tofu-var)"; scripts/run-infra.sh tofu -chdir=infra/opentofu plan -var "enabled_services=${enabled_services}" -var-file=../../values/terraform.tfvars -state=../../values/terraform.tfstate -out=../../tfplan
    scripts/run-infra.sh tofu -chdir=infra/opentofu show ../../tfplan
    scripts/python.sh scripts/tfplan-metadata.py create --plan tfplan --metadata tfplan.meta.json

# Apply reviewed infrastructure plan, then configure services with Ansible
apply: check-values
    @if [[ -n "$(git -C values status --short)" ]]; then printf 'Private values repo has uncommitted changes; commit or discard them before just apply.\n' >&2; git -C values status --short >&2; exit 1; fi
    scripts/run-infra.sh python scripts/workspace-preflight.py --require-values
    test -f tfplan
    test -f tfplan.meta.json
    scripts/python.sh scripts/tfplan-metadata.py verify --plan tfplan --metadata tfplan.meta.json
    @printf 'Applying verified tfplan created by `just plan`.\n'
    trap 'rm -f tfplan tfplan.meta.json *.tfplan *.tfplan.meta.json' EXIT; scripts/run-infra.sh tofu -chdir=infra/opentofu apply -state=../../values/terraform.tfstate ../../tfplan && while IFS= read -r playbook; do playbook="$(printf '%s' "${playbook}" | tr -d '\r')"; INFRA_COPY_SSH_KEYS=true scripts/run-infra.sh ansible-playbook -i values/ansible/inventory/local.yml "$playbook"; done < <(scripts/python.sh scripts/settings.py ansible-playbooks) && while IFS= read -r hook; do hook="$(printf '%s' "${hook}" | tr -d '\r')"; "${hook}"; done < <(scripts/python.sh scripts/settings.py post-apply-hooks)
