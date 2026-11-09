"""Scoped LAN access on firmware that uses an iptables input firewall."""

import ipaddress
import json
import shlex
import shutil
import subprocess
from enum import Enum
from pathlib import Path


class FirewallState(Enum):
    CLEAN = "clean"
    INSTALLING = "installing"
    OPEN = "open"
    REMOVING = "removing"
    DIRTY = "dirty"


class PushFirewall:
    CHAIN = "KTRMNL2_PUSH"

    def __init__(self, interface):
        self.interface = interface
        self.journal = Path("/var/run/ktrmnl2-push-firewall.json")
        self.command = shutil.which("iptables")
        self.save = shutil.which("iptables-save")
        self.state = (
            FirewallState.DIRTY if self.journal.exists() else FirewallState.CLEAN
        )

    def _available(self):
        tables = Path("/proc/net/ip_tables_names")
        if (
            self.command is None
            and tables.exists()
            and "filter" in tables.read_text().split()
        ):
            raise OSError("The active firewall has no iptables control utility")
        if self.command is not None and self.save is None:
            raise OSError("The firewall has no iptables-save utility")
        return self.command is not None

    @staticmethod
    def _rule(interface, host, port):
        rule = ["-i", interface, "-p", "tcp", "--dport", str(port)]
        if host != "0.0.0.0":
            rule += ["-d", host]
        return rule + ["-j", "ACCEPT"]

    def _command(self, action, chain, rule=()):
        result = subprocess.run(
            [self.command, action, chain, *rule],
            capture_output=True,
            text=True,
            timeout=8,
        )
        if result.returncode:
            raise OSError(
                "Could not update the push firewall: " + result.stderr.strip()[-512:]
            )

    def open(self, host, port):
        self.close()
        if ipaddress.ip_address(host).is_loopback or not self._available():
            return
        interface = self.interface()
        if not interface:
            raise OSError("The Wi-Fi interface is unavailable for LAN push")
        values = {"interface": interface, "host": host, "port": port}
        temporary = self.journal.with_suffix(".new")
        temporary.write_text(json.dumps(values))
        temporary.replace(self.journal)
        self.state = FirewallState.INSTALLING
        try:
            try:
                self._command("-N", self.CHAIN)
            except OSError:
                # A pre-existing chain was not created by this listener.
                self.journal.unlink()
                raise
            self._command("-A", self.CHAIN, self._rule(**values))
            self._command("-I", "INPUT", ["-j", self.CHAIN])
        except Exception:
            self.state = (
                FirewallState.DIRTY if self.journal.exists() else FirewallState.CLEAN
            )
            raise
        self.state = FirewallState.OPEN

    def close(self):
        if not self.journal.exists():
            self.state = FirewallState.CLEAN
            return
        self.state = FirewallState.REMOVING
        try:
            self._remove_rules()
            self.journal.unlink()
        except Exception:
            self.state = FirewallState.DIRTY
            raise
        self.state = FirewallState.CLEAN

    def _remove_rules(self):
        if self._available():
            result = subprocess.run(
                [self.save, "-t", "filter"],
                capture_output=True,
                text=True,
                timeout=8,
            )
            if result.returncode:
                raise OSError(
                    "Could not read the push firewall: " + result.stderr.strip()[-512:]
                )
            chain_exists = False
            for line in result.stdout.splitlines():
                rule = shlex.split(line)
                if rule == ["-A", "INPUT", "-j", self.CHAIN]:
                    self._command("-D", "INPUT", rule[2:])
                if rule and rule[0] == ":" + self.CHAIN:
                    chain_exists = True
            if chain_exists:
                self._command("-F", self.CHAIN)
                self._command("-X", self.CHAIN)
