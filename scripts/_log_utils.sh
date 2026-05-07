#!/usr/bin/env bash
# _log_utils.sh — Shared log-session helpers for all demo scripts.
# Source this file; then call: init_session_log_dir "<script-name>"
#
# Result:
#   LOG_DIR  — set to the new timestamped session directory
#   A "latest" symlink is created/updated in .dev-runtime/logs/
#   Old session directories beyond KEEP_SESSIONS are auto-deleted.
#
# Environment:
#   KEEP_SESSIONS  — number of past sessions to retain (default: 5)

# How many past sessions to keep (oldest are pruned). Override via env.
KEEP_SESSIONS="${KEEP_SESSIONS:-5}"

init_session_log_dir() {
    local script_name="${1:-session}"
    local logs_base="${ROOT_DIR}/.dev-runtime/logs"
    local ts
    ts="$(date +%Y%m%d-%H%M%S)"
    LOG_DIR="${logs_base}/${script_name}-${ts}"
    mkdir -p "${LOG_DIR}"

    # One-time migration: move any legacy flat *.log files into an archive dir
    _migrate_legacy_logs "${logs_base}"

    # Update "latest" symlink (absolute path for clarity)
    ln -sfn "${LOG_DIR}" "${logs_base}/latest"

    # Prune oldest session directories, keeping KEEP_SESSIONS newest
    _prune_old_sessions "${logs_base}"
}

# Move old flat *.log files (pre-session system) to archive-legacy/ once.
_migrate_legacy_logs() {
    local logs_base="$1"
    local archive="${logs_base}/archive-legacy"
    local found_any=false
    while IFS= read -r f; do
        found_any=true
        break
    done < <(find "${logs_base}" -maxdepth 1 -mindepth 1 -name "*.log" -type f 2>/dev/null)
    if [[ "${found_any}" == "true" ]]; then
        mkdir -p "${archive}"
        find "${logs_base}" -maxdepth 1 -mindepth 1 -name "*.log" -type f \
            -exec mv -n {} "${archive}/" \;
    fi
}

_prune_old_sessions() {
    local logs_base="$1"
    # Collect all session dirs (not symlinks, not "latest", not "archive-legacy")
    local sessions=()
    while IFS= read -r d; do
        sessions+=("$d")
    done < <(find "${logs_base}" -maxdepth 1 -mindepth 1 -type d \
        -not -name "latest" -not -name "archive-legacy" | sort)

    local total="${#sessions[@]}"
    if (( total > KEEP_SESSIONS )); then
        local to_remove=$(( total - KEEP_SESSIONS ))
        for (( i = 0; i < to_remove; i++ )); do
            rm -rf "${sessions[$i]}"
        done
    fi
}
