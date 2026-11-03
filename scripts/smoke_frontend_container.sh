#!/usr/bin/env bash
# Run the real image entrypoint and Docker health check, without provider access.
set -euo pipefail

image="${1:?Usage: bash scripts/smoke_frontend_container.sh IMAGE}"
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

container_id=$(docker run --detach --network none --env ANTHROPIC_API_KEY= --env STREAMLIT_BROWSER_GATHER_USAGE_STATS=false "$image")
healthy=false
for attempt in {1..60}; do
    state=$(docker inspect --format '{{.State.Status}} {{.State.Health.Status}}' "$container_id")
    if [[ "$state" == "running healthy" ]]; then
        healthy=true
        break
    fi
    if [[ "$state" != "running starting" ]]; then
        echo "Frontend container failed before becoming healthy: $state" >&2
        exit 1
    fi
    sleep 2
done
if [[ "$healthy" != true ]]; then
    echo "Frontend container did not become healthy within 120 seconds" >&2
    exit 1
fi

docker exec -i "$container_id" python - <<'PYTHON'
import os
from urllib.request import urlopen

assert not os.environ.get("ANTHROPIC_API_KEY"), "Smoke test must not use credentials"
with urlopen("http://localhost:8501/_stcore/health", timeout=5) as response:
    assert response.status == 200
    assert response.read().decode().strip() == "ok"
with urlopen("http://localhost:8501/", timeout=5) as response:
    assert response.status == 200
    assert "Streamlit" in response.read().decode()
print("Frontend entrypoint and HTTP health passed")
PYTHON

# Exercise the packaged app, not source mounted from the host.
docker exec "$container_id" python -m pytest -q tests/test_streamlit_demo.py
