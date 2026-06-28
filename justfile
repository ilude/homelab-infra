set shell := ["bash", "-euo", "pipefail", "-c"]

# Show available commands
default:
    @just --list

# Fresh-checkout setup: build tools, create or clone values/, then show next files to edit
setup remote="":
    docker compose build infra
    @if [[ -d values ]]; then \
        scripts/values.sh check; \
    elif [[ -n "{{remote}}" ]]; then \
        scripts/values.sh clone "{{remote}}"; \
    else \
        scripts/values.sh init; \
    fi
    @printf '\nEdit these private values before running `just validate` and `just plan`:\n'
    @printf '  values/.env\n  values/terraform.tfvars\n  values/dns-records.local.json\n  values/ansible/inventory/local.yml\n'

# Show private values repo git status
status-values:
    scripts/values.sh status

# Verify values/ contains required files
check-values:
    scripts/values.sh check

# Validate OpenTofu, shell, Python, and Ansible source
validate: check-values
    docker compose config >/dev/null
    scripts/run-infra.sh tofu init -backend=false
    scripts/run-infra.sh tofu fmt -check *.tf values.example/terraform.tfvars
    scripts/run-infra.sh tofu validate
    docker compose run --rm infra shellcheck scripts/*.sh
    docker compose run --rm infra python -m py_compile scripts/apply-technitium-dns.py
    docker compose run --rm infra python -m json.tool dns-records.example.json >/dev/null
    docker compose run --rm infra python -m json.tool values.example/dns-records.local.json >/dev/null
    scripts/run-infra.sh ansible-playbook -i values/ansible/inventory/local.yml --syntax-check ansible/playbooks/site.yml
    docker compose run --rm infra ansible-lint ansible

# Review infrastructure changes using private values; writes tfplan for `just apply`
plan: check-values
    scripts/run-infra.sh tofu init
    scripts/run-infra.sh tofu plan -var-file=values/terraform.tfvars -out=tfplan
    scripts/run-infra.sh tofu show tfplan

# Apply reviewed infrastructure plan, then configure services with Ansible
apply: check-values
    test -f tfplan
    scripts/run-infra.sh tofu apply tfplan
    rm -f tfplan *.tfplan
    scripts/run-infra.sh ansible-playbook -i values/ansible/inventory/local.yml ansible/playbooks/site.yml
