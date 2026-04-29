import pytest
import logging
from click.testing import CliRunner
from cloudmesh.ai.command.vpn import vpn_group

# Set logging level to DEBUG to capture logger.debug calls in tests
logging.getLogger("vpn").setLevel(logging.DEBUG)

@pytest.fixture
def runner():
    return CliRunner()

def test_vpn_connect(runner, caplog):
    """Test the connect command and its options."""
    # Test basic connect
    result = runner.invoke(vpn_group, ["connect"])
    assert result.exit_code == 0
    assert "[VPN] Connecting to service: Default..." in caplog.text
    assert "[VPN] Connection established (Mock)." in caplog.text

    # Test connect with options
    result = runner.invoke(vpn_group, [
        "connect", 
        "--service", "my-service", 
        "--provider", "openconnect", 
        "--profile", "work",
        "-v"
    ])
    assert result.exit_code == 0
    assert "Connecting to service: my-service" in caplog.text
    assert "Provider: openconnect" in caplog.text
    assert "Profile: work" in caplog.text
    assert "Debug: True" in caplog.text

def test_vpn_connect_alias(runner, caplog):
    """Test the '+' alias for connect."""
    result = runner.invoke(vpn_group, ["+"])
    assert result.exit_code == 0
    assert "[VPN] Connecting to service: Default..." in caplog.text

def test_vpn_disconnect(runner, caplog):
    """Test the disconnect command."""
    result = runner.invoke(vpn_group, ["disconnect"])
    assert result.exit_code == 0
    assert "[VPN] Disconnecting..." in caplog.text
    assert "[VPN] Disconnected (Mock)." in caplog.text

def test_vpn_disconnect_alias(runner, caplog):
    """Test the '-' alias for disconnect."""
    result = runner.invoke(vpn_group, ["-"])
    assert result.exit_code == 0
    assert "[VPN] Disconnecting..." in caplog.text

def test_vpn_status(runner, caplog):
    """Test the status command."""
    # Test basic status
    result = runner.invoke(vpn_group, ["status"])
    assert result.exit_code == 0
    assert "True" in result.output

    # Test status with debug
    result = runner.invoke(vpn_group, ["status", "-v"])
    assert result.exit_code == 0
    assert "[VPN] VPN status check" in caplog.text

def test_vpn_info(runner, caplog):
    """Test the info command."""
    result = runner.invoke(vpn_group, ["info"])
    assert result.exit_code == 0
    assert "[VPN Info] Location: UVA Campus" in caplog.text
    assert "[VPN Info] IP: 128.118.x.x" in caplog.text

def test_vpn_reset(runner, caplog):
    """Test the reset command."""
    # Default reset
    result = runner.invoke(vpn_group, ["reset"])
    assert result.exit_code == 0
    assert "Resetting credentials for service: default" in caplog.text

    # Specific service reset
    result = runner.invoke(vpn_group, ["reset", "--service", "my-vpn"])
    assert result.exit_code == 0
    assert "Resetting credentials for service: my-vpn" in caplog.text

def test_vpn_watch(runner, caplog):
    """Test the watch command."""
    # Test basic watch
    result = runner.invoke(vpn_group, ["watch", "30"])
    assert result.exit_code == 0
    assert "Watching connection every 30 seconds" in caplog.text
    assert "Monitoring... (Press Ctrl+C to stop)" in caplog.text

    # Test watch with count
    result = runner.invoke(vpn_group, ["watch", "30", "--count", "5"])
    assert result.exit_code == 0
    assert "Watching connection every 30 seconds" in caplog.text
    assert "Monitoring for 5 iterations" in caplog.text

def test_vpn_keychain(runner, caplog):
    """Test the keychain command."""
    # Test add (default)
    result = runner.invoke(vpn_group, ["keychain"])
    assert result.exit_code == 0
    assert "Adding private key passphrase to macOS Keychain" in caplog.text
    assert "Keychain add completed (Mock)" in caplog.text

    # Test remove
    result = runner.invoke(vpn_group, ["keychain", "remove"])
    assert result.exit_code == 0
    assert "Removing private key passphrase from macOS Keychain" in caplog.text
    assert "Keychain remove completed (Mock)" in caplog.text

def test_vpn_profile(runner, caplog):
    """Test the profile command."""
    # Test list
    result = runner.invoke(vpn_group, ["profile", "list"])
    assert result.exit_code == 0
    assert "Profile action: list" in caplog.text
    assert "Default" in caplog.text
    assert "Work-Remote" in caplog.text

    # Test add
    result = runner.invoke(vpn_group, ["profile", "add"])
    assert result.exit_code == 0
    assert "Profile add completed (Mock)" in caplog.text

    # Test remove
    result = runner.invoke(vpn_group, ["profile", "remove"])
    assert result.exit_code == 0
    assert "Profile remove completed (Mock)" in caplog.text