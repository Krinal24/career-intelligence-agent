import json
from pathlib import Path

from playwright.sync_api import sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BROWSER_PROFILE = PROJECT_ROOT / ".browser_profile"
MATCHED_JOBS_FILE = PROJECT_ROOT / "app" / "data" / "matched_jobs.json"


def load_top_job():
    """Load the highest-ranked job from matched_jobs.json."""

    if not MATCHED_JOBS_FILE.exists():
        raise FileNotFoundError(
            f"Could not find {MATCHED_JOBS_FILE}"
        )

    with open(MATCHED_JOBS_FILE, "r", encoding="utf-8") as file:
        jobs = json.load(file)

    if not jobs:
        raise ValueError("matched_jobs.json contains no jobs.")

    return jobs[0]


def inspect_application_page(page):
    """Inspect the current page without applying."""

    print()
    print("=" * 70)
    print("APPLICATION PAGE INSPECTION")
    print("=" * 70)

    print()
    print(f"Page title: {page.title()}")
    print(f"Current URL: {page.url}")

    text = page.locator("body").inner_text().lower()

    # --------------------------------------------------------
    # Look for application-related text
    # --------------------------------------------------------

    indicators = {
        "easy_apply": [
            "easy apply",
        ],
        "apply": [
            "apply",
            "apply now",
        ],
        "external_application": [
            "apply on company website",
            "company website",
            "external application",
        ],
        "login_required": [
            "sign in",
            "join now",
        ],
    }

    detected = {}

    for category, phrases in indicators.items():
        matches = [
            phrase
            for phrase in phrases
            if phrase in text
        ]

        detected[category] = matches

    print()
    print("DETECTED INDICATORS")
    print("-" * 70)

    for category, matches in detected.items():
        if matches:
            print(f"{category}: {matches}")
        else:
            print(f"{category}: none")

    # --------------------------------------------------------
    # Inspect buttons
    # --------------------------------------------------------

    print()
    print("VISIBLE BUTTONS")
    print("-" * 70)

    try:
        buttons = page.locator("button").all_inner_texts()

        for button in buttons[:30]:
            button = button.strip()

            if button:
                print(f"- {button}")

    except Exception as error:
        print(f"Could not inspect buttons: {error}")

    # --------------------------------------------------------
    # Inspect links containing application-related text
    # --------------------------------------------------------

    print()
    print("APPLICATION-RELATED LINKS")
    print("-" * 70)

    try:
        links = page.locator("a").all()

        count = 0

        for link in links:
            try:
                text_content = link.inner_text().strip()
                href = link.get_attribute("href")

                combined = (
                    f"{text_content} {href or ''}"
                ).lower()

                if any(
                    keyword in combined
                    for keyword in [
                        "apply",
                        "career",
                        "job",
                        "application",
                    ]
                ):
                    print(
                        f"- {text_content[:100]}"
                    )

                    if href:
                        print(
                            f"  {href[:200]}"
                        )

                    count += 1

                    if count >= 20:
                        break

            except Exception:
                continue

    except Exception as error:
        print(
            f"Could not inspect links: {error}"
        )

    return detected


def main():

    job = load_top_job()

    print()
    print("=" * 70)
    print("TOP MATCHED JOB")
    print("=" * 70)

    print()
    print(f"Title:    {job.get('title')}")
    print(f"Company:  {job.get('company')}")
    print(f"Location: {job.get('location')}")
    print(f"Score:    {job.get('final_score', job.get('score', 'N/A'))}")
    print(f"URL:      {job.get('url')}")

    url = job.get("url")

    if not url:
        raise ValueError(
            "Top matched job does not contain a URL."
        )

    with sync_playwright() as playwright:

        print()
        print("Starting application browser...")

        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_PROFILE),
            headless=False,
            viewport={
                "width": 1440,
                "height": 900,
            },
            args=[
                "--start-maximized",
            ],
        )

        try:

            if context.pages:
                page = context.pages[0]
            else:
                page = context.new_page()

            print()
            print("Opening job...")

            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            # Give LinkedIn some time to finish rendering.
            page.wait_for_timeout(5000)

            inspect_application_page(page)

            screenshot_path = (
                PROJECT_ROOT
                / "application_inspection.png"
            )

            page.screenshot(
                path=str(screenshot_path),
                full_page=True,
            )

            print()
            print(
                f"Screenshot saved to:\n"
                f"{screenshot_path}"
            )

            print()
            print("=" * 70)
            print("INSPECTION COMPLETE")
            print("=" * 70)

            print()
            print(
                "No Apply button was clicked."
            )
            print(
                "No application was submitted."
            )

            print()
            print(
                "Browser will remain open for 20 seconds."
            )

            page.wait_for_timeout(20000)

        finally:
            context.close()


if __name__ == "__main__":
    main()