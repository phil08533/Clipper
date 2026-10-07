"""Instagram Reels via instagram.com's Create dialog."""
from .base import NotLoggedIn, Unconfirmed, click_if_visible, first_visible, replace_text, wait_for_any_text

NAME = "Instagram"
LOGIN_URL = "https://www.instagram.com/accounts/login/"


def is_logged_in(page):
    page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
    page.wait_for_timeout(4000)
    if "accounts/login" in page.url:
        return False
    return not page.locator('input[name="username"]').first.is_visible()


def upload(page, post):
    page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    if "accounts/login" in page.url or page.locator('input[name="username"]').first.is_visible():
        raise NotLoggedIn("Instagram session expired — reconnect the account")
    click_if_visible(page, ['button:has-text("Not Now")', 'div[role="button"]:has-text("Not now")'], 3)

    if not click_if_visible(page, ['svg[aria-label="New post"]', 'svg[aria-label="Create"]'], 15):
        raise RuntimeError("Could not find the Create button")
    # Newer layouts open a small menu first (Post / Live / Ad).
    click_if_visible(page, ['a:has(span:text-is("Post"))', 'div[role="menuitem"]:has-text("Post")', 'span:text-is("Post")'], 4)

    page.locator('input[type="file"]').first.set_input_files(post["file"])
    click_if_visible(page, ['button:has-text("OK")'], 8)  # "Video posts are now shared as reels"

    # Keep the original 9:16 frame rather than Instagram's default square crop.
    if click_if_visible(page, ['svg[aria-label="Select crop"]', 'svg[aria-label="Select Crop"]'], 10):
        click_if_visible(page, ['div[role="button"]:has-text("Original")', 'span:text-is("Original")'], 5)

    for _ in range(2):
        nxt = first_visible(page, ['div[role="dialog"] div[role="button"]:text-is("Next")', 'div[role="button"]:has-text("Next")'], 60)
        if not nxt:
            raise RuntimeError("Could not find Next button")
        nxt.click()
        page.wait_for_timeout(2000)

    caption = first_visible(page, ['div[aria-label="Write a caption..."]', 'div[contenteditable="true"][role="textbox"]'], 30)
    if not caption:
        raise RuntimeError("Caption box did not appear")
    replace_text(page, caption, post["caption"][:2150], delay=8)

    if post["ai_label"]:
        click_if_visible(page, ['span:text-is("Advanced settings")', 'div[role="button"]:has-text("Advanced settings")'], 5)
        row = first_visible(page, [':text("Add AI label")'], 5)
        if not row:
            raise RuntimeError("Could not find Instagram's AI label toggle (disable AI label in the campaign to post anyway)")
        toggle = row.locator('xpath=ancestor::*[.//input[@type="checkbox"]][1]//input[@type="checkbox"]').first
        if not toggle.is_checked():
            toggle.click(force=True)

    share = first_visible(page, ['div[role="dialog"] div[role="button"]:text-is("Share")', 'div[role="button"]:has-text("Share")'], 30)
    if not share:
        raise RuntimeError("Could not find Share button")
    share.click()
    if not wait_for_any_text(page, ["Your reel has been shared", "Reel shared", "Your post has been shared"], 600):
        raise Unconfirmed("Clicked Share but Instagram showed no confirmation")
    return None
