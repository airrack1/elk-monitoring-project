"""Canonical NetSec Assessments audit checklist, as structured data.

This is a faithful, machine-readable encoding of the engagement checklist so the
rest of the program can track progress, gate phases, attach evidence/findings to
specific items, and render reports. Edit here to evolve the master checklist.

Each item id is stable (`p{phase}.{n}`) so engagement records keep referencing
the same item even if wording changes.
"""

TEMPLATE_VERSION = "1.0.0"

# A phase is gated when every item it depends on (by phase number) must be
# complete before the runner will execute any active tooling for it. Phase 0
# (authorization) gates everything that touches the network.
PHASES = [
    {
        "number": 0,
        "name": "Pre-Engagement & Authorization",
        "intent": "Do not touch a single packet until this phase is 100% complete.",
        "gating": True,  # blocks all active tooling until complete
        "items": [
            "Signed SOW / engagement letter on file",
            "Signed written authorization with CFAA language, signed by an authorized officer/owner",
            "Rules of Engagement documented: in-scope IPs/subnets/hosts, exclusions, windows, intensity",
            "Scope boundaries re-confirmed in writing (in-scope vs out-of-scope)",
            "Emergency contacts + escalation path documented",
            "Client confirmed backups exist and accepts risk of active testing",
            "Get-out-of-jail authorization letter saved offline + accessible on-site",
            "Testing source IP(s) documented and (if needed) whitelisted",
            "Evidence handling + data retention/destruction policy agreed",
        ],
        "tools": ["SOW template", "Authorization agreement template", "Rules of Engagement doc"],
    },
    {
        "number": 1,
        "name": "Reconnaissance & Asset Discovery",
        "intent": "Build a complete, accurate inventory of what's on the in-scope network.",
        "items": [
            "Passive recon completed (external footprint, if external scope)",
            "Live host discovery across all in-scope subnets",
            "Asset inventory built: IP, hostname, MAC, OS guess, role",
            "Cross-checked discovered assets vs client-provided inventory; flag rogue devices",
            "Network topology / segmentation mapped (VLANs, subnets, trust boundaries)",
        ],
        "tools": ["Nmap", "netdiscover", "arp-scan", "masscan", "theHarvester", "Shodan", "dnsenum/fierce"],
    },
    {
        "number": 2,
        "name": "Port Scanning & Service Enumeration",
        "intent": "Know every open port and what's really listening.",
        "items": [
            "Full TCP port scan on in-scope hosts",
            "UDP scan on key hosts (SNMP/161, DNS/53, etc.)",
            "Service + version detection (-sV) and OS detection (-O) recorded",
            "Nmap NSE default + safe scripts run; output saved",
            "SMB/NetBIOS enumerated (shares, users, sessions)",
            "SNMP enumerated (default/weak community strings)",
            "LDAP / directory services enumerated (if present)",
            "All raw scan output saved as evidence (XML/greppable + screenshots)",
        ],
        "tools": ["Nmap (+NSE)", "enum4linux-ng", "smbclient", "nbtscan", "snmp-check", "onesixtyone", "ldapsearch"],
    },
    {
        "number": 3,
        "name": "Vulnerability Assessment",
        "intent": "Find known-vulnerable surfaces; validate, don't just dump a scanner PDF.",
        "items": [
            "Authenticated and/or unauthenticated vuln scan run across in-scope hosts",
            "Web/admin interfaces scanned for known issues",
            "Template-based checks run (fast, current CVEs)",
            "Each high/critical finding cross-referenced to a known exploit/CVE",
            "Obvious false positives flagged for manual validation in Phase 7",
            "Scanner output exported and archived as evidence",
        ],
        "tools": ["Nessus", "OpenVAS/Greenbone", "nuclei", "Nikto", "searchsploit"],
    },
    {
        "number": 4,
        "name": "Configuration & Hardening Review",
        "intent": "Where most real SMB findings live. Your differentiator vs an automated scan.",
        "items": [
            "Firewall ruleset reviewed (any-any, unnecessary inbound, egress filtering)",
            "Management plane exposure checked (admin UIs, SSH, RDP from user VLAN/WAN)",
            "Default / weak credentials tested on devices and services",
            "TLS/SSL configuration tested (weak ciphers, SWEET32, deprecated TLS, expired certs)",
            "SSH configuration reviewed (weak algorithms, password auth, root login)",
            "Network segmentation validated (can user VLAN reach mgmt/server VLAN?)",
            "SNMP community strings + write access reviewed",
            "Wireless/router/AP config reviewed (firmware, guest isolation)",
            "NAS / storage config reviewed (exposed shares, services, patch level)",
            "Patch / firmware levels recorded vs latest available",
        ],
        "tools": ["testssl.sh", "sslscan", "Nipper", "CIS-CAT", "manual device consoles"],
    },
    {
        "number": 5,
        "name": "Wireless Assessment",
        "intent": "If in scope.",
        "optional": True,
        "items": [
            "All SSIDs enumerated (incl. hidden); encryption type recorded",
            "Guest network isolation verified",
            "WPS enabled/vulnerable check",
            "Rogue / unauthorized AP check",
            "Handshake capture + offline crack (validate weak PSK only; document, don't exfiltrate)",
            "Signal bleed / coverage beyond premises noted",
        ],
        "tools": ["aircrack-ng suite", "Kismet", "wifite", "wash", "hcxdumptool/hcxtools", "hashcat"],
    },
    {
        "number": 6,
        "name": "Traffic & Protocol Analysis",
        "intent": "Scope-permitting.",
        "optional": True,
        "items": [
            "Cleartext protocols in use identified (HTTP, FTP, Telnet, SNMPv1/2, LLMNR/NBT-NS)",
            "Sensitive data observed in transit documented (credentials, PII)",
            "Broadcast/multicast poisoning exposure noted (LLMNR/NBT-NS/mDNS)",
        ],
        "tools": ["Wireshark", "tcpdump", "Zeek"],
    },
    {
        "number": 7,
        "name": "Exploitation / Validation",
        "intent": "Prove risk is real. Safe, controlled, documented. No destructive actions.",
        "items": [
            "Selected high-impact findings safely validated (not just scanner-reported)",
            "Weak/default credential findings confirmed via controlled login test",
            "Successful access fully documented (screenshot, timestamp, host) and access dropped immediately",
            "No data exfiltrated; no persistence left behind",
            "Every action logged for the report's reproduction steps",
        ],
        "tools": ["Metasploit", "NetExec", "Hydra", "Impacket", "Responder", "John the Ripper / hashcat"],
    },
    {
        "number": 8,
        "name": "Web / Admin Portal Testing",
        "intent": "If web apps in scope.",
        "optional": True,
        "items": [
            "Admin/login portals tested (auth, lockout, default creds)",
            "Directory/content discovery run",
            "Common web issues checked (injection, auth bypass, exposed panels) per scope",
            "TLS on web services validated (ties back to Phase 4)",
        ],
        "tools": ["Burp Suite", "OWASP ZAP", "gobuster / ffuf", "Nikto"],
    },
    {
        "number": 9,
        "name": "Analysis & Risk Rating",
        "intent": "Consolidate, validate, score.",
        "items": [
            "All findings consolidated and de-duplicated",
            "False positives removed/validated",
            "Each finding scored (CVSS) and prioritized (Critical -> Low)",
            "Business impact written in plain language for each finding",
            "Evidence/screenshot attached to every finding",
            "Remediation recommendation drafted per finding",
        ],
        "tools": ["CVSS v3.1/v4.0 calculator", "Dradis / Faraday / ClientOps"],
    },
    {
        "number": 10,
        "name": "Reporting & Deliverables",
        "intent": "Deliver the work product.",
        "items": [
            "Executive summary written (non-technical, risk-focused)",
            "Technical findings section complete with evidence + reproduction steps",
            "Remediation roadmap prioritized",
            "Report mapped against SOW scope (every promised item addressed)",
            "Retest offer / retainer upsell included",
            "Report proofread; client name/dates correct; no leftover placeholders",
            "Report delivered securely (encrypted/agreed channel)",
        ],
        "tools": ["Word audit report template", "CVSS calculator", "secure delivery method"],
    },
    {
        "number": 11,
        "name": "Post-Engagement & Cleanup",
        "intent": "Leave the environment clean.",
        "items": [
            "All testing artifacts removed from client environment (tools, accounts, files, shells)",
            "Temporary firewall/whitelist entries reverted",
            "Captured credentials/handshakes/evidence handled per retention policy",
            "Client debrief / walkthrough scheduled or completed",
            "Retest date discussed; retainer offered",
            "Engagement notes archived; client folder closed out",
        ],
        "tools": ["ClientOps", "evidence retention/destruction log"],
    },
]

# Final QA recheck — verification gate before declaring the job done.
FINAL_QA = [
    "Every in-scope asset from Phase 1 appears somewhere in findings/coverage",
    "Nothing out-of-scope was touched",
    "Each finding has: evidence, CVSS score, business impact, remediation",
    "No scanner false positives left in the report",
    "Report scope == SOW scope (one-to-one)",
    "All raw evidence archived and backed up",
    "Client environment left clean (Phase 11 verified)",
    "Authorization letter + RoE retained with the engagement file",
]

# Master tool inventory, grouped — used by the `tools` command to check install.
TOOL_INVENTORY = {
    "Discovery & Scanning": ["nmap", "netdiscover", "arp-scan", "masscan", "nbtscan"],
    "Enumeration": ["enum4linux-ng", "smbclient", "snmp-check", "onesixtyone", "ldapsearch"],
    "Vulnerability": ["nuclei", "nikto", "searchsploit"],
    "Config / Hardening": ["testssl.sh", "sslscan"],
    "Wireless": ["aircrack-ng", "airodump-ng", "kismet", "wifite", "wash", "hashcat"],
    "Traffic": ["tshark", "tcpdump", "zeek"],
    "Validation / Exploitation": ["msfconsole", "netexec", "hydra", "responder", "john"],
    "Web": ["gobuster", "ffuf"],
    "External recon": ["theHarvester", "dnsenum", "fierce"],
}


def build_phase_items():
    """Return {phase_number: [(item_id, text), ...]} with stable ids."""
    out = {}
    for phase in PHASES:
        out[phase["number"]] = [
            (f"p{phase['number']}.{i}", text) for i, text in enumerate(phase["items"], start=1)
        ]
    return out
