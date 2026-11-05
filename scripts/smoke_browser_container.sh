#!/usr/bin/env bash
# Bind only to loopback; never mount host source or pass provider credentials.
set -euo pipefail
image="${1:?Usage: bash scripts/smoke_browser_container.sh IMAGE}"
container_id=""
cleanup() {
    result=$?
    if [[ -n "$container_id" ]]; then
        if (( result != 0 )); then
            docker logs "$container_id" || true
        fi
        docker rm --force "$container_id" >/dev/null || true
    fi
    exit "$result"
}
trap cleanup EXIT
container_id=$(docker run --detach --publish 127.0.0.1::8501 --env ANTHROPIC_API_KEY= --env STREAMLIT_BROWSER_GATHER_USAGE_STATS=false "$image")
address=$(docker port "$container_id" 8501/tcp)
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
    echo "Frontend did not become healthy within 120 seconds" >&2
    exit 1
fi
python scripts/check_demo_browser.py "http://$address"
