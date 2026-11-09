from noodle.plugins.ble.adapter import explain_error


def test_radio_off_on_windows():
    err = OSError("[WinError -2147020577] The device is not ready for use")
    err.winerror = -2147020577
    assert "switched off" in explain_error(err)


def test_no_adapter_and_unknown():
    assert "No Bluetooth adapter" in explain_error(RuntimeError("No Bluetooth adapters found."))
    assert explain_error(RuntimeError("boom")) == "boom"
