#!/usr/bin/env bash
# Run the real image entrypoint and Docker health check, without provider access.
set -euo pipefail

image="${1:?Usage: bash scripts/smoke_api_container.sh IMAGE}"
container_id=""
cleanup() {
    result=$?
    if [[ -n "$container_id" ]]; then
        if (( result != 0 )); then
            docker logs "$container_id" || true
            docker inspect --format '{{json .State}}' "$container_id" || true
        fi
        docker rm --force "$container_id" >/dev/null || true
    fi
    exit "$result"
}
trap cleanup EXIT

container_id=$(docker run --detach --network none --env ANTHROPIC_API_KEY= "$image")
healthy=false
for attempt in {1..60}; do
    state=$(docker inspect --format '{{.State.Status}} {{.State.Health.Status}}' "$container_id")
    if [[ "$state" == "running healthy" ]]; then
        healthy=true
        break
    fi
    if [[ "$state" != "running starting" ]]; then
        echo "API container failed before becoming healthy: $state" >&2
        exit 1
    fi
    sleep 2
done
if [[ "$healthy" != true ]]; then
    echo "API container did not become healthy within 120 seconds" >&2
    exit 1
fi

docker exec -i "$container_id" python - <<'PY'
import json
import os
from urllib.request import urlopen

assert not os.environ.get("ANTHROPIC_API_KEY"), "Smoke test must not use credentials"

def get(path):
    with urlopen("http://localhost:8000" + path, timeout=5) as response:
        assert response.status == 200
        return json.load(response)

for _ in range(3):
    assert get("/")["name"] == "AgentFlow v2.0 API"
diagnostics = get("/health")
assert diagnostics["status"] == "degraded", diagnostics
assert diagnostics["anthropic_connected"] is False, diagnostics
assert len(diagnostics["agents_available"]) == 6, diagnostics
print("API image started, Docker liveness passed, and missing-provider diagnostics passed")
PY
