#!/usr/bin/env bash
# Start the blog locally (after .env and database are set up).
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -d .venv ]]; then
  echo "Run first: python3.10 -m venv .venv && pip install -r requirements.txt"
  exit 1
fi

if [[ ! -f .env ]]; then
  echo "Copy .env.example to .env and set POSTGRES_PASSWORD"
  exit 1
fi

.venv/bin/python manage.py runserver
