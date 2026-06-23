#!/usr/bin/env bash
# Installs a pre-commit hook that auto-refreshes the self-knowledge doc.
# Idempotent — running twice won't duplicate the hook body.
# Use --force to overwrite a foreign hook.

set -euo pipefail

REPO_ROOT="$(git -C "$(dirname "$0")/.." rev-parse --show-toplevel)"
HOOK_FILE="$REPO_ROOT/.git/hooks/pre-commit"
MARKER="# [self-knowledge-hook]"

if [ -f "$HOOK_FILE" ]; then
    if grep -q "self-knowledge-hook" "$HOOK_FILE" 2>/dev/null; then
        echo "Self-knowledge hook already installed. Nothing to do."
        exit 0
    fi
    if [ "${1:-}" != "--force" ]; then
        echo "A pre-commit hook already exists at $HOOK_FILE"
        echo "Use --force to append the self-knowledge hook to it."
        exit 1
    fi
    echo "Appending self-knowledge hook to existing pre-commit..."
fi

cat >> "$HOOK_FILE" << 'HOOK'

# [self-knowledge-hook]
# Auto-refresh the R.A.M.B.O self-knowledge doc on every commit.
BACKEND_DIR="$(git rev-parse --show-toplevel)/rambo-backend"
if [ -d "$BACKEND_DIR/self_knowledge" ]; then
    cd "$BACKEND_DIR"
    python -m self_knowledge --refresh 2>/dev/null || true
    DOC="context/self/rambo.md"
    if [ -f "$DOC" ]; then
        git add "$DOC"
    fi
fi
# [/self-knowledge-hook]
HOOK

chmod +x "$HOOK_FILE"
echo "Self-knowledge pre-commit hook installed."
