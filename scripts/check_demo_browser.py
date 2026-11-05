"""Exercise the real Streamlit client/server connection with Chromium."""

import argparse

from playwright.sync_api import expect, sync_playwright
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg


SCENARIOS = [
    ("LLM risks in medical diagnosis", "Non-technical", "Large language models can help clinicians", "92"),
    ("RAG assistant for company documents", "Technical", "Use an ingestion pipeline", "94"),
    ("AI customer-support assistant", "Business and technical", "Start with an agent-assist workflow", "93"),
]


def script_finished(payload):
    # Wait for an actual completed server rerun, not merely an old DOM that
    # still contains the previous result while the new run is in flight.
    if not isinstance(payload, bytes):
        return False
    message = ForwardMsg()
    message.ParseFromString(payload)
    return message.HasField("script_finished")


def assert_waiting(page):
    expect(page.get_by_test_id("stApp")).to_have_attribute("data-test-script-state", "notRunning")
    expect(page.locator(".agent-card")).to_have_count(6)
    expect(page.locator(".agent-card").filter(has_text="waiting")).to_have_count(6)
    expect(page.get_by_role("heading", name="Final response", exact=True)).to_have_count(0)
    expect(page.get_by_test_id("stMetricValue")).to_have_count(0)


def select_scenario(page, socket, name):
    selector = page.get_by_role("combobox", name="Example", exact=True)
    selector.fill(name)
    # Editing the search text is not a selection. Explicitly open the list
    # and commit an option before waiting for the server's rerun.
    selector.press("ArrowDown")
    expect(selector).to_have_attribute("aria-expanded", "true")
    option = page.get_by_role("option", name=name, exact=True)
    expect(option).to_be_visible()
    with socket.expect_event("framereceived", predicate=script_finished):
        selector.press("Enter")


def assert_completed(page, prefix, score):
    expect(page.get_by_test_id("stApp")).to_have_attribute("data-test-script-state", "notRunning")
    expect(page.locator(".agent-card").filter(has_text="complete · confidence")).to_have_count(6)
    expect(page.get_by_role("heading", name="Final response", exact=True)).to_be_visible()
    # The summary is also present in an agent card; check the standalone output.
    summaries = page.get_by_test_id("stMarkdownContainer").filter(has_text=prefix)
    expect(summaries).to_have_count(2)
    expect(summaries.last).to_be_visible()
    expect(page.get_by_test_id("stMetricValue")).to_have_text(["6 / 6", "PASS", score])
    expect(page.get_by_test_id("stException")).to_have_count(0)


def check_demo(url):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page()
            page.set_default_timeout(15000)
            expect.set_options(timeout=15000)
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            with page.expect_websocket() as connection:
                page.goto(url)
            socket = connection.value
            expect(page.locator(".demo-banner")).to_contain_text("curated, deterministic examples")
            assert_waiting(page)
            for index, (name, audience, prefix, score) in enumerate(SCENARIOS):
                if index:
                    select_scenario(page, socket, name)
                expect(page.get_by_label("Audience", exact=True)).to_have_value(audience)
                assert_waiting(page)
                with socket.expect_event("framereceived", predicate=script_finished):
                    page.get_by_role("button", name="Run six-agent demo", exact=True).click()
                assert_completed(page, prefix, score)
                # Streamlit's rerun shortcut must preserve the completed result.
                # Keep focus outside inputs without scrolling down to the
                # result and then back up while the next popup is opening.
                page.get_by_role("heading", name="Choose a workflow", exact=True).click()
                with socket.expect_event("framereceived", predicate=script_finished):
                    page.keyboard.press("r")
                assert_completed(page, prefix, score)
                print(f"Browser scenario and rerun passed: {name}")
            # Returning to a previously completed scenario must clear stale output.
            select_scenario(page, socket, SCENARIOS[0][0])
            assert_waiting(page)
            assert not errors, f"Browser JavaScript errors: {errors}"
        except Exception:
            print("Browser errors:", errors, flush=True)
            print("Browser accessibility:", page.locator("body").aria_snapshot(), flush=True)
            print("Browser page at failure:", page.locator("body").inner_text())
            raise
        finally:
            browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="URL of the running frontend")
    check_demo(parser.parse_args().url)
