# DSS5105 — Group 4 Capstone

NUS DSS5105 capstone project: **Blog Reading Co-Pilot Agent** (Track 5).

## Structure

- `Final_project/blog/` — Django/Wagtail blog platform
- `Final_project/项目说明.md` — project overview (Chinese)

## Quick start

```bash
cd Final_project/blog
cp .env.example .env   # set POSTGRES_PASSWORD
python3.10 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
./scripts/run_local.sh
```

Open http://127.0.0.1:8000/
