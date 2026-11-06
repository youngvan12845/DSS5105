import os
import sys
import time
import subprocess
import django

sys.path.insert(0, '/Users/huangrenqian/Projects/DSS5105/Final_project/blog')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'a_core.settings')
django.setup()

from django.db import close_old_connections
from django.contrib.auth.models import User
from django.test import Client
from a_agent.models import ChatSession, ChatMessage
from a_agent.services.orchestrator import handle_user_message

user = User.objects.filter(username='rhea').first() or User.objects.first()

test_runs = [
    # Q1: Git rebase vs merge
    {
        'tc_key': 'en_q1_rebase',
        'tc_title': 'Git rebase vs merge: Difference & Forbidden Scenarios',
        'query': 'What is the fundamental difference between Git rebase and merge? Under what scenario should you NEVER use rebase?',
        'model_key': 'qwen32b',
        'model_name': 'Qwen 2.5 Coder 32B',
        'model_id': '@cf/qwen/qwen2.5-coder-32b-instruct',
        'structured': True,
        'mode_label': 'Structured',
    },
    {
        'tc_key': 'en_q1_rebase',
        'tc_title': 'Git rebase vs merge: Difference & Forbidden Scenarios',
        'query': 'What is the fundamental difference between Git rebase and merge? Under what scenario should you NEVER use rebase?',
        'model_key': 'llama70b',
        'model_name': 'Llama 3.3 70B Fast',
        'model_id': '@cf/meta/llama-3.3-70b-instruct-fp8-fast',
        'structured': True,
        'mode_label': 'Structured',
    },
    {
        'tc_key': 'en_q1_rebase',
        'tc_title': 'Git rebase vs merge: Difference & Forbidden Scenarios',
        'query': 'What is the fundamental difference between Git rebase and merge? Under what scenario should you NEVER use rebase?',
        'model_key': 'qwen32b',
        'model_name': 'Qwen 2.5 Coder 32B',
        'model_id': '@cf/qwen/qwen2.5-coder-32b-instruct',
        'structured': False,
        'mode_label': 'Unconstrained (Raw)',
    },
    {
        'tc_key': 'en_q1_rebase',
        'tc_title': 'Git rebase vs merge: Difference & Forbidden Scenarios',
        'query': 'What is the fundamental difference between Git rebase and merge? Under what scenario should you NEVER use rebase?',
        'model_key': 'llama70b',
        'model_name': 'Llama 3.3 70B Fast',
        'model_id': '@cf/meta/llama-3.3-70b-instruct-fp8-fast',
        'structured': False,
        'mode_label': 'Unconstrained (Raw)',
    },
    # Q2: Purging secrets from Git history
    {
        'tc_key': 'en_q2_secrets',
        'tc_title': 'Purge committed .env secrets from Git history',
        'query': 'I accidentally committed and pushed a .env file with production secrets to GitHub. How do I completely purge it from Git history?',
        'model_key': 'qwen32b',
        'model_name': 'Qwen 2.5 Coder 32B',
        'model_id': '@cf/qwen/qwen2.5-coder-32b-instruct',
        'structured': True,
        'mode_label': 'Structured',
    },
    {
        'tc_key': 'en_q2_secrets',
        'tc_title': 'Purge committed .env secrets from Git history',
        'query': 'I accidentally committed and pushed a .env file with production secrets to GitHub. How do I completely purge it from Git history?',
        'model_key': 'llama70b',
        'model_name': 'Llama 3.3 70B Fast',
        'model_id': '@cf/meta/llama-3.3-70b-instruct-fp8-fast',
        'structured': True,
        'mode_label': 'Structured',
    },
]

created_sessions = []

print("=== STARTING ENGLISH MODEL COMPARISON RUNS (STRUCTURED & RAW) ===")

for run in test_runs:
    close_old_connections()
    title_str = f"[{run['mode_label']}] {run['model_name']} - {run['tc_title']}"
    print(f"\n--> Running: {title_str}...")
    t0 = time.time()
    try:
        reply = handle_user_message(
            run['query'],
            user,
            model=run['model_id'],
            structured=run['structured'],
        )
        sess = ChatSession.objects.create(
            user=user,
            title=f"[{run['mode_label']}-{run['model_key']}] {run['tc_title'][:20]}"
        )
        ChatMessage.objects.create(
            session=sess,
            role='user',
            content=run['query']
        )
        ChatMessage.objects.create(
            session=sess,
            role='assistant',
            content=reply.content,
            citations=reply.citations,
            tool_trace=reply.tool_trace,
            pending_action=reply.pending_action,
        )
        run_record = dict(run)
        run_record['session_id'] = sess.id
        run_record['latency'] = round(time.time() - t0, 2)
        created_sessions.append(run_record)
        print(f"    Done in {run_record['latency']}s. Session ID: {sess.id}")
    except Exception as e:
        print(f"    ERROR in {title_str}:", e)

out_dir = '/Users/huangrenqian/.gemini/antigravity/brain/27963ca9-22ab-4c87-9607-032d359f3dd4'
scratch_dir = os.path.join(out_dir, 'scratch')
os.makedirs(scratch_dir, exist_ok=True)

# Start Django test server on port 8097
proc = subprocess.Popen(
    ['/Users/huangrenqian/Projects/DSS5105/Final_project/blog/.venv/bin/python', 'manage.py', 'runserver', '127.0.0.1:8097', '--noreload'],
    cwd='/Users/huangrenqian/Projects/DSS5105/Final_project/blog',
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)

time.sleep(2.5)

chrome_bin = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
close_old_connections()
c = Client()
c.force_login(user)

extra_css = """
<base href="http://127.0.0.1:8097/">
<style>
  header, nav, footer, #agent-sidebar, .agent-chat > div:first-child { display: none !important; }
  .agent-chat { padding-top: 16px !important; padding-bottom: 16px !important; max-width: 960px !important; margin: 0 auto !important; }
  .agent-main { min-height: auto !important; border: 1px solid #cbd5e1 !important; box-shadow: 0 4px 16px rgba(0,0,0,0.06) !important; border-radius: 1rem !important; }
  #chat-messages { overflow: visible !important; max-height: none !important; }
</style>
"""

screenshot_files = []

try:
    for item in created_sessions:
        close_old_connections()
        sid = item['session_id']
        resp = c.get(f'/agent/session/{sid}/', HTTP_HOST='127.0.0.1:8097')
        html = resp.content.decode('utf-8').replace('<head>', '<head>' + extra_css, 1)
        mode_suffix = 'structured' if item['structured'] else 'raw'
        file_prefix = f"compare_en_{item['tc_key']}_{item['model_key']}_{mode_suffix}"
        html_path = os.path.join(scratch_dir, f"view_{file_prefix}.html")
        png_path = os.path.join(out_dir, f"{file_prefix}.png")
        
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        subprocess.run([
            chrome_bin, '--headless=new', '--disable-gpu', '--hide-scrollbars',
            '--window-size=1020,1100', '--force-device-scale-factor=2',
            f'--screenshot={png_path}', f'file://{html_path}'
        ], check=True)
        screenshot_files.append((item['tc_title'], item['model_name'], item['mode_label'], item['latency'], png_path))
        print("Captured screenshot:", png_path)

finally:
    proc.terminate()
    close_old_connections()
    for item in created_sessions:
        ChatSession.objects.filter(id=item['session_id']).delete()

print("\nALL ENGLISH SCREENSHOTS GENERATED SUCCESSFULLY:")
for title, model_name, mode_label, lat, path in screenshot_files:
    print(f" - [{model_name} | {mode_label}] {title} ({lat}s) -> {path}")
