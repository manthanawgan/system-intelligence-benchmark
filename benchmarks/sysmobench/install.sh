#!/bin/bash

set -e

echo "==> Installing SysMoBench dependencies..."

# Try to create virtual environment, but continue if it fails
if [ ! -d ".venv" ]; then
    if python3 -m venv .venv 2>/dev/null; then
        echo "Virtual environment created"
        USE_VENV=1
    else
        echo "Warning: Could not create virtual environment, installing globally"
        USE_VENV=0
    fi
else
    USE_VENV=1
fi

if [ $USE_VENV -eq 1 ]; then
    source .venv/bin/activate
fi

# Install SysMoBench dependencies
pip install -r sysmobench_core/requirements.txt --user 2>/dev/null || pip install -r sysmobench_core/requirements.txt

# Install SDK dependencies
pip install sentence-transformers scikit-learn requests azure-identity litellm --user 2>/dev/null || pip install sentence-transformers scikit-learn requests azure-identity litellm

# Download TLA+ tools
echo "==> Downloading TLA+ tools..."
python3 sysmobench_core/tla_eval/setup_cli.py

echo "==> Installation complete!"

if [ $USE_VENV -eq 1 ]; then
    deactivate
fi
