from fastapi.testclient import TestClient

from prior.app import app
from prior.base_action import B20_FACTORY, POLICY_REGISTRY, read_b20_factory


def test_read_b20_factory_mocked(monkeypatch):
    def fake_eth_call(to, data, url=None):
        if to == B20_FACTORY:
            return "0x" + "0" * 64
        if to == POLICY_REGISTRY:
            return "0x" + "0" * 63 + "1"
        return "0x"

    monkeypatch.setattr("prior.base_action._eth_call", fake_eth_call)
    res = read_b20_factory(url="https://mainnet.base.org")
    assert res["ok"] is True
    assert res["isB20_factory"] == "0x" + "0" * 64
    assert res["policyExists_0"] == "0x" + "0" * 63 + "1"
    assert res["qualifies_as"] == "B20 read"


def test_base_verify_endpoint(monkeypatch):
    def fake_eth_call(to, data, url=None):
        if to == B20_FACTORY:
            return "0x" + "0" * 64
        if to == POLICY_REGISTRY:
            return "0x" + "0" * 63 + "1"
        return "0x"

    monkeypatch.setattr("prior.base_action._eth_call", fake_eth_call)
    client = TestClient(app)
    response = client.get("/api/base/verify?network=mainnet")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["factory"] == B20_FACTORY
    assert data["policy_registry"] == POLICY_REGISTRY
    assert data["network_name"] == "Base Mainnet"
