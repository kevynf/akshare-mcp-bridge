#!/usr/bin/env bash
# Resolve the AKShare commit SHA for a released version.
#
# AKShare renamed its release tags from release-vX.Y.Z (through 1.20.0) to
# vX.Y.Z (from 1.20.1 on). Both conventions are tried so the documentation
# index is always built from the exact source of the pinned version; the
# commit SHA, not the tag name, keeps builds reproducible if a tag moves.
set -euo pipefail

if [[ "$#" -ne 1 ]]; then
    echo "usage: $0 <akshare-version>" >&2
    exit 2
fi

version="$1"

for tag in "v${version}" "release-v${version}"; do
    if sha="$(gh api "repos/akfamily/akshare/commits/${tag}" --jq .sha 2>/dev/null)" &&
        [[ -n "${sha}" ]]; then
        echo "${sha}"
        exit 0
    fi
done

echo "No AKShare tag matches version ${version} (tried v${version} and release-v${version})." >&2
exit 1
