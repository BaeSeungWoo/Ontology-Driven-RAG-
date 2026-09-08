import re

from playwright.sync_api import sync_playwright


A4_CONTENT_PX = (210 - 16) / 25.4 * 96
LAYOUT_WIDTH = 1280
PRINT_CSS = """
@page { size: A4; margin: 8mm; }
html, body { background: #fff !important; }
article, tr, li, figure, blockquote { break-inside: avoid; page-break-inside: avoid; }
thead { display: table-header-group; }
h1, h2, h3 { break-after: avoid; page-break-after: avoid; }
"""


def render_html_pdf(html: str) -> bytes:
    scale = round(A4_CONTENT_PX / LAYOUT_WIDTH, 4)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(
                viewport={"width": LAYOUT_WIDTH, "height": 1200},
                java_script_enabled=False,
            )
            page.route(re.compile(r"^(?:https?|file):"), lambda route: route.abort())
            html = html.replace("</head>", f"<style>{PRINT_CSS}</style></head>", 1)
            page.set_content(html, wait_until="networkidle")
            page.emulate_media(media="screen")
            return page.pdf(
                format="A4",
                print_background=True,
                prefer_css_page_size=False,
                scale=scale,
                margin={"top": "8mm", "right": "8mm", "bottom": "8mm", "left": "8mm"},
            )
        finally:
            browser.close()
