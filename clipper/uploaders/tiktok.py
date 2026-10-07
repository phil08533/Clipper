"""TikTok via TikTok Studio's web uploader."""
import time

from .base import NotLoggedIn, Unconfirmed, click_if_visible, first_visible, replace_text, wait_for_any_text

NAME = "TikTok"
LOGIN_URL = "https://www.tiktok.com/login"
UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload?from=upload"


def is_logged_in(page):
    page.goto(UPLOAD_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    return "/login" not in page.url


def _set_ai_label(page):
    click_if_visible(page, ['text="Show more"', 'div[data-e2e="advanced_settings_container"]'], 3)
    row = first_visible(page, ['div:has(> div:text-is("AI-generated content"))', ':text("AI-generated content")'], 5)
    if not row:
        return False
    switch = row.locator('xpath=ancestor-or-self::*[.//input[@type="checkbox"] or .//*[@role="switch"]][1]')
    toggle = switch.locator('input[type="checkbox"], [role="switch"]').first
    try:
        checked = toggle.is_checked() if toggle.get_attribute("type") == "checkbox" else toggle.get_attribute("aria-checked") == "true"
        if not checked:
            toggle.click(force=True)
            click_if_visible(page, ['button:has-text("Turn on")'], 3)
        return True
    except Exception:  # noqa: BLE001
        return False


def upload(page, post):
    page.goto(UPLOAD_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    if "/login" in page.url:
        raise NotLoggedIn("TikTok session expired — reconnect the account")

    page.locator('input[type="file"]').first.set_input_files(post["file"])
    editor = first_visible(page, ['div.public-DraftEditor-content[contenteditable="true"]', 'div[contenteditable="true"]'], 180)
    if not editor:
        raise RuntimeError("Caption editor did not appear after selecting the file")
    replace_text(page, editor, post["caption"][:2100], delay=20)
    page.keyboard.press("Escape")  # close any hashtag suggestion popup

    if post["ai_label"] and not _set_ai_label(page):
        raise RuntimeError("Could not tick TikTok's AI-generated content label (disable AI label in the campaign to post anyway)")

    button = first_visible(page, ['button[data-e2e="post_video_button"]', 'button:has-text("Post"):not(:has-text("Posts"))'], 30)
    if not button:
        raise RuntimeError("Could not find Post button")
    deadline = time.time() + 900  # stays disabled until the upload finishes
    while time.time() < deadline and not button.is_enabled():
        page.wait_for_timeout(2000)
    button.click()
    click_if_visible(page, ['button:has-text("Post now")'], 8)

    if not wait_for_any_text(page, ["Your video has been uploaded", "Manage your posts", "Video published"], 180) \
            and "/tiktokstudio/content" not in page.url:
        raise Unconfirmed("Clicked Post but TikTok showed no confirmation")
    return None
