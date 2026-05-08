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


def _connect_logic(service, timeout, debug, choco, nosplit, provider, profile):
    if debug:
        logger.setLevel(logging.DEBUG)

    logger.debug(f"[VPN] Connecting to service: {service if service else 'Default'}...")
    logger.debug(f"      Provider: {provider}")
    logger.debug(f"      Profile: {profile if profile else 'Default'}")
    logger.debug(f"      Timeout: {timeout}")
    logger.debug(f"      Debug: {debug}, Choco: {choco}, NoSplit: {nosplit}")

    if choco:
        vpn_checker = Vpn(debug=debug)
        vpn_checker.anyconnect_checker(choco=True)

    vpn = Vpn(
        service=service,
        timeout=timeout,
        debug=debug,
        provider=provider,
        profile_name=profile,
    )

    # The Vpn.connect method handles the actual connection logic
    vpn.connect({"nosplit": nosplit})
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


def _query_llm_for_ranges(org):
    """Query a vLLM server for VPN IP ranges."""
    try:
        host = os.environ.get("VLLM_HOST", "localhost")
        port = os.environ.get("VLLM_PORT", "8000")
        url = f"http://{host}:{port}/v1/chat/completions"
        prompt = f"What are the public VPN IP ranges (CIDR) for {org}? Provide only the CIDR ranges as a comma-separated list. If unknown, say 'Unknown'."
        payload = {
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        }
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"].strip()
        if "Unknown" in content:
            return []
        # Match CIDR (1.2.3.0/24) or Range (1.2.3.0 - 1.2.3.255)
        cidr_regex = r"\b\d{1,3}(?:\.\d{1,3}){3}/\d{1,2}\b"
        range_regex = r"\b\d{1,3}(?:\.\d{1,3}){3}\s*-\s*\d{1,3}(?:\.\d{1,3}){3}\b"
        return re.findall(cidr_regex, content)
    except Exception as e:
        logger.debug(f"LLM query failed: {e}")
        return []


def _fetch_asn_ranges(org):
    """Fetch IP ranges using ASN lookup via BGPView API."""
    try:
        # 1. Try to find the ASN for the organization
        # We use a search query to BGPView or a similar service
        # For simplicity and reliability, we'll use the BGPView ASN search
        search_url = f"https://api.bgpview.io/search?query={org}"
        response = requests.get(search_url, timeout=5)
        response.raise_for_status()
        results = response.json().get("results", [])
        
        if not results:
            return []
            
        # Take the first ASN result
        asn = results[0].get("asn")
        if not asn:
            return []
            
        logger.debug(f"[ASN] Found ASN {asn} for {org}")
        
        # 2. Get prefixes for this ASN
        prefix_url = f"https://api.bgpview.io/asn/{asn}/prefixes"
        prefix_resp = requests.get(prefix_url, timeout=5)
        prefix_resp.raise_for_status()
        prefixes_data = prefix_resp.json().get("ipv4_prefixes", [])
        
        ranges = [p.get("prefix") for p in prefixes_data if p.get("prefix")]
        return ranges
    except Exception as e:
        logger.debug(f"ASN lookup failed for {org}: {e}")
        return []

def _fetch_searxng_ranges(query):
    """Fetch IP ranges using SearXNG JSON API with fallback instances."""
    # List of public SearXNG instances to try if the primary one fails
    instances = [
        os.environ.get("SEARXNG_URL", "https://searx.be"),
        "https://searx.space",
        "https://searxng.be",
        "https://priv.searx.be",
    ]

    cidr_regex = r"\b\d{1,3}(?:\.\d{1,3}){3}/\d{1,2}\b"

    for base_url in instances:
        try:
            url = f"{base_url}/search"
            params = {"q": query, "format": "json", "engines": "google,bing,duckduckgo"}
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                results = response.json().get("results", [])
                found = set()
                for res in results:
                    text = f"{res.get('title', '')} {res.get('content', '')}"
                    found.update(re.findall(cidr_regex, text))
                    found.update(re.findall(range_regex, text))
                if found:
                    return list(found)
        except Exception as e:
            logger.debug(f"SearXNG instance {base_url} failed: {e}")

    return []


def _fetch_ip_ranges(query, org):
    """Hybrid approach: Known data -> ASN Lookup -> SearXNG -> LLM -> Advanced Scraper."""
    # 1. Known data (High confidence)
    known_data = {
        "virginia.edu": ["128.143.0.0/16", "137.54.0.0/16"],
        "uva.edu": ["128.143.0.0/16", "137.54.0.0/16"],
        "mit.edu": ["18.0.0.0/8"],
        "stanford.edu": ["171.64.0.0/14"],
        "flu.edu": ["134.110.0.0/16"],
    }
    for k, v in known_data.items():
        if k in query.lower() or k in org.lower():
            return v

    # 2. ASN Lookup (Authoritative Network Data)
    asn_ranges = _fetch_asn_ranges(org)
    if asn_ranges:
        return asn_ranges

    # 3. SearXNG Metasearch (Structured API)
    searx_ranges = _fetch_searxng_ranges(query)
    if searx_ranges:
        return searx_ranges

    # 3. LLM Query (If server is available)
    llm_ranges = _query_llm_for_ranges(org)
    if llm_ranges:
        return llm_ranges

    # 4. Advanced Scraper Fallback
    found_ranges = set()
    search_targets = [
        (
            f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}",
            "DuckDuckGo",
        ),
        (
            f"https://html.duckduckgo.com/html/?q={org.replace(' ', '+')}+vpn+cidr",
            "DuckDuckGo CIDR",
        ),
    ]
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    for url, name in search_targets:
        try:
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                cidr_regex = r"\b\d{1,3}(?:\.\d{1,3}){3}/\d{1,2}\b"
                range_regex = r"\b\d{1,3}(?:\.\d{1,3}){3}\s*-\s*\d{1,3}(?:\.\d{1,3}){3}\b"
                found_ranges.update(re.findall(cidr_regex, response.text))
                found_ranges.update(re.findall(range_regex, response.text))
        except Exception:
            pass

    return list(found_ranges)


@vpn_group.command(name="search")
@click.argument("org")
@click.option("-v", "debug", is_flag=True, default=False, help="Debug mode.")
def search_cmd(org, debug):
    """
    Search the internet for VPN IP ranges of a given organization.
    """
    if debug:
        logger.setLevel(logging.DEBUG)

    query = f"{org} vpn ip ranges"
    url = f"https://www.google.com/search?q={query.replace(' ', '+')}"

    logger.info(f"[VPN Search] Searching for: {query}")

    # AI-style "Thinking" animation
    with Live(console=console, refresh_per_second=4, transient=True) as live:
        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠴", "⠦", "⠧", "⠇", "⠏"]
        steps = [
            f"Analyzing {org} network patterns...",
            "Performing ASN lookup...",
            "Querying SearXNG metasearch...",
            "Consulting LLM knowledge base...",
            "Parsing CIDR ranges from results...",
        ]
        for i in range(20):
            step = steps[(i // 5) % len(steps)]
            live.update(f"[bold blue]{frames[i % len(frames)]} {step}[/bold blue]")
            import time

            time.sleep(0.1)

        found_ranges = _fetch_ip_ranges(query, org)

    # ASCII Presentation
    ranges_text = (
        "\n".join([f"  - {r}" for r in found_ranges])
        if found_ranges
        else "  No ranges found automatically. Check browser."
    )

    ascii_banner = f"""
    +-------------------------------------------------------+
    |                VPN ORGANIZATION SEARCH                |
    +-------------------------------------------------------+
    | Organization: {org:<35} |
    | Search Query: {query:<35} |
    |                                                       |
    | Found IP Ranges:                                      |
    {ranges_text}
    |                                                       |
    | Action:       Opening Web Browser for AI Overview...   |
    +-------------------------------------------------------+
    """
    console.print(ascii_banner)

    webbrowser.open(url)


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
