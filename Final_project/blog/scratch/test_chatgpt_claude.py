#!/usr/bin/env python3
"""
Test script for ChatGPT (OpenAI) and Claude (Anthropic) integrations.

Usage:
    # 1. Using environment variables:
    export OPENAI_API_KEY="sk-..."
    export ANTHROPIC_API_KEY="sk-ant-..."
    python scratch/test_chatgpt_claude.py

    # 2. Or passing keys directly:
    python scratch/test_chatgpt_claude.py --openai-key "sk-..." --claude-key "sk-ant-..."

    # 3. Test only one provider:
    python scratch/test_chatgpt_claude.py --only-chatgpt
    python scratch/test_chatgpt_claude.py --only-claude

    # 4. Custom prompt:
    python scratch/test_chatgpt_claude.py --prompt "什么是 Docker 的多阶段构建？"
"""

import argparse
import os
import sys
import time

# Ensure blog repo is in sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'a_core.settings')

import django
django.setup()

from django.conf import settings
from a_agent.services.llm import generate_answer, get_llm_info


def test_chatgpt(api_key: str | None, model: str, prompt: str, base_url: str | None = None):
    print("\n" + "=" * 60)
    print(f"🤖 [TESTING CHATGPT / OPENAI] Model: {model}")
    print("=" * 60)

    key = api_key or getattr(settings, 'AGENT_OPENAI_API_KEY', '') or os.environ.get('OPENAI_API_KEY', '')
    if not key:
        print("❌ SKIPPED: OPENAI_API_KEY is not set.")
        print("   Set it via: export OPENAI_API_KEY='sk-...' or pass --openai-key")
        return False

    # Temporarily override settings for test
    orig_key = getattr(settings, 'AGENT_OPENAI_API_KEY', '')
    orig_base = getattr(settings, 'AGENT_OPENAI_BASE_URL', '')
    settings.AGENT_OPENAI_API_KEY = key
    if base_url:
        settings.AGENT_OPENAI_BASE_URL = base_url

    system_prompt = "You are CheeseO, a helpful programming co-pilot. Answer clearly in Simplified Chinese (简体中文)."

    print(f"Sending prompt: \"{prompt}\" ...")
    t0 = time.time()
    try:
        reply = generate_answer(system_prompt, prompt, model=model)
        elapsed = time.time() - t0
        print(f"✅ SUCCESS ({elapsed:.2f}s):\n")
        print(reply)
        return True
    except Exception as exc:
        print(f"❌ FAILED ({time.time() - t0:.2f}s): {exc}")
        return False
    finally:
        settings.AGENT_OPENAI_API_KEY = orig_key
        settings.AGENT_OPENAI_BASE_URL = orig_base


def test_claude(api_key: str | None, model: str, prompt: str, base_url: str | None = None):
    print("\n" + "=" * 60)
    print(f"🧠 [TESTING CLAUDE / ANTHROPIC] Model: {model}")
    print("=" * 60)

    key = api_key or getattr(settings, 'ANTHROPIC_API_KEY', '') or os.environ.get('ANTHROPIC_API_KEY', '')
    if not key:
        print("❌ SKIPPED: ANTHROPIC_API_KEY is not set.")
        print("   Set it via: export ANTHROPIC_API_KEY='sk-ant-...' or pass --claude-key")
        return False

    # Temporarily override settings for test
    orig_key = getattr(settings, 'ANTHROPIC_API_KEY', '')
    orig_base = getattr(settings, 'AGENT_ANTHROPIC_BASE_URL', '')
    settings.ANTHROPIC_API_KEY = key
    if base_url:
        settings.AGENT_ANTHROPIC_BASE_URL = base_url

    system_prompt = "You are CheeseO, a helpful programming co-pilot. Answer clearly in Simplified Chinese (简体中文)."

    print(f"Sending prompt: \"{prompt}\" ...")
    t0 = time.time()
    try:
        reply = generate_answer(system_prompt, prompt, model=model)
        elapsed = time.time() - t0
        print(f"✅ SUCCESS ({elapsed:.2f}s):\n")
        print(reply)
        return True
    except Exception as exc:
        print(f"❌ FAILED ({time.time() - t0:.2f}s): {exc}")
        return False
    finally:
        settings.ANTHROPIC_API_KEY = orig_key
        settings.AGENT_ANTHROPIC_BASE_URL = orig_base


def main():
    parser = argparse.ArgumentParser(description="Test ChatGPT and Claude APIs in CheeseO")
    parser.add_argument("--openai-key", help="OpenAI API Key")
    parser.add_argument("--openai-model", default="gpt-4o-mini", help="OpenAI Model (default: gpt-4o-mini)")
    parser.add_argument("--openai-base-url", default=None, help="Custom OpenAI base_url (optional proxy)")
    parser.add_argument("--claude-key", help="Anthropic API Key")
    parser.add_argument("--claude-model", default="claude-3-5-sonnet-20241022", help="Claude Model (default: claude-3-5-sonnet-20241022)")
    parser.add_argument("--claude-base-url", default=None, help="Custom Anthropic base_url (optional proxy)")
    parser.add_argument("--prompt", default="Git 的 rebase 和 merge 有什么本质区别？用两句话概括。", help="Prompt to test")
    parser.add_argument("--only-chatgpt", action="store_true", help="Only test ChatGPT")
    parser.add_argument("--only-claude", action="store_true", help="Only test Claude")

    args = parser.parse_args()

    print("==================================================")
    print("🚀 CheeseO LLM Integration Diagnostic & Runner")
    print("==================================================")

    if not args.only_claude:
        test_chatgpt(args.openai_key, args.openai_model, args.prompt, args.openai_base_url)

    if not args.only_chatgpt:
        test_claude(args.claude_key, args.claude_model, args.prompt, args.claude_base_url)

    print("\n" + "=" * 60)
    print("🏁 Testing complete.")
    print("==================================================")


if __name__ == '__main__':
    main()
