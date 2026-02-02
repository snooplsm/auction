#!/usr/bin/env python3
"""
Script to download property lists from bid4assets.com for Philadelphia foreclosures and tax sales.
Uses Playwright for browser automation.

Usage:
    export bid_username="your_username"
    export bid_password="your_password"
    python download_bid4assets.py
"""

import os
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright, Page, Browser

# Configuration
FORECLOSURES_URL = "https://www.bid4assets.com/philaforeclosures"
TAXSALES_URL = "https://www.bid4assets.com/philataxsales"
LOGIN_URL = "https://www.bid4assets.com/myaccount/login"

BASE_DIR = Path(__file__).parent
FORECLOSURES_DIR = BASE_DIR / "foreclosures"
TAXSALES_DIR = BASE_DIR / "taxsales"


async def logout(page: Page):
    """Log out of the site."""
    print("Logging out...")
    # Try to find and click logout link
    await page.goto("https://www.bid4assets.com/myaccount/logout", timeout=15000)
    await asyncio.sleep(2)
    print("Logged out")


async def handle_cookie_consent(page: Page):
    """Handle cookie consent popup by searching DOM for Accept All Cookies button."""
    for _ in range(10):  # Try for up to 5 seconds
        clicked = await page.evaluate('''() => {
            const elements = document.querySelectorAll('button, a, div, span');
            for (const el of elements) {
                if (el.textContent.trim() === 'Accept All Cookies') {
                    el.click();
                    return true;
                }
            }
            return false;
        }''')
        if clicked:
            print("Clicked Accept All Cookies")
            await asyncio.sleep(1)
            return True
        await asyncio.sleep(0.5)
    return False


async def login(page: Page, username: str, password: str) -> bool:
    """Handle login if redirected to login page."""
    print("Login required, attempting to log in...")

    await asyncio.sleep(2)  # Wait for form to load

    # Handle cookie consent on login page first
    await handle_cookie_consent(page)

    # Use JavaScript to find and fill the form fields
    print(f"Filling username: {username}")
    filled_username = await page.evaluate('''(username) => {
        // Find username/email input
        const inputs = document.querySelectorAll('input');
        for (const input of inputs) {
            const type = input.type.toLowerCase();
            const name = (input.name || '').toLowerCase();
            const id = (input.id || '').toLowerCase();
            const placeholder = (input.placeholder || '').toLowerCase();

            if (type === 'email' || name.includes('email') || name.includes('username') ||
                id.includes('email') || id.includes('username') ||
                placeholder.includes('email') || placeholder.includes('username')) {
                input.focus();
                input.value = username;
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
                return true;
            }
        }
        // Fallback: first text/email input
        for (const input of inputs) {
            if (input.type === 'text' || input.type === 'email') {
                input.focus();
                input.value = username;
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
                return true;
            }
        }
        return false;
    }''', username)
    print(f"Username filled: {filled_username}")

    await asyncio.sleep(0.5)

    print("Filling password...")
    filled_password = await page.evaluate('''(password) => {
        const inputs = document.querySelectorAll('input[type="password"]');
        if (inputs.length > 0) {
            inputs[0].focus();
            inputs[0].value = password;
            inputs[0].dispatchEvent(new Event('input', { bubbles: true }));
            inputs[0].dispatchEvent(new Event('change', { bubbles: true }));
            return true;
        }
        return false;
    }''', password)
    print(f"Password filled: {filled_password}")

    await asyncio.sleep(0.5)

    # Click submit button
    print("Clicking login button...")
    clicked = await page.evaluate('''() => {
        // Look for submit button
        const buttons = document.querySelectorAll('button, input[type="submit"]');
        for (const btn of buttons) {
            const text = btn.textContent.toLowerCase();
            const type = btn.type;
            if (type === 'submit' || text.includes('log in') || text.includes('login') || text.includes('sign in')) {
                btn.click();
                return true;
            }
        }
        // Fallback: any button in a form
        const form = document.querySelector('form');
        if (form) {
            const btn = form.querySelector('button');
            if (btn) {
                btn.click();
                return true;
            }
        }
        return false;
    }''')
    print(f"Login button clicked: {clicked}")

    # Wait for navigation after login
    await asyncio.sleep(5)

    # Check if login was successful (not still on login page)
    current_url = page.url
    if 'login' not in current_url.lower():
        print("Login successful!")
        return True
    else:
        print("Login may have failed, still on login page")
        return False


async def download_property_lists(page: Page, url: str, output_dir: Path, username: str, password: str) -> list:
    """Download all property lists from a given auction page."""
    downloaded_files = []

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nNavigating to {url}")
    await page.goto(url, timeout=15000)
    await asyncio.sleep(3)  # Give page time to render and redirect

    print(f"Current URL after navigation: {page.url}")

    # Handle cookie consent if it appears
    await handle_cookie_consent(page)

    # Check if redirected to login
    if 'login' in page.url.lower() or 'myaccount' in page.url.lower():
        # Handle cookie consent on login page too
        await handle_cookie_consent(page)
        success = await login(page, username, password)
        if not success:
            print("Failed to login, cannot continue")
            return downloaded_files
        # Navigate back to the target page
        await page.goto(url, timeout=15000)
        await asyncio.sleep(2)
        # Handle cookie consent again after login
        await handle_cookie_consent(page)

    # Give time for JavaScript to load
    await asyncio.sleep(2)

    # Find the sales date dropdown
    dropdown_selectors = [
        'select[name*="sale"]',
        'select[name*="date"]',
        'select#saleDate',
        'select.sale-date',
        'select[id*="sale"]',
        'select[id*="date"]',
        'select'  # Fallback to any select
    ]

    dropdown = None
    for selector in dropdown_selectors:
        try:
            elements = await page.query_selector_all(selector)
            for elem in elements:
                # Check if this dropdown has sale date options
                options = await elem.query_selector_all('option')
                if len(options) > 1:
                    dropdown = elem
                    break
            if dropdown:
                break
        except:
            continue

    if not dropdown:
        print("Could not find sales date dropdown")
        # Try to find and click any download button on the page
        await try_download_current_page(page, output_dir, "default", downloaded_files)
        return downloaded_files

    # Get all options from the dropdown
    options = await dropdown.query_selector_all('option')
    sale_dates = []

    for option in options:
        value = await option.get_attribute('value')
        text = await option.inner_text()
        if value and value.strip() and text.strip():
            sale_dates.append((value, text.strip()))

    print(f"Found {len(sale_dates)} sale dates: {[s[1] for s in sale_dates]}")

    # Iterate through each sale date and download
    for value, text in sale_dates:
        print(f"\nProcessing sale date: {text}")

        # Re-find the dropdown each time (it may have become stale after navigation)
        dropdown = await page.query_selector('select')
        if not dropdown:
            print("Could not find dropdown, refreshing page...")
            await page.goto(url, timeout=15000)
            await asyncio.sleep(3)
            await handle_cookie_consent(page)
            dropdown = await page.query_selector('select')
            if not dropdown:
                print("Still no dropdown, skipping...")
                continue

        # Select the date
        try:
            await dropdown.select_option(value=value)
        except Exception as e:
            print(f"Error selecting {text}: {e}")
            try:
                await dropdown.select_option(label=text)
            except:
                print(f"Could not select {text}")
                continue

        # Wait for page to update
        await asyncio.sleep(2)

        # Sanitize filename
        safe_filename = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in text)

        # Try to download (pass the date value for the second dropdown)
        await try_download_current_page(page, output_dir, safe_filename, downloaded_files, url, username, password, value)

    return downloaded_files


async def try_download_current_page(page: Page, output_dir: Path, filename_prefix: str, downloaded_files: list,
                                     original_url: str = None, username: str = None, password: str = None,
                                     date_value: str = None):
    """Try to find and click the download property list button."""

    download_selectors = [
        'a:has-text("Download Property List")',
        'button:has-text("Download Property List")',
        'a:has-text("Download")',
        'button:has-text("Download")',
        'a[href*="download"]',
        'a[href*="export"]',
        'a[href*=".xlsx"]',
        'a[href*=".xls"]',
        'a[href*=".csv"]',
        '.download-link',
        '#downloadBtn',
        'a.btn:has-text("Download")',
        'input[value*="Download"]'
    ]

    # Find and click the first download link
    download_btn = await page.evaluate('''() => {
        const links = document.querySelectorAll('a');
        for (const link of links) {
            if (link.textContent.includes('Download Property List') || link.textContent.includes('Download')) {
                link.click();
                return true;
            }
        }
        return false;
    }''')

    if not download_btn:
        print(f"Could not find download button for {filename_prefix}")
        return False

    print("Clicked download link, waiting for redirect...")
    await asyncio.sleep(3)

    # Check if we're on the propertylistdownload page
    current_url = page.url
    print(f"Now on: {current_url}")

    if 'propertylistdownload' in current_url.lower():
        print("On download page, selecting date and downloading...")

        # Handle cookie consent if it appears
        await handle_cookie_consent(page)

        # Find and select the same date from the dropdown on this page
        dropdown = await page.query_selector('select')
        if dropdown and date_value:
            print(f"Selecting date value: {date_value}")
            try:
                await dropdown.select_option(value=date_value)
            except:
                # Try selecting by label if value doesn't work
                options = await dropdown.query_selector_all('option')
                for option in options:
                    value = await option.get_attribute('value')
                    if value and value.strip():
                        await dropdown.select_option(value=value)
                        break
            await asyncio.sleep(1)

        # Now click the Download button on this page (id="bttnDownload")
        try:
            async with page.expect_download(timeout=30000) as download_info:
                # Click the DOWNLOAD button
                clicked = await page.evaluate('''() => {
                    // First try the specific button ID
                    const btn = document.getElementById('bttnDownload');
                    if (btn) {
                        btn.click();
                        return true;
                    }
                    // Fallback to any button with DOWNLOAD text
                    const buttons = document.querySelectorAll('button');
                    for (const b of buttons) {
                        if (b.textContent.trim().toUpperCase() === 'DOWNLOAD') {
                            b.click();
                            return true;
                        }
                    }
                    return false;
                }''')
                if not clicked:
                    print("Could not find Download button on download page")
                    return False

            download = await download_info.value
            suggested_name = download.suggested_filename
            ext = Path(suggested_name).suffix if suggested_name else '.xlsx'
            filename = f"{filename_prefix}{ext}"
            filepath = output_dir / filename
            await download.save_as(filepath)
            print(f"Downloaded: {filepath}")
            downloaded_files.append(str(filepath))

            # Go back to original page for next download
            if original_url:
                print(f"Returning to {original_url}")
                await page.goto(original_url, timeout=15000)
                await asyncio.sleep(2)
            return True

        except Exception as e:
            print(f"Download failed: {e}")
            # Check if redirected to login
            if 'login' in page.url.lower():
                print("Redirected to login page, logging in...")
                await handle_cookie_consent(page)
                await login(page, username, password)
                if original_url:
                    await page.goto(original_url, timeout=15000)
                    await asyncio.sleep(2)
            return False

    # Check if redirected to login
    elif 'login' in current_url.lower():
        print("Redirected to login page, logging in...")
        await handle_cookie_consent(page)
        await login(page, username, password)
        if original_url:
            await page.goto(original_url, timeout=15000)
            await asyncio.sleep(2)
        return False

    print(f"Unexpected page: {current_url}")
    return False


async def main():
    # Get credentials from environment
    username = os.environ.get('bid_username')
    password = os.environ.get('bid_password')

    if not username or not password:
        print("Error: Please set bid_username and bid_password environment variables")
        print("  export bid_username='your_username'")
        print("  export bid_password='your_password'")
        return

    print("Starting bid4assets downloader...")
    print(f"Foreclosures will be saved to: {FORECLOSURES_DIR}")
    print(f"Tax sales will be saved to: {TAXSALES_DIR}")

    async with async_playwright() as p:
        # Launch browser with stealth settings to avoid detection
        browser = await p.chromium.launch(
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
            ]
        )
        context = await browser.new_context(
            accept_downloads=True,
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            java_script_enabled=True,
            locale='en-US',
            timezone_id='America/New_York',
        )

        # Remove webdriver property to avoid detection
        await context.add_init_script('''
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
            window.chrome = { runtime: {} };
        ''')

        page = await context.new_page()

        all_downloads = []

        # Log in first before downloading anything
        print("\n" + "="*50)
        print("LOGGING IN FIRST")
        print("="*50)
        await page.goto("https://www.bid4assets.com/myaccount/login", timeout=15000)
        await asyncio.sleep(3)
        await handle_cookie_consent(page)
        await login(page, username, password)

        # Download foreclosures
        print("\n" + "="*50)
        print("DOWNLOADING FORECLOSURES")
        print("="*50)
        foreclosure_files = await download_property_lists(
            page, FORECLOSURES_URL, FORECLOSURES_DIR, username, password
        )
        all_downloads.extend(foreclosure_files)

        # Logout and login again before tax sales
        print("\n" + "="*50)
        print("LOGGING OUT")
        print("="*50)
        await logout(page)

        print("\n" + "="*50)
        print("LOGGING BACK IN")
        print("="*50)
        await page.goto("https://www.bid4assets.com/myaccount/login", timeout=15000)
        await asyncio.sleep(3)
        await handle_cookie_consent(page)
        await login(page, username, password)

        # Download tax sales
        print("\n" + "="*50)
        print("DOWNLOADING TAX SALES")
        print("="*50)
        taxsale_files = await download_property_lists(
            page, TAXSALES_URL, TAXSALES_DIR, username, password
        )
        all_downloads.extend(taxsale_files)

        await browser.close()

    # Summary
    print("\n" + "="*50)
    print("DOWNLOAD SUMMARY")
    print("="*50)
    print(f"Total files downloaded: {len(all_downloads)}")
    for f in all_downloads:
        print(f"  - {f}")


if __name__ == "__main__":
    asyncio.run(main())
