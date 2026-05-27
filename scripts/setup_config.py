#!/usr/bin/env python3
"""
First-time setup helper.
Copies config.example -> config.ini and stores admin auth settings.
Uses only the Python standard library — safe to run before pip install.
"""
import configparser
import getpass
import hashlib
import secrets
import shutil
from pathlib import Path

CONFIG_FILE = Path("config.ini")
CONFIG_EXAMPLE = Path("config.example")


def main() -> None:
    if CONFIG_FILE.exists():
        print(f"{CONFIG_FILE} already exists — skipping config setup.")
        return

    if not CONFIG_EXAMPLE.exists():
        print(f"ERROR: {CONFIG_EXAMPLE} not found. Cannot continue.")
        raise SystemExit(1)

    print(f"Copying {CONFIG_EXAMPLE} → {CONFIG_FILE} ...")
    shutil.copy(CONFIG_EXAMPLE, CONFIG_FILE)

    # Prompt for admin password (hidden input, never touches the process list)
    while True:
        password = getpass.getpass("Set administrator password: ")
        if not password:
            print("Password cannot be empty, try again.")
            continue
        confirm = getpass.getpass("Confirm administrator password: ")
        if password == confirm:
            break
        print("Passwords do not match, try again.")

    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_FILE)

    if "auth" not in cfg:
        cfg["auth"] = {}

    # Admin username is fixed in code to "document-admin".
    cfg["auth"]["admin_password_hash"] = hashlib.sha256(password.encode()).hexdigest()
    cfg["auth"]["admin_jwt_salt"] = secrets.token_hex(32)

    with CONFIG_FILE.open("w") as fh:
        cfg.write(fh)

    print("Admin auth settings saved to config.ini.")


if __name__ == "__main__":
    main()
