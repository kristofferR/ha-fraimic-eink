#!/bin/sh
# Install beside download_firmware.py, outside a disposable Git worktree.
set -u
umask 077
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 1
FIRMWARE_DIR="$HOME/Library/Application Support/Fraimic/firmware"
KEY_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/fraimic"
status=0

# Always ask for the available offer. Exact content hashes suppress duplicates,
# while a replacement binary published under the same version is still saved.
for model in standard large; do
    uv run --offline --no-project "$SCRIPT_DIR/download_firmware.py" \
        --device-key-file "$KEY_DIR/$model.key" \
        --model "$model" --current-version 0.0.1 \
        --output-dir "$FIRMWARE_DIR" --notify || status=1
done
exit "$status"
