from noodle.plugins.ble.adapter import explain_error


def test_radio_off_on_windows():
    err = OSError("[WinError -2147020577] The device is not ready for use")
    err.winerror = -2147020577
    assert "switched off" in explain_error(err)


def test_no_adapter_and_unknown():
    assert "No Bluetooth adapter" in explain_error(RuntimeError("No Bluetooth adapters found."))
    assert explain_error(RuntimeError("boom")) == "boom"


def test_zigbee_without_broker_explains_what_is_missing(tmp_path):
    import asyncio

    import pytest

    from noodle.hub import Hub
    from noodle.plugins.zigbee.adapter import ZigbeeAdapter
    from noodle.store import Store

    adapter = ZigbeeAdapter(Hub(Store(tmp_path / "db.sqlite")))
    adapter.error = "Connection refused"
    with pytest.raises(RuntimeError, match="Cannot reach an MQTT broker at .*Connection refused.*Zigbee2MQTT"):
        asyncio.run(adapter.search(1, lambda *a, **k: None))
