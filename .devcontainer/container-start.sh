#!/bin/bash

set -euo pipefail  # Exit on error, undefined vars, and pipeline failures
IFS=$'\n\t'       # Stricter word splitting

# A freshly-created Docker volume whose mountpoint does not exist in the image comes up
# root-owned, so every volume target below has to be handed back to node before use.
mkdir -p /workspace/.venv /home/node/.cache/uv
chown -R node:node /workspace/.venv /home/node/.cache/uv /commandhistory /home/node/.claude
