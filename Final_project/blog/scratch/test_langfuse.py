#!/usr/bin/env python3
"""
Diagnostic and test script for Langfuse integration.

Project URL: https://jp.cloud.langfuse.com/project/cmw4ylhev0007ad0l7osbr6i3/traces

Usage:
    # 1. Via environment variables:
    export LANGFUSE_PUBLIC_KEY="pk-lf-..."
    export LANGFUSE_SECRET_KEY="sk-lf-..."
    python scratch/test_langfuse.py

    # 2. Or pass keys directly:
    python scratch/test_langfuse.py --public-key "pk-lf-..." --secret-key "sk-lf-..."
"""

import argparse
import os
import sys
import time

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'a_core.settings')

import django
django.setup()

from django.conf import settings
from langfuse import Langfuse


def main():
    parser = argparse.ArgumentParser(description="Test Langfuse Tracing for CheeseO")
    parser.add_argument("--public-key", default=None, help="Langfuse Public Key (pk-lf-...)")
    parser.add_argument("--secret-key", default=None, help="Langfuse Secret Key (sk-lf-...)")
    parser.add_argument("--host", default="https://jp.cloud.langfuse.com", help="Langfuse Host URL")
    args = parser.parse_args()

    pub_key = args.public_key or getattr(settings, 'LANGFUSE_PUBLIC_KEY', '') or os.environ.get('LANGFUSE_PUBLIC_KEY', '')
    sec_key = args.secret_key or getattr(settings, 'LANGFUSE_SECRET_KEY', '') or os.environ.get('LANGFUSE_SECRET_KEY', '')
    host = args.host or getattr(settings, 'LANGFUSE_HOST', 'https://jp.cloud.langfuse.com')

    print("=" * 65)
    print("🔭 CheeseO Langfuse Observability Integration Tester")
    print("=" * 65)
    print(f"Target Host: {host}")
    print(f"Project URL: https://jp.cloud.langfuse.com/project/cmw4ylhev0007ad0l7osbr6i3/traces")
    print(f"Public Key : {pub_key[:10] + '...' if pub_key else '[NOT SET]'}")
    print(f"Secret Key : {sec_key[:10] + '...' if sec_key else '[NOT SET]'}")

    if not pub_key or not sec_key:
        print("\n❌ KEYS MISSING:")
        print("   Please provide your Langfuse API Keys:")
        print("   1. Open: https://jp.cloud.langfuse.com/project/cmw4ylhev0007ad0l7osbr6i3/settings")
        print("   2. Generate API Keys (Public Key & Secret Key)")
        print("   3. Run:")
        print("      python scratch/test_langfuse.py --public-key 'pk-lf-...' --secret-key 'sk-lf-...'")
        print("      or add to your .env file:")
        print("      LANGFUSE_PUBLIC_KEY=pk-lf-...")
        print("      LANGFUSE_SECRET_KEY=sk-lf-...")
        print("      LANGFUSE_HOST=https://jp.cloud.langfuse.com")
        sys.exit(1)

    print("\n[1/3] Initializing Langfuse client...")
    client = Langfuse(public_key=pub_key, secret_key=sec_key, host=host)

    test_query = "What is the difference between Git rebase and merge?"
    print(f"[2/3] Generating synthetic Agent Trace with spans for: \"{test_query}\"...")

    t0 = time.time()
    with client.start_as_current_observation(
        name="CheeseO-Agent",
        as_type="agent",
        input={"query": test_query},
        metadata={"project": "CheeseO", "version": "Sprint-3", "test_run": True},
    ) as agent_obs:
        with client.start_as_current_observation(
            name="Multi-Strategy-Retrieval",
            as_type="retriever",
            input={"query": test_query},
            metadata={"lexical": True, "vector": True},
        ) as ret_obs:
            time.sleep(0.1)
            ret_obs.update(output={"keyword_hits": 2, "chunk_hits": 4, "vector_hits": 3})

        with client.start_as_current_observation(
            name="CheeseO-LLM",
            as_type="generation",
            model="llama-3.3-70b-instruct-fp8-fast",
            input={"prompt": test_query},
            metadata={"temperature": 0.1, "max_tokens": 900},
        ) as gen_obs:
            time.sleep(0.2)
            gen_obs.update(output="Git rebase rewrites commit history into a linear line, whereas merge preserves original commit topology.")

        agent_obs.update(output="Finished CheeseO diagnosis successfully.")

    print("[3/3] Flushing traces to https://jp.cloud.langfuse.com...")
    client.flush()
    elapsed = time.time() - t0

    print("\n" + "=" * 65)
    print(f"🎉 SUCCESS ({elapsed:.2f}s)! Trace pushed to Langfuse!")
    print(f"👉 Open your project dashboard to view:")
    print(f"   https://jp.cloud.langfuse.com/project/cmw4ylhev0007ad0l7osbr6i3/traces")
    print("=" * 65)


if __name__ == '__main__':
    main()
