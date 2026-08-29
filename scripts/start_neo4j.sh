#!/usr/bin/env bash
# Start (or create) the Ontographia Neo4j dev container.
#
# Usage:
#   ./scripts/start_neo4j.sh           # start container and wait until ready
#   ./scripts/start_neo4j.sh --seed    # also load seed via scripts/load_neo4j_seed.sh
#
# Environment overrides:
#   NEO4J_CONTAINER_NAME  default: ontographia-neo4j
#   NEO4J_IMAGE           default: neo4j:2025.06
#   NEO4J_HTTP_PORT       default: 7474
#   NEO4J_BOLT_PORT       default: 7687
#   NEO4J_USER            default: neo4j
#   NEO4J_PASSWORD        default: ontographia

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER_NAME="${NEO4J_CONTAINER_NAME:-ontographia-neo4j}"
IMAGE="${NEO4J_IMAGE:-neo4j:2025.06}"
HTTP_PORT="${NEO4J_HTTP_PORT:-7474}"
BOLT_PORT="${NEO4J_BOLT_PORT:-7687}"
USER="${NEO4J_USER:-neo4j}"
PASSWORD="${NEO4J_PASSWORD:-ontographia}"
LOAD_SEED=0

for arg in "$@"; do
  case "$arg" in
    --seed) LOAD_SEED=1 ;;
    -h|--help)
      sed -n '2,14p' "$0"
      exit 0
      ;;
    *)
      echo "unknown argument: $arg" >&2
      exit 1
      ;;
  esac
done

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required but not installed" >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "docker daemon is not running (try: colima start)" >&2
  exit 1
fi

if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  echo "Starting existing container: $CONTAINER_NAME"
  docker start "$CONTAINER_NAME" >/dev/null
else
  echo "Creating container: $CONTAINER_NAME ($IMAGE)"
  docker run -d \
    --name "$CONTAINER_NAME" \
    -p "${HTTP_PORT}:7474" \
    -p "${BOLT_PORT}:7687" \
    -e "NEO4J_AUTH=${USER}/${PASSWORD}" \
    "$IMAGE" >/dev/null
fi

echo "Waiting for Neo4j to accept connections..."
ready=0
for _ in $(seq 1 40); do
  if docker exec "$CONTAINER_NAME" cypher-shell -u "$USER" -p "$PASSWORD" "RETURN 1" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 3
done

if [[ "$ready" -ne 1 ]]; then
  echo "Neo4j did not become ready in time" >&2
  exit 1
fi

if [[ "$LOAD_SEED" -eq 1 ]]; then
  "${ROOT}/scripts/load_neo4j_seed.sh"
fi

cat <<EOF

Neo4j is ready.

  Container : $CONTAINER_NAME
  Browser   : http://localhost:${HTTP_PORT}
  Bolt      : bolt://localhost:${BOLT_PORT}
  User      : $USER
  Password  : $PASSWORD

Load seed (if not done): ./scripts/load_neo4j_seed.sh
Run demo query         : NEO4J_URI=bolt://localhost:${BOLT_PORT} NEO4J_PASSWORD=$PASSWORD \\
                         python examples/run_neo4j_demo.py --execute
EOF
