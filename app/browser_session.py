from playwright.sync_api import sync_playwright


class BrowserSession:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def start(self):
        """
        Start a real Chromium browser for TAB.

        The window is positioned far off-screen so it
        remains headed, but does not sit over your desktop.
        """

        if self.browser is not None:
            return

        self.playwright = sync_playwright().start()

        self.browser = self.playwright.chromium.launch(
            headless=False,
            args=[
                "--window-position=-32000,-32000",
                "--window-size=1600,1200",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding"
            ]
        )

        self.context = self.browser.new_context(
            permissions=["local-network-access"],
            viewport={
                "width": 1600,
                "height": 1200
            }
        )

        self.page = self.context.new_page()

        print(
            "Browser session started "
            "(off-screen)."
        )

    def get_page(self):
        """
        Return the browser page.
        """

        if self.page is None:
            raise RuntimeError(
                "Browser session has not been started."
            )

        return self.page

    def close(self):
        """
        Cleanly close Chromium and Playwright.
        """

        if self.context is not None:
            self.context.close()

        if self.browser is not None:
            self.browser.close()

        if self.playwright is not None:
            self.playwright.stop()

        self.page = None
        self.context = None
        self.browser = None
        self.playwright = None

        print("Browser session closed.")