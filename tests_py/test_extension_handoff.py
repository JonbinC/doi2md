from __future__ import annotations

from mdtero.extension_handoff import (
    attach_extension_handoff,
    build_extension_handoff,
    classify_acquisition_path,
    preferred_open_url,
    reason_needs_extension_handoff,
)


def test_classify_acquisition_path_cli_server_and_extension():
    assert (
        classify_acquisition_path(
            {
                "route_kind": "source_first",
                "requires_browser_capture": False,
                "requires_raw_upload": False,
                "action_sequence": ["native_arxiv_parse"],
            }
        )
        == "cli_server"
    )
    assert (
        classify_acquisition_path(
            {
                "route_kind": "browser_capture_required",
                "requires_browser_capture": True,
                "requires_raw_upload": True,
                "action_sequence": ["fetch_browser_source"],
            }
        )
        == "extension_required"
    )
    assert (
        classify_acquisition_path(
            {
                "route_kind": "browser_capture_required",
                "requires_browser_capture": False,
                "requires_raw_upload": False,
                "action_sequence": ["fetch_remote_html"],
            }
        )
        == "cli_server"
    )
    assert (
        classify_acquisition_path(
            {
                "route_kind": "server_html_first",
                "requires_browser_capture": False,
                "requires_raw_upload": True,
                "action_sequence": ["fetch_remote_html"],
            }
        )
        == "cli_local"
    )
    assert (
        classify_acquisition_path(
            {
                "top_connector": "ieee_html_document",
                "requires_browser_capture": False,
                "requires_raw_upload": False,
                "action_sequence": ["fetch_remote_html"],
            }
        )
        == "extension_required"
    )


def test_build_extension_handoff_includes_install_and_open_urls():
    handoff = build_extension_handoff(
        input_value="10.1109/ACCESS.2023.3340044",
        route={
            "requires_browser_capture": True,
            "route_kind": "browser_capture_required",
            "best_oa_url": "https://ieeexplore.ieee.org/document/10345571",
        },
        reason_code="browser_extension_required",
    )
    assert handoff["acquisition_path"] == "extension_required"
    assert handoff["open_url"] == "https://ieeexplore.ieee.org/document/10345571"
    assert "chromewebstore.google.com" in handoff["extension"]["chrome_webstore_url"]
    assert handoff["extension"]["dev_zip_url"].endswith("/downloads/mdtero-extension-dev.zip")
    assert any("Install the Mdtero extension" in step for step in handoff["steps"])


def test_attach_extension_handoff_on_challenge_reason():
    assert reason_needs_extension_handoff("client_acquisition_challenge_page")
    payload = attach_extension_handoff(
        {"status": "failed", "reason_code": "client_acquisition_challenge_page"},
        input_value="https://ieeexplore.ieee.org/document/5206848",
        route={"requires_raw_upload": True, "requires_browser_capture": False},
        reason_code="client_acquisition_challenge_page",
    )
    assert payload["extension_handoff"]["status"] == "extension_required"
    assert payload["extension_handoff"]["open_url"] == "https://ieeexplore.ieee.org/document/5206848"
    assert preferred_open_url(None, "10.1109/ACCESS.2023.3340044").startswith("https://doi.org/")
