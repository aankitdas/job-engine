"""Prove the Greenhouse and Ashby public job board APIs work."""
import httpx

GREENHOUSE = ["stripe", "figma", "databricks", "anthropic", "duolingo"]
ASHBY = ["ramp", "linear", "vanta", "openai", "cursor"]

def greenhouse(slug: str):
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    r = httpx.get(url, timeout=20)
    r.raise_for_status()
    jobs = r.json()["jobs"]
    return jobs, jobs[0] if jobs else None

def ashby(slug: str):
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"
    r = httpx.get(url, timeout=20)
    r.raise_for_status()
    jobs = r.json().get("jobs", [])
    return jobs, jobs[0] if jobs else None

for name, slugs, fn in [("GREENHOUSE", GREENHOUSE, greenhouse),
                        ("ASHBY", ASHBY, ashby)]:
    print(f"\n=== {name} ===")
    for slug in slugs:
        try:
            jobs, first = fn(slug)
            title = first.get("title") if first else "n/a"
            date = (first.get("updated_at") or first.get("publishedAt")
                    if first else "n/a")
            desc = first.get("content") or first.get("descriptionPlain", "") if first else ""
            print(f"  OK   {slug:12} {len(jobs):4} jobs | {title[:40]:40} | "
                  f"{str(date)[:10]} | desc {len(desc)} chars")
        except Exception as e:
            print(f"  FAIL {slug:12} {type(e).__name__}: {str(e)[:60]}")
