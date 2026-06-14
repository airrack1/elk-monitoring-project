"""Scope enforcement.

The whole point of Phase 0 is that nothing gets touched outside written,
authorized scope. This module is the single source of truth for "is this target
allowed?" and is used to gate every active tool invocation.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from typing import List, Optional


def _parse_networks(entries: List[str]):
    """Parse a list of IPs/CIDRs/ranges into ip_network objects.

    Accepts single IPs, CIDR notation, and 'a.b.c.d-e' short ranges. Hostnames
    (non-numeric) are returned separately as literal strings to match exactly.
    """
    nets = []
    hostnames = []
    for raw in entries:
        entry = raw.strip()
        if not entry:
            continue
        try:
            if "-" in entry and "/" not in entry:
                start_s, end_s = entry.split("-", 1)
                start = ipaddress.ip_address(start_s.strip())
                # allow 'a.b.c.d-e' shorthand for the last octet
                if "." not in end_s and ":" not in end_s:
                    end_s = ".".join(start_s.strip().split(".")[:-1] + [end_s.strip()])
                end = ipaddress.ip_address(end_s.strip())
                nets.extend(ipaddress.summarize_address_range(start, end))
            else:
                nets.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            hostnames.append(entry.lower())
    return nets, hostnames


@dataclass
class Scope:
    """In-scope and excluded assets for an engagement."""

    in_scope: List[str] = field(default_factory=list)
    exclusions: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"in_scope": self.in_scope, "exclusions": self.exclusions}

    @classmethod
    def from_dict(cls, d: dict) -> "Scope":
        d = d or {}
        return cls(in_scope=list(d.get("in_scope", [])), exclusions=list(d.get("exclusions", [])))

    def check(self, target: str) -> "ScopeResult":
        """Decide whether `target` (IP or hostname) is permitted."""
        target = target.strip()
        in_nets, in_hosts = _parse_networks(self.in_scope)
        ex_nets, ex_hosts = _parse_networks(self.exclusions)

        as_ip: Optional[ipaddress._BaseAddress] = None
        try:
            as_ip = ipaddress.ip_address(target)
        except ValueError:
            as_ip = None

        # Exclusions always win.
        if as_ip is not None:
            for net in ex_nets:
                if as_ip in net:
                    return ScopeResult(False, f"{target} is explicitly EXCLUDED ({net})")
        if target.lower() in ex_hosts:
            return ScopeResult(False, f"{target} is explicitly EXCLUDED")

        if as_ip is not None:
            for net in in_nets:
                if as_ip in net:
                    return ScopeResult(True, f"{target} in-scope ({net})")
            return ScopeResult(False, f"{target} is NOT within any in-scope range")

        # hostname
        if target.lower() in in_hosts:
            return ScopeResult(True, f"{target} in-scope (host)")
        return ScopeResult(False, f"{target} not listed as an in-scope host")

    def all_targets(self) -> List[str]:
        """Expanded list of individual in-scope IPs (for small ranges) + hosts."""
        nets, hosts = _parse_networks(self.in_scope)
        targets: List[str] = []
        for net in nets:
            if net.num_addresses <= 1024:
                targets.extend(str(h) for h in net.hosts()) if net.prefixlen < 32 else targets.append(str(net.network_address))
            else:
                targets.append(str(net))  # too big to expand; keep as CIDR
        targets.extend(hosts)
        return targets


@dataclass
class ScopeResult:
    allowed: bool
    reason: str

    def __bool__(self) -> bool:
        return self.allowed
