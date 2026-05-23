#!/usr/bin/env python3
"""
First-time setup helper.
Copies config.example.ini → config.ini and stores a salted admin password hash.
Uses only the Python standard library — safe to run before pip install.
"""
import configparser
import getpass
import hashlib
import shutil
import time
from pathlib import Path

CONFIG_FILE = Path("config.ini")
CONFIG_EXAMPLE = Path("config.example.ini")


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

    # salt = Unix timestamp at setup time; stored alongside the hash
    salt = str(int(time.time()))
    hashed = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()

    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_FILE)
    cfg["auth"]["admin_hashed_password"] = hashed
    cfg["auth"]["admin_salt"] = salt

    with CONFIG_FILE.open("w") as fh:
        cfg.write(fh)

    print("Admin credentials saved to config.ini.")


if __name__ == "__main__":
    main()
