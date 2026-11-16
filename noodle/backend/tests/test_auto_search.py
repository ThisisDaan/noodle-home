from noodle import plugins


def test_searches_start_by_themselves_except_zigbee_pairing():
    found = {p.id: p for p in plugins.discover()}
    assert found["zigbee"].auto_search is False
    assert all(p.auto_search for p in found.values() if p.searchable and p.id != "zigbee")
