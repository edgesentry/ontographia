#!/usr/bin/env bash
# Load Ontographia seed data into a running Neo4j container.
#
# Usage:
#   ./scripts/load_neo4j_seed.sh
#   ./scripts/load_neo4j_seed.sh path/to/custom.cypher
#
# Environment overrides:
#   NEO4J_CONTAINER_NAME  default: ontographia-neo4j
#   NEO4J_USER            default: neo4j
#   NEO4J_PASSWORD        default: ontographia
#   NEO4J_SEED_FILE       default: examples/neo4j/seed.cypher (repo-relative)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER_NAME="${NEO4J_CONTAINER_NAME:-ontographia-neo4j}"
USER="${NEO4J_USER:-neo4j}"
PASSWORD="${NEO4J_PASSWORD:-ontographia}"
SEED_FILE="${NEO4J_SEED_FILE:-${ROOT}/examples/neo4j/seed.cypher}"

for arg in "$@"; do
  case "$arg" in
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    -*)
      echo "unknown argument: $arg" >&2
      exit 1
      ;;
    *)
      if [[ -n "${CUSTOM_SEED:-}" ]]; then
        echo "too many arguments" >&2
        exit 1
      fi
      CUSTOM_SEED="$arg"
      ;;
  esac
done

if [[ -n "${CUSTOM_SEED:-}" ]]; then
  if [[ "$CUSTOM_SEED" = /* ]]; then
    SEED_FILE="$CUSTOM_SEED"
  else
    SEED_FILE="${ROOT}/${CUSTOM_SEED}"
  fi
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required but not installed" >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "docker daemon is not running (try: colima start)" >&2
  exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  echo "container is not running: $CONTAINER_NAME" >&2
  echo "Start it with: ./scripts/start_neo4j.sh" >&2
  exit 1
fi

if [[ ! -f "$SEED_FILE" ]]; then
  echo "seed file not found: $SEED_FILE" >&2
  exit 1
fi

echo "Loading ${SEED_FILE#"${ROOT}/"} into $CONTAINER_NAME"
docker exec -i "$CONTAINER_NAME" cypher-shell -u "$USER" -p "$PASSWORD" <"$SEED_FILE"

echo "Seed data loaded."
