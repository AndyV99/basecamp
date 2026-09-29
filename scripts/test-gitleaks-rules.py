#!/usr/bin/env python3
"""Regression test for .gitleaks.toml: plant fake credentials, assert what fires.

Every credential shape this repository is likely to handle gets a fixture, and
each fixture declares the rule that must catch it. A second set of fixtures
must stay clean (placeholders, SOPS-encrypted files), because a scanner that
cries wolf on every encrypted secret in a GitOps repo gets bypassed.

Why this exists: a gitleaks rule can stop firing without anyone noticing. An
upstream release renames or tightens a bundled rule, or an edit to a custom
regex breaks it, and the full-history scan keeps reporting "no leaks found",
because there are none to find. Only a planted credential distinguishes "clean"
from "not looking".

Fixtures are generated at runtime with random values and written to a temp
directory, never committed. A committed fixture would itself have to be
allowlisted, which is the kind of exemption this test is meant to keep honest.

Usage:  scripts/test-gitleaks-rules.py
Exit:   0 all expectations met, 1 otherwise.
"""

import base64
import json
import os
import secrets
import string
import subprocess
import sys
import tempfile

ROOT = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
GITLEAKS = os.path.join(ROOT, "scripts", "gitleaks.sh")

ALNUM = string.ascii_letters + string.digits
BECH32 = "qpzry9x8gf2tvdw0s3jn54khce6mua7l".upper()


def rand(alphabet: str, n: int) -> str:
    return "".join(secrets.choice(alphabet) for _ in range(n))


def b64(n: int) -> str:
    return base64.b64encode(secrets.token_bytes(n)).decode()


def tunnel_token() -> str:
    # cloudflared serialises compactly: no spaces, so the token always starts
    # eyJhIjoi. json.dumps' default separators would add a space and produce a
    # shape real tokens never have.
    body = {"a": secrets.token_hex(16), "t": "6ff42ae2-765d-4adf-8112-31c55c1551ef", "s": b64(32)}
    return base64.b64encode(json.dumps(body, separators=(",", ":")).encode()).decode()


def k3s_token() -> str:
    return f"K10{secrets.token_hex(32)}::server:{secrets.token_hex(16)}"


def pem_b64(kind: str, n: int) -> str:
    pem = f"-----BEGIN {kind}-----\n{b64(n)}\n-----END {kind}-----\n"
    return base64.b64encode(pem.encode()).decode()


# filename -> (content, rule that must fire)
MUST_FIRE = {
    # Custom rules (.gitleaks.toml)
    "dsn.md": (f"connect with postgres://app:{rand(ALNUM, 14)}@db.internal:5432/app\n",
               "basecamp-datastore-url-inline-credential"),
    "redis-dsn.yaml": (f"url: rediss://:{rand(ALNUM, 20)}@valkey.data.svc:6379/0\n",
                       "basecamp-datastore-url-inline-credential"),
    "k3s-token.sh": (f"export K3S_TOKEN={k3s_token()}\n", "basecamp-k3s-token"),
    "k3s-config.yaml": (f"token: {k3s_token()}\n", "basecamp-k3s-token"),
    "tailscale.env": (f"TS_AUTHKEY=tskey-auth-k{rand(ALNUM, 16)}CNTRL-{rand(ALNUM, 33)}\n",
                      "basecamp-tailscale-key"),
    "tunnel-bare.yaml": (f"data:\n  value: {tunnel_token()}\n", "basecamp-cloudflare-tunnel-token"),
    # Bundled rules this repo depends on. If upstream renames or drops one of
    # these, the test fails and says which, instead of the shape going unscanned.
    "age.key.txt": (f"# public key: age1example\nAGE-SECRET-KEY-1{rand(BECH32, 58)}\n", "age-secret-key"),
    "aws.env": (f"AWS_ACCESS_KEY_ID=AKIA{rand(string.ascii_uppercase + '234567', 16)}\n", "aws-access-token"),
    "kubeconfig.yaml": ("users:\n- name: default\n  user:\n"
                        f"    client-key-data: {pem_b64('EC PRIVATE KEY', 90)}\n", "private-key"),
}

# filename -> content that must raise nothing
MUST_STAY_CLEAN = {
    "dsn-placeholders.md": "postgres://app:${DB_PASSWORD}@db:5432/app\n"
                           "redis://:<password>@valkey:6379\n"
                           "postgres://{{ .Values.user }}:{{ .Values.password }}@db/app\n",
    "sops-encrypted.yaml": (
        "apiVersion: v1\nkind: Secret\nmetadata:\n    name: app\nstringData:\n"
        f"    password: ENC[AES256_GCM,data:{b64(18)},iv:{b64(32)},tag:{b64(16)},type:str]\n"
        "sops:\n    age:\n"
        "        - recipient: age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p\n"
        "          enc: |\n            -----BEGIN AGE ENCRYPTED FILE-----\n"
        f"            {b64(120)}\n            -----END AGE ENCRYPTED FILE-----\n"
        f"    mac: ENC[AES256_GCM,data:{b64(48)},iv:{b64(32)},tag:{b64(16)},type:str]\n"
    ),
}


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        fixtures = os.path.join(tmp, "fixtures")
        os.mkdir(fixtures)
        for name, content in {**{k: v[0] for k, v in MUST_FIRE.items()}, **MUST_STAY_CLEAN}.items():
            with open(os.path.join(fixtures, name), "w") as f:
                f.write(content)

        report = os.path.join(tmp, "report.json")
        # --redact: the values are fake, but a habit of printing matches in CI
        # logs is the habit this repo is trying not to have.
        proc = subprocess.run(
            [GITLEAKS, "dir", "--no-banner", "--redact", "--exit-code", "0",
             "--report-format", "json", "--report-path", report, fixtures],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            print("gitleaks failed to run:\n" + proc.stderr, file=sys.stderr)
            return 1

        with open(report) as f:
            findings = json.load(f)

    fired: dict[str, set[str]] = {}
    for finding in findings:
        fired.setdefault(os.path.basename(finding["File"]), set()).add(finding["RuleID"])

    failures = []
    for name, (_, rule) in MUST_FIRE.items():
        got = fired.get(name, set())
        status = "ok  " if rule in got else "FAIL"
        if rule not in got:
            failures.append(name)
        print(f"{status} {name:22} expects {rule:42} got {', '.join(sorted(got)) or 'nothing'}")
    for name in MUST_STAY_CLEAN:
        got = fired.get(name, set())
        status = "ok  " if not got else "FAIL"
        if got:
            failures.append(name)
        print(f"{status} {name:22} expects {'(clean)':42} got {', '.join(sorted(got)) or 'nothing'}")

    if failures:
        print(f"\n{len(failures)} expectation(s) not met: {', '.join(failures)}", file=sys.stderr)
        return 1
    print(f"\nAll {len(MUST_FIRE) + len(MUST_STAY_CLEAN)} expectations met.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
