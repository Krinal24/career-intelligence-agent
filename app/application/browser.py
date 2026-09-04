from pathlib import Path
from playwright.sync_api import sync_playwright


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Dedicated browser profile for the application agent.
#
# IMPORTANT:
# Do NOT use your normal Chrome profile here.
# Playwright will maintain its own session.
BROWSER_PROFILE = PROJECT_ROOT / ".browser_profile"

# Start with headed browser so we can actually watch what happens.
HEADLESS = False

# Default URL used when testing the browser.
DEFAULT_URL = "https://www.linkedin.com"


# ============================================================
# BROWSER CONTROLLER
# ============================================================

class BrowserController:

    def __init__(self):
        self.playwright = None
        self.context = None
        self.page = None

    def start(self):
        """
        Start a persistent Chromium browser session.

        The persistent context allows cookies/login sessions
        to survive between runs.
        """

        print()
        print("=" * 70)
        print("STARTING APPLICATION BROWSER")
        print("=" * 70)

        print()
        print(f"Browser profile: {BROWSER_PROFILE}")

        BROWSER_PROFILE.mkdir(
            parents=True,
            exist_ok=True
        )

        self.playwright = sync_playwright().start()

        self.context = (
            self.playwright.chromium.launch_persistent_context(
                user_data_dir=str(BROWSER_PROFILE),

                headless=HEADLESS,

                viewport={
                    "width": 1440,
                    "height": 900,
                },

                args=[
                    "--start-maximized",
                ],
            )
        )

        # A persistent context may already contain a page.
        if self.context.pages:

            self.page = self.context.pages[0]

        else:

            self.page = self.context.new_page()

        print()
        print("Browser started successfully.")

        print(
            f"Current page: {self.page.url}"
        )

        return self.page

    def open(self, url):
        """
        Navigate to a URL.
        """

        if self.page is None:
            raise RuntimeError(
                "Browser has not been started. "
                "Call start() first."
            )

        print()
        print(f"Opening:")
        print(url)

        self.page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=60000,
        )

        print()
        print(
            f"Page loaded: {self.page.url}"
        )

        return self.page

    def wait(self, seconds=3):
        """
        Wait for a specified number of seconds.
        """

        if self.page is None:
            return

        self.page.wait_for_timeout(
            seconds * 1000
        )

    def title(self):
        """
        Return current page title.
        """

        if self.page is None:
            return ""

        return self.page.title()

    def url(self):
        """
        Return current URL.
        """

        if self.page is None:
            return ""

        return self.page.url

    def screenshot(self, filename="browser_test.png"):
        """
        Save a screenshot for debugging.
        """

        if self.page is None:
            return

        screenshot_path = (
            PROJECT_ROOT / filename
        )

        self.page.screenshot(
            path=str(screenshot_path),
            full_page=True,
        )

        print()
        print(
            f"Screenshot saved to:"
            f"\n{screenshot_path}"
        )

    def close(self):
        """
        Close browser and Playwright cleanly.
        """

        print()
        print("Closing browser...")

        if self.context:

            self.context.close()
            self.context = None

        if self.playwright:

            self.playwright.stop()
            self.playwright = None

        self.page = None

        print("Browser closed.")


# ============================================================
# LINKEDIN HELPERS
# ============================================================

def check_linkedin_login(page):
    """
    Determine whether the current LinkedIn session appears
    to be logged in.

    This is intentionally conservative. We don't attempt to
    bypass authentication or anti-bot mechanisms.
    """

    url = page.url.lower()

    if "linkedin.com" not in url:

        return {
            "logged_in": False,
            "reason": "Not currently on LinkedIn.",
        }

    # Common indicators of an authenticated LinkedIn session.
    logged_in_indicators = [
        "/feed",
        "/in/",
        "/mynetwork",
        "/jobs/",
    ]

    if any(
        indicator in url
        for indicator in logged_in_indicators
    ):

        return {
            "logged_in": True,
            "reason": "URL indicates an authenticated LinkedIn session.",
        }

    # Check for common page elements.
    try:

        profile_selectors = [
            'a[href*="/in/"]',
            '[data-testid="nav-profile"]',
            'button[aria-label*="Me"]',
        ]

        for selector in profile_selectors:

            if page.locator(selector).count() > 0:

                return {
                    "logged_in": True,
                    "reason": (
                        "Authenticated LinkedIn UI element detected."
                    ),
                }

    except Exception:
        pass

    return {
        "logged_in": False,
        "reason": (
            "Could not confirm an authenticated LinkedIn session."
        ),
    }


# ============================================================
# TEST
# ============================================================

def main():

    browser = BrowserController()

    try:

        page = browser.start()

        # ----------------------------------------------------
        # Open LinkedIn
        # ----------------------------------------------------

        browser.open(
            DEFAULT_URL
        )

        browser.wait(3)

        # ----------------------------------------------------
        # Print information
        # ----------------------------------------------------

        print()
        print("=" * 70)
        print("BROWSER TEST")
        print("=" * 70)

        print()
        print(
            f"Page title: {browser.title()}"
        )

        print(
            f"Current URL: {browser.url()}"
        )

        # ----------------------------------------------------
        # Login status
        # ----------------------------------------------------

        login_status = check_linkedin_login(
            page
        )

        print()

        if login_status["logged_in"]:

            print(
                "LinkedIn login: DETECTED"
            )

        else:

            print(
                "LinkedIn login: NOT DETECTED"
            )

            print()
            print(
                "If this is your first run, log into LinkedIn "
                "manually in the browser window."
            )

            print(
                "The session will be saved in:"
            )

            print(
                BROWSER_PROFILE
            )

        print()
        print(
            f"Reason: {login_status['reason']}"
        )

        # ----------------------------------------------------
        # Screenshot
        # ----------------------------------------------------

        browser.screenshot(
            "browser_test.png"
        )

        # ----------------------------------------------------
        # Keep browser open
        # ----------------------------------------------------

        print()
        print("=" * 70)
        print("BROWSER IS READY")
        print("=" * 70)

        print()
        print(
            "The browser will remain open for 30 seconds."
        )

        print(
            "Use this time to verify that the browser "
            "looks normal."
        )

        browser.wait(30)

    except KeyboardInterrupt:

        print()
        print(
            "Browser test interrupted."
        )

    except Exception as error:

        print()
        print("=" * 70)
        print("BROWSER ERROR")
        print("=" * 70)

        print()
        print(
            repr(error)
        )

    finally:

        browser.close()


if __name__ == "__main__":
    main()