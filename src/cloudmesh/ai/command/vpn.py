"""
Cloudmesh AI VPN Extension
==========================

This extension manages VPN connections, profiles, and keys.

Usage:
      vpn connect [--service=SERVICE] [--timeout=TIMEOUT]
                  [-v] [--choco] [--nosplit] [--provider=PROVIDER] [--profile=PROFILE]
      vpn + [--service=SERVICE] [--timeout=TIMEOUT]
            [-v] [--choco] [--nosplit] [--provider=PROVIDER] [--profile=PROFILE]
      vpn disconnect [-v]
      vpn - [-v]
      vpn status [-v]
      vpn info
      vpn reset [--service=SERVICE]
      vpn watch [INTERVAL] [--count=COUNT]
      vpn keychain [remove]
      vpn profile [add|remove|list]

Options:
      -v                    debug [default: False]
      --choco               installs chocolatey [default: False]
      --provider=PROVIDER   vpn provider for macOS (openconnect-decrypted,
                            openconnect-keychain, openconnect) [default: openconnect-decrypted]

Description:
      vpn info
         prints out information about your current location as
         obtained via the vpn connection.

      vpn status
         prints out "True" if the vpn is connected
         and "False" if it is not.

      vpn disconnect
      vpn -
         disconnects from the VPN.

      vpn connect [--service=SERVICE]
      vpn +
         connects to the UVA Anywhere VPN.

         If the VPN is already connected a warning is shown.

         You can connect to other VPNs while specifying their names
         as given to you by the VPN provider with e service option.

      vpn reset [--service=SERVICE]
         clears the credentials for the VPN service

      vpn watch [INTERVAL] [--count=COUNT]
         monitors the VPN connection at a given interval.

         The count option specifies how many times to check before stopping.

      vpn keychain
         securely adds the VPN private key passphrase to the macOS Keychain.

      vpn keychain remove
         removes the VPN private key passphrase from the macOS Keychain.

      vpn profile [add|remove|list]
         manages user-specific connection profiles.
"""

import click
import logging
import sys
import os
import webbrowser
import requests
import re
from cloudmesh.ai.common.logging_utils import get_contextual_logger
from cloudmesh.ai.common.io import console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.padding import Padding
from rich.box import ROUNDED
from rich.console import Group, Console
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn
from cloudmesh.ai.vpn.vpn import Vpn
from cloudmesh.ai.vpn import profiles

# Initialize Logger
logger = get_contextual_logger("vpn")


@click.group()
def vpn_group():
    """
    This command manages the vpn connection.
    """
    pass


# Internal helpers removed in favor of Vpn class


from cloudmesh.ai.vpn.vpn import Vpn, VpnDependencyError

def _connect_logic(service, timeout, debug, choco, nosplit, provider, profile):
    if debug:
        logger.setLevel(logging.DEBUG)

    logger.debug(f"[VPN] Connecting to service: {service if service else 'Default'}...")
    logger.debug(f"      Provider: {provider}")
    logger.debug(f"      Profile: {profile if profile else 'Default'}")
    logger.debug(f"      Timeout: {timeout}")
    logger.debug(f"      Debug: {debug}, Choco: {choco}, NoSplit: {nosplit}")

    try:
        vpn = Vpn(
            service=service,
            timeout=timeout,
            debug=debug,
            provider=provider,
            profile_name=profile,
        )

        if choco:
            vpn.strategy.check_dependencies(choco=True)

        # Connect to VPN with granular progress
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            task = progress.add_task(description="Initializing...", total=None)
            
            def progress_callback(msg: str):
                progress.update(task, description=msg)

            vpn.connect({"nosplit": nosplit}, progress_callback=progress_callback)
    except VpnDependencyError as e:
        console.error(str(e))
        return

    logger.debug("[VPN] Connection process completed.")


@vpn_group.command(name="connect")
@click.option("--service", default=None, help="VPN service name.")
@click.option("--timeout", default=None, help="Connection timeout.")
@click.option("-v", "debug", is_flag=True, default=False, help="Debug mode.")
@click.option("--choco", is_flag=True, default=False, help="Install chocolatey.")
@click.option("--nosplit", is_flag=True, default=False, help="Disable split tunneling.")
@click.option(
    "--provider", default="openconnect-decrypted", help="VPN provider for macOS."
)
@click.option("--profile", default=None, help="VPN profile to use.")
def connect_cmd(service, timeout, debug, choco, nosplit, provider, profile):
    """
    Connects to the UVA Anywhere VPN.

    If the VPN is already connected a warning is shown.
    You can connect to other VPNs while specifying their names
    as given to you by the VPN provider with e service option.
    """
    _connect_logic(service, timeout, debug, choco, nosplit, provider, profile)


@vpn_group.command(name="+")
@click.option("--service", default=None, help="VPN service name.")
@click.option("--timeout", default=None, help="Connection timeout.")
@click.option("-v", "debug", is_flag=True, default=False, help="Debug mode.")
@click.option("--choco", is_flag=True, default=False, help="Install chocolatey.")
@click.option("--nosplit", is_flag=True, default=False, help="Disable split tunneling.")
@click.option(
    "--provider", default="openconnect-decrypted", help="VPN provider for macOS."
)
@click.option("--profile", default=None, help="VPN profile to use.")
def connect_alias_cmd(service, timeout, debug, choco, nosplit, provider, profile):
    """Alias for 'connect'"""
    _connect_logic(service, timeout, debug, choco, nosplit, provider, profile)


def _disconnect_logic(debug):
    if debug:
        logger.setLevel(logging.DEBUG)
    logger.debug(f"[VPN] Disconnecting... (Debug: {debug})")

    vpn = Vpn(debug=debug)
    vpn.disconnect()

    logger.debug("[VPN] Disconnection process completed.")


@vpn_group.command(name="disconnect")
@click.option("-v", "debug", is_flag=True, default=False, help="Debug mode.")
def disconnect_cmd(debug):
    """Disconnects from the VPN."""
    _disconnect_logic(debug)


@vpn_group.command(name="-")
@click.option("-v", "debug", is_flag=True, default=False, help="Debug mode.")
def disconnect_alias_cmd(debug):
    """Alias for 'disconnect'"""
    _disconnect_logic(debug)


@vpn_group.command(name="status")
@click.option("-v", "debug", is_flag=True, default=False, help="Debug mode.")
def status_cmd(debug):
    """
    Prints out "True" if the vpn is connected
    and "False" if it is not.
    """
    if debug:
        logger.setLevel(logging.DEBUG)

    vpn = Vpn(debug=debug)
    enabled = vpn.enabled()
    console.print(str(enabled))

    if debug:
        logger.debug(f"[VPN] VPN status check: enabled={enabled}")


@vpn_group.command(name="info")
@click.option("-v", "debug", is_flag=True, default=False, help="Debug mode.")
def info_cmd(debug):
    """
    Prints out information about your current location as
    obtained via the vpn connection.
    """
    if debug:
        logger.setLevel(logging.DEBUG)

    vpn = Vpn(debug=debug)
    vpn.info()

    if debug:
        logger.debug("[VPN Info] IP information retrieved and displayed.")


@vpn_group.command(name="reset")
@click.option("--service", default=None, help="VPN service to reset.")
@click.option("-v", "debug", is_flag=True, default=False, help="Debug mode.")
def reset_cmd(service, debug):
    """Clears the credentials for the VPN service."""
    if debug:
        logger.setLevel(logging.DEBUG)

    target = service if service else "default"
    logger.debug(f"Resetting credentials for service: {target}")

    vpn = Vpn(debug=debug)
    if vpn.reset_routes(service):
        console.ok(f"Successfully reset routes for {target}")
    else:
        console.error(f"Failed to reset routes for {target}")

    logger.debug("[VPN] Route reset process completed.")


@vpn_group.command(name="watch")
@click.argument("interval", default="10")
@click.option("--count", default=None, help="Number of times to check before stopping.")
@click.option("-v", "debug", is_flag=True, default=False, help="Debug mode.")
def watch_cmd(interval, count, debug):
    """Monitors the VPN connection at a given interval."""
    if debug:
        logger.setLevel(logging.DEBUG)

    import time

    try:
        interval_val = int(interval)
    except ValueError:
        console.error("Interval must be an integer.")
        return

    logger.debug(f"[VPN] Watching connection every {interval_val} seconds...")
    if count:
        logger.debug(f"[VPN] Monitoring for {count} iterations.")
    elif os.environ.get("VPN_MOCK") == "1":
        count = 1
        logger.debug(f"[VPN] Monitoring... (Press Ctrl+C to stop)")
        logger.debug(f"[VPN] Mock mode: limiting to {count} iteration.")
    else:
        logger.debug("[VPN] Monitoring... (Press Ctrl+C to stop)")

    vpn = Vpn(debug=debug)
    iteration = 0

    from rich.console import Group

    try:
        # Use auto_refresh=False to have tighter control over when the screen updates
        with Live(console=console, refresh_per_second=1, auto_refresh=False) as live:
            while True:
                iteration += 1

                # Build the content
                banner_panel = console.create_banner(
                    "VPN Watch", f"Iteration: {iteration} | Service: {vpn.service}"
                )

                try:
                    status_msgs = vpn.watch()
                    table = Table(box=ROUNDED, expand=True)
                    table.add_column("Category")
                    table.add_column("Status")
                    for msg in status_msgs:
                        if "]" in msg:
                            category, detail = msg.split("]", 1)
                            detail = detail.strip()
                            # Dynamic Color Coding
                            lower_detail = detail.lower()
                            if any(
                                word in lower_detail
                                for word in ["connected", "success", "ok"]
                            ):
                                table.add_row(
                                    category.strip("["), f"[green]{detail}[/green]"
                                )
                            elif any(
                                word in lower_detail
                                for word in ["disconnected", "error", "failed"]
                            ):
                                table.add_row(
                                    category.strip("["), f"[red]{detail}[/red]"
                                )
                            elif any(
                                word in lower_detail
                                for word in ["connecting", "warning"]
                            ):
                                table.add_row(
                                    category.strip("["), f"[yellow]{detail}[/yellow]"
                                )
                            else:
                                table.add_row(category.strip("["), detail)
                        else:
                            table.add_row("Info", msg)
                except Exception as e:
                    logger.error(f"[VPN] Error during watch iteration {iteration}: {e}")
                    table = Table(box=ROUNDED, expand=True)
                    table.add_column("Category")
                    table.add_column("Status")
                    table.add_row("Error", f"[red]Failed to retrieve status: {e}[/red]")

                display_content = Group(banner_panel, table)

                live.update(display_content)
                live.refresh()

                if count and iteration >= int(count):
                    logger.debug(f"[VPN] Reached count limit of {count}. Stopping.")
                    break

                if os.environ.get("VPN_MOCK") != "1":
                    time.sleep(interval_val)
    except KeyboardInterrupt:
        console.info("\nVPN Watch stopped by user.")
    finally:
        pass


@vpn_group.command(name="keychain")
@click.argument("action", default="add")
@click.option("--service", default="uva", help="VPN service name.")
@click.option("-v", "debug", is_flag=True, default=False, help="Debug mode.")
def keychain_cmd(action, service, debug):
    """
    Securely adds or removes the VPN private key passphrase to the macOS Keychain.

    Actions:
      add    (default) adds the passphrase
      remove removes the passphrase
    """
    if debug:
        logger.setLevel(logging.DEBUG)

    vpn = Vpn(debug=debug)

    if action == "remove":
        logger.debug(
            f"Removing private key passphrase from macOS Keychain for {service}..."
        )
        vpn.pw_clearer(service)
    else:
        logger.debug(
            f"Adding private key passphrase to macOS Keychain for {service}..."
        )
        vpn.pw_fetcher(service)

    if os.environ.get("VPN_MOCK") == "1":
        msg = (
            "Keychain add completed (Mock)"
            if action != "remove"
            else "Keychain remove completed (Mock)"
        )
        logger.debug(msg)

    logger.debug(f"[VPN] Keychain {action} process completed for {service}.")




@vpn_group.group(name="key")
def key_group():
    """Manage VPN keys and certificates."""
    pass

@key_group.command(name="init")
@click.option("--p12", default="~/.ssh/uva/user.p12", help="Path to the user.p12 bundle.")
@click.option("--out", default="~/.ssh/uva/", help="Output directory for extracted keys.")
@click.option("-v", "debug", is_flag=True, default=False, help="Debug mode.")
def init_key_cmd(p12, out, debug):
    """Initialize VPN keys from a .p12 bundle. Extracts .crt, .key, and creates decrypted .pem."""
    if debug:
        logger.setLevel(logging.DEBUG)

    vpn = Vpn(debug=debug)
    if vpn.init_keys(p12, out):
        console.ok("VPN keys initialized successfully.")
    else:
        console.error("Failed to initialize VPN keys.")

@key_group.command(name="validate")
@click.option("--cert", default="~/.ssh/uva/user.crt", help="Path to user certificate.")
@click.option("--key", default="~/.ssh/uva/user.key", help="Path to private key.")
@click.option("--ca", default=None, help="Path to CA certificate (optional).")
@click.option("-v", "debug", is_flag=True, default=False, help="Debug mode.")
def validate_key_cmd(cert, key, ca, debug):
    """Verify that VPN certificates and keys are valid and match."""
    if debug:
        logger.setLevel(logging.DEBUG)

    vpn = Vpn(debug=debug)
    console.msg(f"Validating keys:\n  Cert: {cert}\n  Key:  {key}\n  CA:   {ca}")
    
    results = vpn.validate_keys(cert, key, ca)
    
    if not results["files_found"]:
        console.error("One or more certificate files were not found. Please check the paths.")
        return

    table = Table(
        title="VPN Key Validation Results",
        box=ROUNDED,
        show_header=True,
        header_style="bold magenta"
    )
    table.add_column("Check", style="cyan")
    table.add_column("Status", style="cyan")
    table.add_column("Detail", style="cyan")

    checks = [
        ("Expiration", "expiration"),
        ("Integrity", "integrity"),
        ("Modulus Match", "match"),
        ("Trust Chain", "trust"),
    ]

    all_ok = True
    for label, key_name in checks:
        res = results[key_name]
        status = res["status"]
        detail = res["detail"]
        
        if status == "OK":
            table.add_row(label, "[green]OK[/green]", detail)
        elif status == "FAILED":
            table.add_row(label, "[red]FAILED[/red]", detail)
            all_ok = False
        else:
            table.add_row(label, "[yellow]Unknown[/yellow]", detail)

    console.print(table)
    
    if all_ok:
        console.ok("All certificate checks passed!")
    else:
        console.error("Some certificate checks failed. Please review the table above.")

@vpn_group.command(name="profile")
@click.argument("action", type=click.Choice(["add", "remove", "list"]))
@click.option("--name", default=None, help="Profile name.")
@click.option("--service", default=None, help="VPN service for the profile.")
@click.option("-v", "debug", is_flag=True, default=False, help="Debug mode.")
def profile_cmd(action, name, service, debug):
    """
    Manages user-specific connection profiles.

    Actions:
      add    adds a new profile
      remove removes a profile
      list   lists all profiles
    """
    if debug:
        logger.setLevel(logging.DEBUG)

    if action == "list":
        logger.debug("Profile action: list")
        all_profiles = profiles.load_profiles()
        if os.environ.get("VPN_MOCK") == "1":
            all_profiles = {
                "Default": {"service": "uva"},
                "Work-Remote": {"service": "uva-remote"},
            }
            logger.debug(f"Mock profiles: {all_profiles}")

        if not all_profiles:
            console.print("No profiles found.")
        else:
            for p_name, p_data in all_profiles.items():
                console.print(f"{p_name}: {p_data}")

    elif action == "add":
        if not name or not service:
            if os.environ.get("VPN_MOCK") != "1":
                console.error(
                    "Both --name and --service are required to add a profile."
                )
                return

        logger.debug(
            f"[VPN] Adding profile {name if name else 'Default'} for service {service if service else 'uva'}..."
        )
        if os.environ.get("VPN_MOCK") == "1":
            logger.debug("Profile add completed (Mock)")
            console.ok(
                f"Profile '{name if name else 'Default'}' added successfully (Mock)."
            )
        elif profiles.add_profile(name, service):
            console.ok(f"Profile '{name}' added successfully.")
        else:
            console.error(f"Failed to add profile '{name}'.")

    elif action == "remove":
        if not name:
            if os.environ.get("VPN_MOCK") != "1":
                console.error("The --name option is required to remove a profile.")
                return

        logger.debug(f"[VPN] Removing profile {name if name else 'Default'}...")
        if os.environ.get("VPN_MOCK") == "1":
            logger.debug("Profile remove completed (Mock)")
            console.ok(
                f"Profile '{name if name else 'Default'}' removed successfully (Mock)."
            )
        elif profiles.remove_profile(name):
            console.ok(f"Profile '{name}' removed successfully.")
        else:
            console.error(f"Profile '{name}' not found.")

    logger.debug(f"[VPN] Profile {action} process completed.")


entry_point = vpn_group


def register(cli):
    cli.add_command(vpn_group, name="vpn")
