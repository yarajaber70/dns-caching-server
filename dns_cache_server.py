#!/usr/bin/env python3
"""
DNS Caching Server - Full Implementation (LRU + TTL)
Cache File Format: hostname,record_type,ip_address,ttl,timestamp

Text protocol (UDP payloads are UTF-8 strings):
Client -> Server:
  RESOLVE|<hostname>|<record_type>
  SHOWCACHE
  CLEARCACHE
  EXIT

Server -> Client:
  OK|RESOLVE|<hostname>|<record_type>|<ip_list>|TTL_LEFT=<seconds>|SOURCE=<CACHE|UPSTREAM>|TS=<iso>
  OK|SHOWCACHE|<num_entries>|<entry1>;<entry2>;...|TS=<iso>
    where entry = domain,qtype,ip_list,ttl_left
  OK|CLEARCACHE|TS=<iso>
  OK|EXIT|TS=<iso>
  ERROR|<code>|<message>|TS=<iso>
"""

import socket
import sys
import time
import os
from datetime import datetime
from collections import OrderedDict

import dns.resolver
import dns.exception

BUFFER_SIZE = 1024
CACHE_FILE = "dns_cache.txt"
DEFAULT_TTL = 3600
UPSTREAM_DNS = ["8.8.8.8", "1.1.1.1"]
SERVER_PORT = 5300


def _iso_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


# ------------------ LRU Cache (with TTL) ------------------
# OrderedDict: key -> (answers_list, expiry_ts)
# key is (domain, qtype)
class DNSCache:
    def __init__(self, cache_file: str, max_entries: int = 10):
        self.cache_file = cache_file
        self.max_entries = max(1, int(max_entries))
        self.cache: "OrderedDict[tuple[str, str], tuple[list[str], float]]" = OrderedDict()
        self.load_cache()

    def _purge_expired(self):
        now = time.time()
        expired_keys = [k for k, (_, exp) in self.cache.items() if now >= exp]
        for k in expired_keys:
            self.cache.pop(k, None)
        if expired_keys:
            self.save_cache()

    def load_cache(self):
        """Load cache entries from file into OrderedDict (ignore expired/malformed)."""
        self.cache.clear()

        if not os.path.exists(self.cache_file):
            return

        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue

                    # hostname,record_type,ip_address,ttl,timestamp
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) != 5:
                        continue

                    hostname, record_type, ip_address, ttl_str, ts_str = parts
                    try:
                        ttl = int(float(ttl_str))
                        inserted_ts = float(ts_str)
                    except ValueError:
                        continue

                    if ttl <= 0:
                        continue

                    expiry_ts = inserted_ts + ttl
                    if time.time() >= expiry_ts:
                        continue

                    domain = hostname.lower()
                    qtype = record_type.upper()

                    answers_list = [ip.strip() for ip in ip_address.split(";") if ip.strip()]
                    if not answers_list:
                        continue

                    key = (domain, qtype)
                    self.cache[key] = (answers_list, expiry_ts)

                    # enforce max size while loading (evict oldest)
                    while len(self.cache) > self.max_entries:
                        self.cache.popitem(last=False)

        except OSError:
            self.cache.clear()

    def save_cache(self):

        try:
            now = time.time()
            with open(self.cache_file, "w", encoding="utf-8") as f:
                f.write("# hostname,record_type,ip_address,ttl,timestamp\n")
                for (domain, qtype), (answers_list, expiry_ts) in self.cache.items():
                    ttl_left = int(expiry_ts - now)
                    if ttl_left <= 0:
                        continue
                    ip_list_str = ";".join(answers_list)
                    f.write(f"{domain},{qtype},{ip_list_str},{ttl_left},{now}\n")
        except OSError:
            pass

    def lookup(self, hostname, record_type="A"):
        """
        Look up a record in cache.
        Return (answers_list, ttl_left) if valid, else (None, None).
        """
        self._purge_expired()

        key = (hostname.lower(), record_type.upper())
        if key not in self.cache:
            return None, None

        answers_list, expiry_ts = self.cache[key]
        ttl_left = int(expiry_ts - time.time())
        if ttl_left <= 0:
            self.cache.pop(key, None)
            self.save_cache()
            return None, None

        # LRU update
        self.cache.move_to_end(key, last=True)
        return list(answers_list), ttl_left

    def add(self, hostname, record_type, ip_address, ttl=DEFAULT_TTL):
        """Add or update cache entry."""
        domain = hostname.lower()
        qtype = record_type.upper()

        if isinstance(ip_address, str):
            answers_list = [ip.strip() for ip in ip_address.split(";") if ip.strip()]
        else:
            answers_list = [str(ip).strip() for ip in ip_address if str(ip).strip()]

        if not answers_list:
            return

        ttl = int(ttl) if ttl else DEFAULT_TTL
        ttl = max(1, ttl)
        expiry_ts = time.time() + ttl

        key = (domain, qtype)
        self.cache[key] = (answers_list, expiry_ts)
        self.cache.move_to_end(key, last=True)

        while len(self.cache) > self.max_entries:
            self.cache.popitem(last=False)

        self.save_cache()

    def clear(self):
        self.cache.clear()
        self.save_cache()

    def snapshot(self):
        """
        Return list for SHOWCACHE:
          domain,qtype,ip_list,ttl_left
        """
        self._purge_expired()
        now = time.time()
        out = []
        for (domain, qtype), (answers_list, expiry_ts) in self.cache.items():
            ttl_left = int(expiry_ts - now)
            if ttl_left <= 0:
                continue
            ip_list_str = ";".join(answers_list)
            out.append(f"{domain},{qtype},{ip_list_str},{ttl_left}")
        return out


def query_upstream_dns(hostname, record_type="A"):

    rtype = record_type.upper()

    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = list(UPSTREAM_DNS)
    resolver.lifetime = 2.0
    resolver.timeout = 1.0

    # REQUIRED call:
    answer = resolver.resolve(hostname, rtype)

    # TTL extraction
    ttl = DEFAULT_TTL
    try:
        if answer.rrset is not None and answer.rrset.ttl is not None:
            ttl = int(answer.rrset.ttl)
    except Exception:
        ttl = DEFAULT_TTL

    # IP extraction
    ip_list = []
    for rdata in answer:
        if rtype in ("A", "AAAA"):
            ip_list.append(getattr(rdata, "address", str(rdata)))
        else:
            ip_list.append(str(rdata))

    if not ip_list:
        raise dns.exception.DNSException("Empty answer")

    return ip_list, ttl


def parse_query(message):
    """Parse RESOLVE|hostname|record_type -> (hostname, record_type) else (None, None)."""
    try:
        text = message.decode("utf-8", errors="replace").strip()
    except Exception:
        return None, None

    parts = [p.strip() for p in text.split("|")]
    if len(parts) != 3:
        return None, None
    if parts[0].upper() != "RESOLVE":
        return None, None

    hostname = parts[1]
    rtype = parts[2].upper() if parts[2] else "A"
    if not hostname:
        return None, None
    return hostname, rtype


def format_response(hostname, record_type, ip_list, source="CACHE", ttl_left=None):
    ip_str = ";".join(str(x) for x in (ip_list if isinstance(ip_list, list) else [str(ip_list)]))
    ttl_left = int(ttl_left) if ttl_left is not None else -1
    return (
        f"OK|RESOLVE|{hostname}|{record_type}|{ip_str}"
        f"|TTL_LEFT={ttl_left}|SOURCE={source}|TS={_iso_now()}"
    )


def _format_error(code: str, msg: str) -> str:
    msg = str(msg).replace("|", "/")
    return f"ERROR|{code}|{msg}|TS={_iso_now()}"


def main():
    # cache size from CLI: python dns_cache_server.py 5
    max_entries = 20
    if len(sys.argv) >= 2:
        try:
            max_entries = int(sys.argv[1])
        except ValueError:
            max_entries = 10

    cache = DNSCache(CACHE_FILE, max_entries=max_entries)

    req_no = 0
    hits = 0
    misses = 0

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", SERVER_PORT))
    print(f"[{_iso_now()}] Server listening UDP {SERVER_PORT} (max_entries={max_entries})")

    while True:
        try:
            data, addr = sock.recvfrom(BUFFER_SIZE)
            req_no += 1
            start = time.perf_counter()

            text = data.decode("utf-8", errors="replace").strip()
            if not text:
                resp = _format_error("BAD_REQUEST", "Empty message")
                sock.sendto(resp.encode("utf-8"), addr)
                continue

            cmd = text.split("|", 1)[0].strip().upper()

            if cmd == "SHOWCACHE":
                entries = cache.snapshot()
                payload = ";".join(entries)
                resp = f"OK|SHOWCACHE|{len(entries)}|{payload}|TS={_iso_now()}"
                sock.sendto(resp.encode("utf-8"), addr)

                proc = time.perf_counter() - start
                print(f"[{_iso_now()}] #{req_no} {addr} CMD=SHOWCACHE entries={len(entries)} proc={proc:.6f}s")
                continue

            if cmd == "CLEARCACHE":
                cache.clear()
                resp = f"OK|CLEARCACHE|TS={_iso_now()}"
                sock.sendto(resp.encode("utf-8"), addr)

                proc = time.perf_counter() - start
                print(f"[{_iso_now()}] #{req_no} {addr} CMD=CLEARCACHE proc={proc:.6f}s")
                continue

            if cmd == "EXIT":
                resp = f"OK|EXIT|TS={_iso_now()}"
                sock.sendto(resp.encode("utf-8"), addr)

                proc = time.perf_counter() - start
                print(f"[{_iso_now()}] #{req_no} {addr} CMD=EXIT proc={proc:.6f}s")
                continue

            if cmd != "RESOLVE":
                resp = _format_error("UNSUPPORTED", "Service not supported")
                sock.sendto(resp.encode("utf-8"), addr)

                proc = time.perf_counter() - start
                print(f"[{_iso_now()}] #{req_no} {addr} CMD={cmd} UNSUPPORTED proc={proc:.6f}s")
                continue

            hostname, rtype = parse_query(data)
            if not hostname:
                resp = _format_error("BAD_REQUEST", "Use RESOLVE|hostname|record_type")
                sock.sendto(resp.encode("utf-8"), addr)

                proc = time.perf_counter() - start
                print(f"[{_iso_now()}] #{req_no} {addr} CMD=RESOLVE BAD_REQUEST proc={proc:.6f}s msg='{text}'")
                continue

            # Cache lookup
            ip_list, ttl_left = cache.lookup(hostname, rtype)
            if ip_list:
                hits += 1
                resp = format_response(hostname, rtype, ip_list, source="CACHE", ttl_left=ttl_left)
                sock.sendto(resp.encode("utf-8"), addr)

                proc = time.perf_counter() - start
                ratio = hits / max(1, (hits + misses))
                print(f"[{_iso_now()}] #{req_no} {addr} RESOLVE {hostname} {rtype} HIT ttl_left={ttl_left}s proc={proc:.6f}s hit_ratio={ratio:.2f}")
                continue

            # Miss -> Upstream
            misses += 1
            upstream_start = time.perf_counter()
            try:
                up_ips, up_ttl = query_upstream_dns(hostname, rtype)
                up_time = time.perf_counter() - upstream_start

                cache.add(hostname, rtype, up_ips, ttl=up_ttl)
                resp = format_response(hostname, rtype, up_ips, source="UPSTREAM", ttl_left=up_ttl)
                sock.sendto(resp.encode("utf-8"), addr)

                proc = time.perf_counter() - start
                ratio = hits / max(1, (hits + misses))
                print(f"[{_iso_now()}] #{req_no} {addr} RESOLVE {hostname} {rtype} MISS up_time={up_time:.6f}s ttl={up_ttl}s proc={proc:.6f}s hit_ratio={ratio:.2f}")

            except dns.exception.DNSException as e:
                up_time = time.perf_counter() - upstream_start
                resp = _format_error("DNS_FAIL", str(e))
                sock.sendto(resp.encode("utf-8"), addr)

                proc = time.perf_counter() - start
                ratio = hits / max(1, (hits + misses))
                print(f"[{_iso_now()}] #{req_no} {addr} RESOLVE {hostname} {rtype} MISS DNS_FAIL up_time={up_time:.6f}s proc={proc:.6f}s hit_ratio={ratio:.2f}")

        except KeyboardInterrupt:
            print("\nServer shutting down.")
            break
        except Exception as e:
            print(f"[{_iso_now()}] ERROR: {str(e)}")
            continue

    sock.close()


if __name__ == "__main__":
    main()
