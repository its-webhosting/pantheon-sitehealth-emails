#!/bin/bash

set -euo pipefail  # Exit on error, undefined vars, and pipeline failures
IFS=$'\n\t'       # Stricter word splitting

mkdir -p /workspace/.venv/.cache
chown -R node:node /workspace/.venv /commandhistory /home/node/.claude
