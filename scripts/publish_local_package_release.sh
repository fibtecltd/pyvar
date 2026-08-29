#!/usr/bin/env bash
#
# scripts/publish_local_package_release.sh — publish the built pyvar-local
# Docker image tarball as a GitHub Release asset.
#
# Called by the local-package CodeBuild pipeline's Publish stage (see
# pyvar-cdk/stacks/local_package_stack.py) -- not meant to be run by hand in
# normal operation, though it works standalone given the same env vars.
# Uses the GitHub REST API directly via curl, not the `gh` CLI -- `gh` is
# not guaranteed present on the CodeBuild image this pipeline uses.
#
# Required env:
#   GITHUB_TOKEN   -- a token with release:write on fibtecltd/pyvar, from
#                     Secrets Manager (pyvar/github-token) in the pipeline
#   TAG            -- release tag, e.g. pyvar-local-v0.1.0-<short-sha>
#   ASSET_PATH     -- path to the built .tar.gz to upload
#
# GitHub Releases replaces same-named assets by delete-then-reupload, not
# an atomic overwrite -- if this script is interrupted between those two
# steps, re-running it completes the upload (the delete is a no-op once the
# old asset is already gone). A release tagged $TAG is created as a
# prerelease if it doesn't already exist -- see the request body below for
# why, and flip that flag deliberately once this pipeline has a track record.

set -euo pipefail

: "${GITHUB_TOKEN:?GITHUB_TOKEN is required}"
: "${TAG:?TAG is required}"
: "${ASSET_PATH:?ASSET_PATH is required}"

if [[ ! -f "$ASSET_PATH" ]]; then
  echo "ERROR: ASSET_PATH '${ASSET_PATH}' does not exist." >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required." >&2
  exit 1
fi

REPO="fibtecltd/pyvar"
API="https://api.github.com"
ASSET_NAME=$(basename "$ASSET_PATH")

auth_header=(-H "Authorization: Bearer ${GITHUB_TOKEN}" -H "Accept: application/vnd.github+json")

fail_on_error() {
  # GitHub's API returns 200 with a JSON body even on some error paths in
  # this script's flow (e.g. querying assets on a fresh release) -- but a
  # genuine failure response always carries a top-level "message" field.
  # Centralised here so every call site checks the same way rather than
  # trusting curl's exit code alone (curl -sS does not fail the shell on a
  # 4xx/5xx HTTP status without --fail, which this script deliberately
  # avoids elsewhere so it can inspect the body first).
  local body="$1" context="$2"
  local message
  message=$(echo "$body" | jq -r '.message // empty')
  if [[ -n "$message" && "$message" != "null" ]]; then
    echo "ERROR (${context}): ${message}" >&2
    exit 1
  fi
}

echo "Looking for an existing release tagged '${TAG}'..." >&2
lookup=$(curl -sS "${auth_header[@]}" "${API}/repos/${REPO}/releases/tags/${TAG}")
existing_id=$(echo "$lookup" | jq -r '.id // empty')

if [[ -n "$existing_id" ]]; then
  release_id="$existing_id"
  echo "Found existing release id ${release_id} -- will add/replace the asset." >&2
else
  echo "Creating release '${TAG}'..." >&2
  create_body=$(jq -n --arg tag "$TAG" --arg name "pyvar Local ${TAG}" '{
    tag_name: $tag,
    name: $name,
    body: "Automated pyvar Local build. See docs/proposals/pyvar-local-package-proposal.docx and docs/p11-pre-launch-hardening.md §2 for what this is and how it was built.",
    draft: false,
    prerelease: true
  }')
  create_resp=$(curl -sS "${auth_header[@]}" -X POST "${API}/repos/${REPO}/releases" -d "$create_body")
  fail_on_error "$create_resp" "create release"
  release_id=$(echo "$create_resp" | jq -r '.id')
fi

# If an asset with this name already exists on the release, remove it first
# -- the upload endpoint returns 422 on a name collision rather than
# replacing in place.
assets_resp=$(curl -sS "${auth_header[@]}" "${API}/repos/${REPO}/releases/${release_id}/assets")
existing_asset_id=$(echo "$assets_resp" | jq -r --arg name "$ASSET_NAME" '.[] | select(.name == $name) | .id')
if [[ -n "$existing_asset_id" ]]; then
  echo "Removing existing asset '${ASSET_NAME}' (id ${existing_asset_id})..." >&2
  curl -sS "${auth_header[@]}" -X DELETE "${API}/repos/${REPO}/releases/assets/${existing_asset_id}" >/dev/null
fi

echo "Uploading ${ASSET_PATH} as '${ASSET_NAME}'..." >&2
upload_resp=$(curl -sS "${auth_header[@]}" -H "Content-Type: application/gzip" \
  --data-binary @"${ASSET_PATH}" \
  "https://uploads.github.com/repos/${REPO}/releases/${release_id}/assets?name=${ASSET_NAME}")
fail_on_error "$upload_resp" "upload asset"

download_url=$(echo "$upload_resp" | jq -r '.browser_download_url')
echo "Published: ${download_url}" >&2
echo "$download_url"
