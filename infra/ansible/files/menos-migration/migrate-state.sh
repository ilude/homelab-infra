#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
    printf 'Usage: %s <archive> <stamp> <expected-archive-sha256>\n' "$0" >&2
    exit 2
fi

archive="$1"
stamp="$2"
expected_archive_sha256="$3"
base_dir=/srv/onramp/menos
incoming_root="${base_dir}/migration/incoming"
snapshot="${incoming_root}/${stamp}"
runtime_dir="${base_dir}/migration/runtime-${stamp}"
compose=(podman-compose -f "${base_dir}/compose.yaml")
source_container="menos-migration-source-${stamp,,}"
source_container="${source_container//[^a-z0-9_.-]/-}"
api_stopped=false
source_started=false

# Invoked by the EXIT trap.
# shellcheck disable=SC2329
cleanup() {
    if [[ "${source_started}" == true ]]; then
        podman rm -f "${source_container}" >/dev/null 2>&1 || true
    fi
    rm -rf -- "${runtime_dir}"
    if [[ "${api_stopped}" == true ]]; then
        printf 'Migration failed with the new API stopped; restore the verified empty baseline.\n' >&2
    fi
}
trap cleanup EXIT

[[ "${stamp}" =~ ^[0-9]{8}T[0-9]{6}Z$ ]] || {
    printf 'Invalid migration stamp\n' >&2
    exit 2
}
[[ -f "${archive}" ]] || {
    printf 'Migration archive is missing\n' >&2
    exit 1
}
actual_archive_sha256="$(sha256sum "${archive}" | awk '{print $1}')"
[[ "${actual_archive_sha256}" == "${expected_archive_sha256}" ]] || {
    printf 'Migration archive checksum mismatch\n' >&2
    exit 1
}
[[ ! -e "${snapshot}" ]] || {
    printf 'Migration snapshot is already extracted\n' >&2
    exit 1
}

mkdir -p "${incoming_root}" "${runtime_dir}"
umask 077
tar -xzf "${archive}" -C "${incoming_root}"
[[ -s "${snapshot}/database.surql" ]]
[[ -f "${snapshot}/migration-manifest.json" ]]
(
    cd "${snapshot}"
    sha256sum -c SHA256SUMS >/dev/null
)

python3 - "${base_dir}/.env" "${snapshot}/migration-manifest.json" "${runtime_dir}" <<'PY'
import json
import secrets
import sys
from pathlib import Path

service_env, manifest_path, runtime_path = map(Path, sys.argv[1:])
values = {}
for raw in service_env.read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    values[key.strip()] = value.strip().strip('"').strip("'")
required = [
    "SURREALDB_PASSWORD",
    "SURREALDB_NAMESPACE",
    "SURREALDB_DATABASE",
    "S3_ACCESS_KEY",
    "S3_SECRET_KEY",
    "S3_BUCKET",
    "S3_REGION",
]
missing = [key for key in required if not values.get(key)]
if missing:
    raise SystemExit("missing required service environment entries: " + ", ".join(missing))
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
source_user = "migration-" + secrets.token_hex(8)
source_password = secrets.token_urlsafe(32)
runtime_path.mkdir(parents=True, exist_ok=True)
(runtime_path / "source-minio.env").write_text(
    f"MINIO_ROOT_USER={source_user}\nMINIO_ROOT_PASSWORD={source_password}\n",
    encoding="utf-8",
)
(runtime_path / "surreal.env").write_text(
    "\n".join(
        [
            "SURREAL_USER=root",
            f"SURREAL_PASS={values['SURREALDB_PASSWORD']}",  # public-safety: allow-secret
            f"SURREAL_NAMESPACE={values['SURREALDB_NAMESPACE']}",
            f"SURREAL_DATABASE={values['SURREALDB_DATABASE']}",
        ]
    )
    + "\n",
    encoding="utf-8",
)
minio = manifest["minio"]
(runtime_path / "migration.env").write_text(
    "\n".join(
        [
            "SOURCE_S3_ENDPOINT=source-minio:9000",
            f"SOURCE_S3_ACCESS_KEY={source_user}",
            f"SOURCE_S3_SECRET_KEY={source_password}",  # public-safety: allow-secret
            "SOURCE_S3_REGION=us-east-1",
            "DEST_S3_ENDPOINT=minio:9000",
            f"DEST_S3_ACCESS_KEY={values['S3_ACCESS_KEY']}",
            f"DEST_S3_SECRET_KEY={values['S3_SECRET_KEY']}",  # public-safety: allow-secret
            f"DEST_S3_REGION={values['S3_REGION']}",
            f"S3_BUCKET={values['S3_BUCKET']}",
            f"EXPECTED_S3_OBJECT_COUNT={minio['object_count']}",
            f"EXPECTED_S3_TOTAL_BYTES={minio['total_bytes']}",
            f"EXPECTED_S3_KEY_LIST_SHA256={minio['key_list_sha256']}",
        ]
    )
    + "\n",
    encoding="utf-8",
)
for path in runtime_path.iterdir():
    path.chmod(0o600)
PY

expected_relationships="$(
    python3 - "${snapshot}/migration-manifest.json" <<'PY'
import json
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(manifest["record_counts"]["content_entity"])
PY
)"
python3 "${base_dir}/migration/bin/normalize-surreal-export.py" \
    "${snapshot}/database.surql" \
    "${runtime_dir}/database.surql" \
    --expected-relationships "${expected_relationships}"
chmod 0600 "${runtime_dir}/database.surql"

authorized_keys_sha256="$(sha256sum "${base_dir}/authorized_keys" | awk '{print $1}')"
authorized_key_count="$(grep -Ec '^ssh-ed25519 [A-Za-z0-9+/=]+( .*)?$' "${base_dir}/authorized_keys")"
[[ "${authorized_key_count}" -eq 1 ]] || {
    printf 'Managed authorized_keys must contain exactly one approved principal\n' >&2
    exit 1
}

"${compose[@]}" stop menos-api
api_stopped=true

podman cp "${runtime_dir}/database.surql" menos_surrealdb_1:/tmp/migration.surql
podman exec --env-file "${runtime_dir}/surreal.env" menos_surrealdb_1 \
    /surreal import --endpoint http://localhost:8000 /tmp/migration.surql

minio_image="$(podman inspect menos_minio_1 | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["ImageName"])')"
api_image="$(podman inspect menos_menos-api_1 | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["ImageName"])')"
network="$(podman inspect menos_minio_1 | python3 -c 'import json,sys; print(next(iter(json.load(sys.stdin)[0]["NetworkSettings"]["Networks"])))')"
[[ -n "${minio_image}" && -n "${api_image}" && -n "${network}" ]]
if podman container exists "${source_container}"; then
    printf 'Temporary migration source container already exists\n' >&2
    exit 1
fi
podman run -d \
    --name "${source_container}" \
    --network "${network}" \
    --network-alias source-minio \
    --env-file "${runtime_dir}/source-minio.env" \
    --volume "${snapshot}/minio:/data:Z" \
    "${minio_image}" server /data >/dev/null
source_started=true

podman run --rm \
    --network "${network}" \
    --env-file "${runtime_dir}/migration.env" \
    --volume "${base_dir}/migration/bin/migrate-s3.py:/migration/migrate-s3.py:ro,Z" \
    --entrypoint /app/.venv/bin/python \
    "${api_image}" /migration/migrate-s3.py

counts_json="$(
    printf '%s\n' 'RETURN { content: count((SELECT id FROM content)), chunk: count((SELECT id FROM chunk)), link: count((SELECT id FROM link)), content_entity: count((SELECT id FROM content_entity)), entity: count((SELECT id FROM entity)), pipeline_job: count((SELECT id FROM pipeline_job)), llm_usage: count((SELECT id FROM llm_usage)), tag_alias: count((SELECT id FROM tag_alias)) };' |
        podman exec -i --env-file "${runtime_dir}/surreal.env" menos_surrealdb_1 \
            /surreal sql --endpoint http://localhost:8000 --json --hide-welcome
)"
python3 - "${snapshot}/migration-manifest.json" "${counts_json}" <<'PY'
import json
import sys
from pathlib import Path

expected = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["record_counts"]
actual = json.loads(sys.argv[2])[0]
if actual != expected:
    raise SystemExit(f"record count mismatch: {actual} != {expected}")
print("surreal_record_counts_verified=true")
PY

index_info="$(
    printf '%s\n' 'INFO FOR TABLE chunk;' |
        podman exec -i --env-file "${runtime_dir}/surreal.env" menos_surrealdb_1 \
            /surreal sql --endpoint http://localhost:8000 --json --hide-welcome
)"
grep -q 'idx_chunk_embedding' <<<"${index_info}"
grep -q 'MTREE DIMENSION 1024 DIST COSINE' <<<"${index_info}"
echo 'surreal_mtree_verified=true'

[[ "$(sha256sum "${base_dir}/authorized_keys" | awk '{print $1}')" == "${authorized_keys_sha256}" ]]
[[ "$(grep -Ec '^ssh-ed25519 [A-Za-z0-9+/=]+( .*)?$' "${base_dir}/authorized_keys")" -eq 1 ]]
echo 'authorized_keys_unchanged=true'

podman rm -f "${source_container}" >/dev/null
source_started=false
"${compose[@]}" start menos-api
api_stopped=false
for _attempt in $(seq 1 60); do
    if curl --fail --silent http://127.0.0.1:8000/health >/dev/null &&
        curl --fail --silent http://127.0.0.1:8000/ready | grep -q '"status":"ready"'; then
        echo 'menos_post_import_ready=true'
        exit 0
    fi
    sleep 10
done
printf 'Menos did not become ready after import\n' >&2
exit 1
