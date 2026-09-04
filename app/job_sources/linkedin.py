import json
import sys
import subprocess
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VENV_PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"

SEARCHES = [
    "Platform Engineer",
    "Software Engineer",
    "Backend Engineer",
    "Site Reliability Engineer",
    "DevOps Engineer",
    "Cloud Engineer",
    "Data Engineer",
    "ML Engineer",
    "AI Engineer",
]

LOCATION = "Bengaluru"
JOBS_PER_SEARCH = 10

OUTPUT_FILE = Path("app/data/jobs.json")


def scrape_linkedin_jobs():
    all_jobs = []

    with tempfile.TemporaryDirectory() as temp_dir:

        for search in SEARCHES:

            print(f"\nSearching LinkedIn: {search}")

            output_file = Path(temp_dir) / "jobs.json"

            command = [
                str(VENV_PYTHON),
                "-m",
                "linkedin_jobs_scraper",
                "jobs",
                search,
                "--location",
                LOCATION,
                "--limit",
                str(JOBS_PER_SEARCH),
                "--chrome-user-data-dir",
                str(Path.home() / ".linkedin-scraper"),
                "-f",
                "json",
                "-o",
                str(output_file),
            ]

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                print(f"Failed: {search}")
                print(result.stderr)
                continue

            try:
                with open(output_file, "r", encoding="utf-8") as file:
                    jobs = json.load(file)

                print(f"Found {len(jobs)} jobs")

                all_jobs.extend(jobs)

            except (FileNotFoundError, json.JSONDecodeError) as error:
                print(f"Could not read results for {search}: {error}")

    return all_jobs


def normalize_jobs(jobs):

    normalized = []
    seen_urls = set()

    for job in jobs:

        url = job.get("link", "").strip()

        if not url:
            continue

        # Same job can appear in multiple searches.
        if url in seen_urls:
            continue

        seen_urls.add(url)

        normalized.append({
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "location": job.get("place", ""),
            "url": url,
            "apply_url": job.get("apply_link", ""),
            "description": job.get("description", ""),
            "posted_date": job.get("date", ""),
            "date_text": job.get("date_text", ""),
            "insights": job.get("insights", []),
            "salary": job.get("salary", ""),
            "is_easy_apply": job.get("is_easy_apply", False),
            "applicant_count": job.get("applicant_count", ""),
            "benefits": job.get("benefits", []),
            "reposted": job.get("reposted", False),
            "source": "linkedin",
        })

    return normalized


def save_jobs(jobs):

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        json.dump(
            jobs,
            file,
            indent=4,
            ensure_ascii=False,
        )

    print(f"\nSaved {len(jobs)} unique jobs to {OUTPUT_FILE}")


def main():

    print("Starting LinkedIn job collection...\n")

    jobs = scrape_linkedin_jobs()

    print(f"\nTotal jobs collected: {len(jobs)}")

    jobs = normalize_jobs(jobs)

    print(f"Unique jobs after deduplication: {len(jobs)}")

    save_jobs(jobs)


if __name__ == "__main__":
    main()