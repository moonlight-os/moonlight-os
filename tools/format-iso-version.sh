#!/usr/bin/env bash
set -euo pipefail

[[ "$#" -eq 1 ]] || { echo "usage: $0 MLOS_VERSION" >&2; exit 2; }

version="${1#v}"
version="${version//\~/-}"
version="${version//:/-}"
[[ "$version" =~ ^[0-9][0-9A-Za-z.+_-]*$ ]] \
	|| { echo "MLOS_VERSION cannot be represented safely in an ISO filename: $1" >&2; exit 2; }

printf '%s\n' "$version"
