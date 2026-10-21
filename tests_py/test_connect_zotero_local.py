from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from mdtero.connect import zotero_local
from mdtero.connect.security import ZOTERO_LOCAL_BASE


def test_connector_status_unreachable():
    with patch("mdtero.connect.zotero_local.httpx.Client") as client_cls:
        client = MagicMock()
        client.__enter__.return_value = client
        client.get.side_effect = httpx.ConnectError("down")
        client_cls.return_value = client
        status = zotero_local.connector_status()
    assert status["available"] is False
    assert status["base_url"] == ZOTERO_LOCAL_BASE
    assert status["reason_code"] == "zotero_connector_unreachable"


def test_collection_key_validation():
    with pytest.raises(zotero_local.ZoteroLocalError):
        zotero_local.collection_items_preview("../secret")
