#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["websockets>=12", "pyyaml>=6"]
# ///
"""Install blueprints and dashboards from this repository into Home Assistant.

Uses the Home Assistant WebSocket API with a long-lived access token. The URL and
token are asked on first run and stored in scripts/.ha-install.env (gitignored).
"""

from __future__ import annotations

import argparse
import difflib
import getpass
import itertools
import json
import os
import ssl
import sys
from contextlib import ExitStack
from pathlib import Path
from urllib.parse import urlparse

import yaml
from websockets.sync.client import connect

REPO = Path(__file__).resolve().parent.parent
CONFIG_FILE = Path(__file__).resolve().parent / ".ha-install.env"
RAW_BASE = "https://raw.githubusercontent.com/koenhausmans/ha-automation-blueprints/master"
GITHUB_USER = "koenhausmans"
META_KEY = "x-meta"


class HAError(Exception):
    pass


# --- configuration ---------------------------------------------------------


def load_config() -> dict[str, str]:
    config = {}
    for line in CONFIG_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            config[key.strip()] = value.strip()
    return config


def save_config(config: dict[str, str]) -> None:
    content = "# Home Assistant install settings. Do not commit.\n" + "".join(
        f"{key}={value}\n" for key, value in config.items()
    )
    fd = os.open(CONFIG_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(content)
    os.chmod(CONFIG_FILE, 0o600)


def ask_config() -> dict[str, str]:
    print("Home Assistant connection setup")
    url = input("  URL (e.g. http://homeassistant.local:8123): ").strip().rstrip("/")
    if urlparse(url).scheme not in ("http", "https"):
        sys.exit("URL must start with http:// or https://")
    print("  Create a long-lived access token (admin user): Profile → Security.")
    token = getpass.getpass("  Token: ").strip()
    verify = "true"
    if url.startswith("https://"):
        answer = input("  Verify TLS certificate? [Y/n]: ").strip().lower()
        verify = "false" if answer in ("n", "no") else "true"
    return {"HA_URL": url, "HA_TOKEN": token, "HA_VERIFY_TLS": verify}


def get_config(reconfigure: bool) -> dict[str, str]:
    if CONFIG_FILE.exists() and not reconfigure:
        config = load_config()
        if config.get("HA_URL") and config.get("HA_TOKEN"):
            return config
    config = ask_config()
    with HAClient(config):
        pass  # validates URL and token before saving
    save_config(config)
    print(f"Saved settings to {CONFIG_FILE.relative_to(REPO)}\n")
    return config


# --- websocket client ------------------------------------------------------


class HAClient:
    def __init__(self, config: dict[str, str]):
        parsed = urlparse(config["HA_URL"])
        scheme = "wss" if parsed.scheme == "https" else "ws"
        self.uri = f"{scheme}://{parsed.netloc}{parsed.path.rstrip('/')}/api/websocket"
        self.token = config["HA_TOKEN"]
        self.ssl = None
        if scheme == "wss":
            self.ssl = ssl.create_default_context()
            if config.get("HA_VERIFY_TLS", "true").lower() == "false":
                self.ssl.check_hostname = False
                self.ssl.verify_mode = ssl.CERT_NONE
        self.ids = itertools.count(1)

    def __enter__(self) -> HAClient:
        self.stack = ExitStack()
        try:
            self.ws = self.stack.enter_context(
                connect(self.uri, ssl=self.ssl, max_size=None, open_timeout=10)
            )
        except OSError as err:
            raise HAError(f"Cannot connect to {self.uri}: {err}") from err
        self._recv()  # auth_required
        self.ws.send(json.dumps({"type": "auth", "access_token": self.token}))
        msg = self._recv()
        if msg.get("type") != "auth_ok":
            self.stack.close()
            raise HAError(f"Authentication failed: {msg.get('message', msg)}")
        return self

    def __exit__(self, *exc) -> None:
        self.stack.close()

    def _recv(self) -> dict:
        return json.loads(self.ws.recv(timeout=30))

    def call(self, type_: str, **payload):
        msg_id = next(self.ids)
        self.ws.send(json.dumps({"id": msg_id, "type": type_, **payload}))
        while True:
            msg = self._recv()
            if msg.get("id") == msg_id and msg.get("type") == "result":
                break
        if not msg["success"]:
            error = msg.get("error", {})
            raise HAError(f"{type_}: {error.get('code')}: {error.get('message')}")
        return msg.get("result")


# --- blueprints ------------------------------------------------------------


class _IgnoreTagsLoader(yaml.SafeLoader):
    pass


_IgnoreTagsLoader.add_multi_constructor("!", lambda loader, suffix, node: None)


def install_blueprints(ha: HAClient, files: list[Path], dry_run: bool) -> tuple[list, set]:
    results, reload_domains = [], set()
    existing: dict[str, dict] = {}
    for file in files:
        name = file.relative_to(REPO)
        try:
            content = file.read_text()
            meta = yaml.load(content, Loader=_IgnoreTagsLoader)["blueprint"]
            domain = meta["domain"]
            source_url = f"{RAW_BASE}/{name.as_posix()}"
            if domain not in existing:
                existing[domain] = ha.call("blueprint/list", domain=domain)
            path = find_blueprint_path(existing[domain], source_url) or (
                f"{GITHUB_USER}/{file.name}"
            )
            current = existing[domain].get(path, {})
            status = "updated" if current else "created"
            if not dry_run:
                ha.call(
                    "blueprint/save",
                    domain=domain,
                    path=path,
                    yaml=content,
                    source_url=source_url,
                    allow_override=True,
                )
            reload_domains.add(domain)
            results.append((name, f"{status} ({domain}/{path})"))
        except (HAError, KeyError, TypeError, yaml.YAMLError) as err:
            results.append((name, f"FAILED: {err}"))
    return results, reload_domains


def find_blueprint_path(blueprints: dict[str, dict], source_url: str) -> str | None:
    for path, info in blueprints.items():
        if info.get("metadata", {}).get("source_url") == source_url:
            return path
    return None


# --- dashboards ------------------------------------------------------------


def install_dashboards(ha: HAClient, files: list[Path], dry_run: bool, yes: bool) -> list:
    results = []
    dashboards = {d["url_path"]: d for d in ha.call("lovelace/dashboards/list")}
    for file in files:
        name = file.relative_to(REPO)
        url_path = file.stem
        try:
            config = yaml.safe_load(file.read_text()) or {}
            meta = config.pop(META_KEY, {}) or {}
            if "-" not in url_path:
                raise HAError("file name (url_path) must contain a hyphen")

            if url_path not in dashboards:
                if not dry_run:
                    ha.call(
                        "lovelace/dashboards/create",
                        url_path=url_path,
                        title=meta.get("title", url_path),
                        **{k: meta[k] for k in ("icon", "show_in_sidebar", "require_admin") if k in meta},
                    )
                    ha.call("lovelace/config/save", url_path=url_path, config=config)
                results.append((name, "created"))
                continue

            if dashboards[url_path].get("mode") == "yaml":
                raise HAError("dashboard is in YAML mode; it cannot be written via the API")
            try:
                live = ha.call("lovelace/config", url_path=url_path, force=True)
            except HAError as err:
                if "config_not_found" not in str(err):
                    raise
                live = None
            if live == config:
                results.append((name, "unchanged"))
                continue
            if live is not None and not yes:
                show_diff(live, config, url_path)
                if dry_run or input(f"Overwrite dashboard '{url_path}'? [y/N]: ").strip().lower() not in ("y", "yes"):
                    results.append((name, "skipped (differs from Home Assistant)"))
                    continue
            if not dry_run:
                ha.call("lovelace/config/save", url_path=url_path, config=config)
            results.append((name, "updated"))
        except (HAError, AttributeError, yaml.YAMLError) as err:
            results.append((name, f"FAILED: {err}"))
    return results


def show_diff(live: dict, local: dict, url_path: str) -> None:
    def dump(data):
        return yaml.safe_dump(data, sort_keys=False, allow_unicode=True).splitlines()

    diff = difflib.unified_diff(
        dump(live), dump(local), f"home-assistant/{url_path}", f"repo/{url_path}", lineterm=""
    )
    print("\n".join(itertools.islice(diff, 80)))


# --- main ------------------------------------------------------------------


def select_files(directory: str, filters: list[str]) -> list[Path]:
    files = sorted((REPO / directory).rglob("*.yaml")) if (REPO / directory).is_dir() else []
    if filters:
        wanted = {Path(f).resolve() for f in filters}
        files = [f for f in files if f.resolve() in wanted or f.name in filters or f.stem in filters]
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "target", nargs="?", default="all", choices=("all", "blueprints", "dashboards")
    )
    parser.add_argument("files", nargs="*", help="only install these files (path, name or stem)")
    parser.add_argument("--dry-run", action="store_true", help="show what would change")
    parser.add_argument("--yes", "-y", action="store_true", help="overwrite changed dashboards without asking")
    parser.add_argument("--reconfigure", action="store_true", help="ask for URL and token again")
    args = parser.parse_args()

    try:
        config = get_config(args.reconfigure)
        results: list[tuple] = []
        with HAClient(config) as ha:
            if args.target in ("all", "blueprints"):
                bp_results, domains = install_blueprints(
                    ha, select_files("blueprints", args.files), args.dry_run
                )
                results += bp_results
                for domain in sorted(domains):
                    if not args.dry_run:
                        ha.call("call_service", domain=domain, service="reload")
                    results.append((f"{domain}.reload", "called"))
            if args.target in ("all", "dashboards"):
                results += install_dashboards(
                    ha, select_files("dashboards", args.files), args.dry_run, args.yes
                )
    except HAError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print(file=sys.stderr)
        return 130

    if args.dry_run:
        print("Dry run, nothing was written.")
    if not results:
        print("Nothing to install.")
    for name, status in results:
        print(f"  {name}: {status}")
    return 1 if any(status.startswith("FAILED") for _, status in results) else 0


if __name__ == "__main__":
    sys.exit(main())
