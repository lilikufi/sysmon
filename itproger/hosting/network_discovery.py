import concurrent.futures
import ipaddress
import logging
import re
import subprocess
import threading

from django.db import transaction

from hosting.models import Host, Route


logger = logging.getLogger(__name__)

IP_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
OID_PATTERN = re.compile(r"^\.?\d+(?:\.\d+)+$")
COMMUNITY_PATTERN = re.compile(r"^[A-Za-z0-9_.:@-]{1,64}$")


class NetworkDiscovery:
    """Discover SNMP devices and persist their topology."""

    def __init__(self, community="public", timeout=2, retries=1):
        if not COMMUNITY_PATTERN.fullmatch(community):
            raise ValueError("SNMP community contains unsupported characters")
        if not 1 <= timeout <= 30:
            raise ValueError("timeout must be between 1 and 30 seconds")
        if not 0 <= retries <= 5:
            raise ValueError("retries must be between 0 and 5")

        self.community = community
        self.timeout = timeout
        self.retries = retries
        self.discovered_hosts = {}
        self.connections = []
        self.lock = threading.Lock()

    @staticmethod
    def normalize_ip(value):
        """Return a canonical IP string or raise ValueError."""
        return str(ipaddress.ip_address(value))

    @staticmethod
    def validate_oid(oid):
        if not OID_PATTERN.fullmatch(oid):
            raise ValueError("OID must contain only numeric components")
        return oid.lstrip(".")

    def _run(self, command, timeout):
        try:
            return subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
            logger.warning("Network command failed: %s", exc)
            return None

    def _snmp_command(self, executable, ip, oid):
        return [
            executable,
            "-v",
            "2c",
            "-c",
            self.community,
            "-t",
            str(self.timeout),
            "-r",
            str(self.retries),
            self.normalize_ip(ip),
            self.validate_oid(oid),
        ]

    def snmp_get(self, ip, oid):
        """Execute an SNMP GET without invoking a shell."""
        result = self._run(self._snmp_command("snmpget", ip, oid), timeout=5)
        if result is not None and result.returncode == 0:
            return result.stdout.strip()
        return None

    def snmp_walk(self, ip, oid):
        """Execute an SNMP WALK without invoking a shell."""
        result = self._run(self._snmp_command("snmpwalk", ip, oid), timeout=10)
        if result is not None and result.returncode == 0:
            return result.stdout.strip().splitlines()
        return []

    def get_device_info(self, ip):
        """Get basic availability and SNMP information for a device."""
        ip = self.normalize_ip(ip)
        info = {
            "ipaddr": ip,
            "hostname": None,
            "device_type": "servers",
            "vendor": None,
            "product": None,
            "online": False,
            "SNMP": False,
        }

        ping_result = self._run(["ping", "-c", "1", "-W", "1", ip], timeout=3)
        info["online"] = ping_result is not None and ping_result.returncode == 0

        sysname = self.snmp_get(ip, "1.3.6.1.2.1.1.5.0")
        if sysname:
            info["SNMP"] = True
            match = re.search(r'STRING:\s*"?([^"\n]+)"?', sysname)
            if match:
                info["hostname"] = match.group(1).strip()

        sysdescr = self.snmp_get(ip, "1.3.6.1.2.1.1.1.0")
        if sysdescr:
            description = sysdescr.lower()
            if "cisco" in description or "ios" in description:
                info.update(device_type="switches", vendor="Cisco")
            elif "hp" in description or "procurve" in description:
                info.update(device_type="switches", vendor="HP")
            elif "mikrotik" in description:
                info.update(device_type="switches", vendor="MikroTik")
            elif "linux" in description:
                info.update(device_type="servers", vendor="Linux")
            elif "windows" in description:
                info.update(device_type="servers", vendor="Microsoft")
            elif "ups" in description or "apc" in description:
                info.update(device_type="UPS", vendor="APC" if "apc" in description else "UPS")
            elif "printer" in description:
                info["device_type"] = "network-printers"

            match = re.search(r"(IOS|Software|Version)[^,]*,\s*([^,]+)", sysdescr)
            if match:
                info["product"] = match.group(2).strip()

        return info

    @staticmethod
    def _extract_ips(lines):
        addresses = []
        for line in lines:
            for match in IP_PATTERN.findall(line):
                try:
                    addresses.append(str(ipaddress.ip_address(match)))
                except ValueError:
                    continue
        return addresses

    def get_neighbors_lldp(self, ip):
        return self._extract_ips(self.snmp_walk(ip, "1.0.8802.1.1.2.1.4.1.1"))

    def get_neighbors_cdp(self, ip):
        neighbors = []
        for line in self.snmp_walk(ip, "1.3.6.1.4.1.9.9.23.1.2.1.1.4"):
            if "Hex-STRING:" not in line:
                continue
            hex_data = line.split("Hex-STRING:", 1)[1].replace(" ", "").replace(":", "")
            if len(hex_data) < 8:
                continue
            try:
                neighbors.append(str(ipaddress.ip_address(bytes.fromhex(hex_data[-8:]))))
            except ValueError:
                continue
        return neighbors

    def get_arp_table(self, ip):
        return [
            address
            for address in self._extract_ips(
                self.snmp_walk(ip, "1.3.6.1.2.1.4.22.1.3")
            )
            if not address.startswith("127.")
        ]

    def get_routing_table(self, ip):
        return [
            address
            for address in self._extract_ips(
                self.snmp_walk(ip, "1.3.6.1.2.1.4.21.1.7")
            )
            if address != "0.0.0.0"
        ]

    @staticmethod
    def is_valid_ip(ip):
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            return False
        return True

    def discover_device(self, ip):
        ip = self.normalize_ip(ip)
        logger.info("Discovering device %s", ip)
        device_info = self.get_device_info(ip)
        if not device_info["SNMP"]:
            logger.info("Device %s does not expose SNMP", ip)
            return set()

        with self.lock:
            self.discovered_hosts[ip] = device_info

        neighbors = set(self.get_neighbors_lldp(ip))
        if device_info.get("vendor") == "Cisco":
            neighbors.update(self.get_neighbors_cdp(ip))
        neighbors.update(self.get_arp_table(ip)[:10])
        neighbors.update(self.get_routing_table(ip)[:5])
        neighbors.discard(ip)

        with self.lock:
            self.connections.extend((ip, neighbor) for neighbor in sorted(neighbors))

        logger.info("Found %d neighbors for %s", len(neighbors), ip)
        return neighbors

    def discover_network(self, start_ip, max_hops=3, max_devices=50):
        start_ip = self.normalize_ip(start_ip)
        if not 1 <= max_hops <= 20:
            raise ValueError("max_hops must be between 1 and 20")
        if not 1 <= max_devices <= 1000:
            raise ValueError("max_devices must be between 1 and 1000")

        to_discover = {start_ip}
        discovered = set()

        for hop in range(max_hops):
            if not to_discover or len(discovered) >= max_devices:
                break
            current_batch = sorted(to_discover)[: max_devices - len(discovered)]
            to_discover = set()
            logger.info("Discovery hop %d: %d devices", hop + 1, len(current_batch))

            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = {
                    executor.submit(self.discover_device, ip): ip
                    for ip in current_batch
                    if ip not in discovered
                }
                for future in concurrent.futures.as_completed(futures):
                    ip = futures[future]
                    discovered.add(ip)
                    try:
                        neighbors = future.result()
                    except Exception:
                        logger.exception("Discovery failed for %s", ip)
                        continue
                    to_discover.update(neighbors - discovered)

        logger.info("Discovery complete: %d devices", len(self.discovered_hosts))
        return self.discovered_hosts, self.connections

    def save_to_database(self):
        with transaction.atomic():
            hosts_by_ip = {}
            for ip, info in self.discovered_hosts.items():
                host, _created = Host.objects.update_or_create(
                    ipaddr=ip,
                    defaults={
                        "hostname": info.get("hostname") or "",
                        "vendor": info.get("vendor") or "",
                        "product": info.get("product") or "",
                        "device_type": info.get("device_type", "servers"),
                        "online": info.get("online", False),
                        "SNMP": info.get("SNMP", False),
                        "com_str": self.community,
                        "nagios_flag": True,
                    },
                )
                hosts_by_ip[ip] = host

            for parent_ip, child_ip in self.connections:
                parent = hosts_by_ip.get(parent_ip)
                child = hosts_by_ip.get(child_ip)
                if parent is None or child is None:
                    continue
                Route.objects.get_or_create(parent=parent, child=child)
                if child.parents_id is None:
                    child.parents = parent
                    child.save(update_fields=["parents"])

        return len(self.discovered_hosts)
