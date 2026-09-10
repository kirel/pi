"""Resolve only declared 1Password fields on Ailab and provision NAS via stdin.

No credentials are returned to Ansible or put in command arguments. The NAS
stores WPA2-derived PSKs, with root-only permissions. Revision tracking outside
this helper compares only public references, never resolved secret values.
"""

import hashlib
import json
import re
import subprocess
import sys


def read_field(reference):
    if not reference.startswith("op://homelab/"):
        raise ValueError("Expected a homelab secret reference")
    result = subprocess.run(
        ["/usr/local/bin/op-sa", "read", "--no-newline", reference],
        check=True, capture_output=True,
    )
    return result.stdout


def render(settings):
    country = settings["country"]
    if not re.fullmatch(r"[A-Z]{2}", country):
        raise ValueError("Invalid country code")
    lines = [
        f"country={country}",
        "ctrl_interface=DIR=/run/wpa_supplicant GROUP=netdev",
        "update_config=0",
    ]
    for profile in settings["profiles"]:
        name = profile["name"]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            raise ValueError("Invalid profile name")
        if ("ssid" in profile) == ("ssid_ref" in profile):
            raise ValueError("Provide exactly one SSID or SSID reference")
        ssid = (profile["ssid"].encode("utf-8") if "ssid" in profile
                else read_field(profile["ssid_ref"]))
        password = read_field(profile["password_ref"])
        if not 1 <= len(ssid) <= 32:
            raise ValueError("Invalid SSID length")
        if re.fullmatch(rb"[0-9a-fA-F]{64}", password):
            psk = password.decode("ascii")
        elif 8 <= len(password) <= 63:
            psk = hashlib.pbkdf2_hmac("sha1", password, ssid, 4096, 32).hex()
        else:
            raise ValueError("Invalid WPA2 passphrase length")
        lines.extend([
            "network={",
            f'    id_str="{name}"',
            f"    ssid={ssid.hex()}",
            f"    psk={psk}",
            "    key_mgmt=WPA-PSK",
            "    ieee80211w=1",
            "    scan_ssid=1",
            f"    priority={int(profile.get('priority', 0))}",
            "}",
        ])
    return ("\n".join(lines) + "\n").encode()


# Fixed receiver code: stdin carries the credentials over authenticated SSH.
RECEIVER = """
import os, sys, tempfile
directory = '/etc/wpa_supplicant'
fd, temporary = tempfile.mkstemp(prefix='.ansible-wifi-', dir=directory)
try:
    with os.fdopen(fd, 'wb') as stream:
        stream.write(sys.stdin.buffer.read())
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, directory + '/wpa_supplicant-wlan0.conf')
finally:
    if os.path.exists(temporary):
        os.unlink(temporary)
"""


def main():
    import shlex
    settings = json.loads(sys.argv[1])
    config = render(settings)
    subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
         "-o", "ConnectTimeout=15", settings["target"],
         "sudo -n python3 -c " + shlex.quote(RECEIVER)],
        input=config, capture_output=True, check=True,
    )
    print("Wi-Fi credentials provisioned")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Do not reveal subprocess output or values when provisioning fails.
        print("Wi-Fi provisioning failed; verify references and host access", file=sys.stderr)
        sys.exit(1)
