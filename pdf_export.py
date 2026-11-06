"""Print an edition's HTML to PDF with headless Chrome (preinstalled on GitHub's Ubuntu runners).

Fail-soft: if Chrome isn't available the digest still goes out, just without a PDF.
"""
import os
import shutil
import subprocess
import sys
import tempfile

import config

CANDIDATES = [
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
]
# A broadsheet-shaped page (1000px paper + margins) so the two-column layout is kept, newsprint
# colours are printed, and the email's inline-block columns (.rr/.rc/.rg from email_builder._cols)
# become flex rows, because Chrome can split flex items across pages but not inline-blocks.
PRINT_CSS = ("<style>@page{size:1064px 1505px;margin:0}"
             "html,body{-webkit-print-color-adjust:exact;print-color-adjust:exact}"
             ".rr{display:flex!important;align-items:flex-start}"
             ".rc{display:block!important;flex:1 1 0;min-width:0}"
             ".rg{flex:0 0 auto}</style>")


def find_chrome() -> str:
    for name in ([config.CHROME_BIN] if config.CHROME_BIN else []) + CANDIDATES:
        path = shutil.which(name) or (name if os.path.isfile(name) else "")
        if path:
            return path
    return ""


def html_to_pdf(html: str, pdf_path: str) -> bool:
    """Write pdf_path from the HTML; True on success."""
    chrome = find_chrome()
    if not chrome:
        print("  ! PDF skipped: Chrome/Chromium not found (set CHROME_BIN).")
        return False
    if os.path.exists(pdf_path):
        os.remove(pdf_path)
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "edition.html")
        with open(src, "w", encoding="utf-8") as fh:
            fh.write(html.replace("</head>", PRINT_CSS + "</head>", 1))
        cmd = [chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
               f"--user-data-dir={os.path.join(tmp, 'profile')}", "--virtual-time-budget=10000",
               f"--print-to-pdf={os.path.abspath(pdf_path)}", "file://" + src]
        if sys.platform.startswith("linux"):
            cmd.insert(1, "--no-sandbox")   # Ubuntu 24.04 runners block Chrome's user-namespace sandbox
        try:
            subprocess.run(cmd, capture_output=True, timeout=120, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"  ! PDF export failed: {exc}")
            return False
    ok = os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0
    if not ok:
        print("  ! PDF export failed: Chrome produced no file.")
    return ok
