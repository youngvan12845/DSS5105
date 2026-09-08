#!/usr/bin/env bash
# Pull the local LLM used by the Reading Assistant (Ollama).
# Install Ollama first: https://ollama.com/download
set -euo pipefail

cd "$(dirname "$0")/.."

MODEL="${OLLAMA_MODEL:-qwen2.5vl:7b}"

if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama is not installed."
  echo "Download: https://ollama.com/download"
  echo "Then re-run: ./scripts/setup_ollama.sh"
  exit 1
fi

echo "Pulling model: ${MODEL}"
ollama pull "${MODEL}"

echo "Pulling embedding model: nomic-embed-text"
ollama pull nomic-embed-text

echo ""
echo "Done. Ensure .env contains:"
echo "  AGENT_LLM_PROVIDER=ollama"
echo "  OLLAMA_MODEL=${MODEL}"
echo ""
echo "Optional for vector search:"
echo "  ollama pull nomic-embed-text"
echo "  python manage.py build_article_index --embed"
