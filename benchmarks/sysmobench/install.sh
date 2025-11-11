#!/bin/bash

set -e

echo "==> Installing SysMoBench dependencies..."

# Create virtual environment (following example_bench pattern)
if [ -d ".venv" ]; then
    echo "==> .venv already exists, skipping creation."
else
    echo "==> Creating .venv directory..."
    python3 -m venv .venv
    source .venv/bin/activate

    # Install SysMoBench dependencies
    pip install -r sysmobench_core/requirements.txt

    # Install SDK dependencies (only litellm is needed for LLM calls)
    pip install litellm

    # Download TLA+ tools
    echo "==> Downloading TLA+ tools..."
    python3 sysmobench_core/tla_eval/setup_cli.py

    deactivate
fi

echo "==> SysMoBench environment is set up successfully."
