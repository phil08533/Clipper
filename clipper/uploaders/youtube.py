"""YouTube Shorts via YouTube Studio's upload dialog."""
import time

from .base import NotLoggedIn, Unconfirmed, click_if_visible, first_visible, replace_text

NAME = "YouTube"
LOGIN_URL = "https://studio.youtube.com"


def is_logged_in(page):
    page.goto("https://studio.youtube.com", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    return "accounts.google.com" not in page.url and "signin" not in page.url.lower()


def upload(page, post):
    page.goto("https://www.youtube.com/upload", wait_until="domcontentloaded")
    page.wait_for_timeout(2500)
    if "accounts.google.com" in page.url:
        raise NotLoggedIn("YouTube session expired — reconnect the account")

    page.locator('input[type="file"]').first.set_input_files(post["file"])
    title = first_visible(page, ["#title-textarea #textbox", "ytcp-social-suggestions-textbox#title-textarea div[contenteditable]"], 120)
    if not title:
        raise RuntimeError("Upload dialog did not open")
    replace_text(page, title, post["title"][:100])
    desc = first_visible(page, ["#description-textarea #textbox"], 10)
    if desc:
        replace_text(page, desc, post["description"][:4900], delay=4)

    click_if_visible(page, ['tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]'], 10)
    choice = "VIDEO_HAS_ALTERED_CONTENT_YES" if post["ai_label"] else "VIDEO_HAS_ALTERED_CONTENT_NO"
    if not click_if_visible(page, [f'tp-yt-paper-radio-button[name="{choice}"]'], 3):
        click_if_visible(page, ["#toggle-button"], 3)  # "Show more"
        if not click_if_visible(page, [f'tp-yt-paper-radio-button[name="{choice}"]'], 5) and post["ai_label"]:
            raise RuntimeError("Could not tick YouTube's altered/synthetic content disclosure")

    for _ in range(3):
        nxt = first_visible(page, ["#next-button"], 20)
        if not nxt:
            raise RuntimeError("Could not find Next button")
        nxt.click()
        page.wait_for_timeout(1500)

    vis = post.get("visibility", "public").upper()
    if not click_if_visible(page, [f'tp-yt-paper-radio-button[name="{vis}"]'], 15):
        raise RuntimeError("Could not set visibility")

    url = None
    link = first_visible(page, ["a.style-scope.ytcp-video-info", "span.video-url-fadeable a"], 20)
    if link:
        url = link.get_attribute("href")

    # The file must finish uploading before the dialog is closed.
    deadline = time.time() + 1800
    while time.time() < deadline:
        label = page.locator("ytcp-video-upload-progress span.progress-label, .progress-label").first
        try:
            text = (label.inner_text(timeout=2000) or "").lower()
        except Exception:  # noqa: BLE001
            text = ""
        if text and "uploading" not in text:  # e.g. "Upload complete", "Checks complete", "Processing…"
            break
        page.wait_for_timeout(3000)

    done = first_visible(page, ["#done-button"], 20)
    if not done:
        raise RuntimeError("Could not find Publish button")
    done.click()
    if not first_visible(page, ["ytcp-video-share-dialog", "ytcp-uploads-still-processing-dialog", "#close-button"], 120):
        raise Unconfirmed("Clicked Publish but YouTube showed no confirmation")
    click_if_visible(page, ["ytcp-video-share-dialog #close-button", "#close-button"], 5)
    return url
