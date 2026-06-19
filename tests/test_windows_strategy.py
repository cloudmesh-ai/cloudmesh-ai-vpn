import sys
from types import SimpleNamespace

from cloudmesh.ai.vpn.strategies.windows import WindowsVpnStrategy, _extract_cert_uri


class _DummyVpn:
    verbosity = 0


def test_extract_cert_uri_matches_connection_label():
    sample = "\n".join([
        "Object Label: something else",
        "Cert URI: pkcs11:object=wrong",
        "Label: Other Org",
        "Object Label: UVA certificate",
        "Cert URI: pkcs11:object=uva-cert",
        "Label: University of Virginia",
    ])

    assert _extract_cert_uri(sample, ["University of Virginia", "UVA"]) == "pkcs11:object=uva-cert"


def test_extract_cert_uri_returns_none_when_no_match():
    sample = "\n".join([
        "Object Label: other certificate",
        "Cert URI: pkcs11:object=other-cert",
        "Label: Some Other School",
    ])

    assert _extract_cert_uri(sample, ["University of Virginia", "UVA"]) is None


def test_get_system_cert_uri_uses_org_match_terms(monkeypatch):
    sample = "\n".join([
        "Object Label: school certificate",
        "Cert URI: pkcs11:object=uva-cert",
        "Label: University of Virginia",
    ])

    class _Shell:
        @staticmethod
        def run(command):
            assert command == "list-system-keys"
            return sample

    monkeypatch.setattr("cloudmesh.ai.common.Shell.run", _Shell.run)
    monkeypatch.setattr("cloudmesh.ai.vpn.strategies.windows.os_is_windows", lambda: True)

    strategy = WindowsVpnStrategy(_DummyVpn())
    org_config = {
        "name": "UVA Anywhere",
        "domain": "virginia.edu",
        "connection_check": ["University of Virginia", "UVA"],
    }

    assert strategy._get_system_cert_uri(org_config) == "pkcs11:object=uva-cert"


def test_connect_returns_false_when_openconnect_exits_during_startup(monkeypatch):
    class _Proc:
        def __init__(self):
            self.pid = 4321
            self.returncode = 1
            self.stdin = None

        def poll(self):
            return self.returncode

    monkeypatch.setitem(sys.modules, "pyuac", SimpleNamespace(isUserAdmin=lambda: True))
    monkeypatch.setattr("cloudmesh.ai.vpn.strategies.windows.get_openconnect_exe", lambda: r"C:\fake\openconnect.exe")
    monkeypatch.setattr("cloudmesh.ai.vpn.strategies.windows.ensure_choco_bin_on_process_path", lambda: None)
    monkeypatch.setattr("cloudmesh.ai.vpn.strategies.windows.os.path.exists", lambda path: True)
    monkeypatch.setattr("cloudmesh.ai.vpn.strategies.windows.time.sleep", lambda _: None)
    monkeypatch.setattr("cloudmesh.ai.vpn.strategies.windows.subprocess.Popen", lambda *args, **kwargs: _Proc())

    strategy = WindowsVpnStrategy(_DummyVpn())
    monkeypatch.setattr(strategy, "_stop_vpn_services", lambda: None)
    monkeypatch.setattr(strategy, "_get_system_cert_uri", lambda org_config: "system:win:id=test-cert;type=cert")

    result = strategy.connect({}, "uva", no_split=True)

    assert result is False
    assert strategy._pid is None
