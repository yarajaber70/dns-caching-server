#!/usr/bin/env python3
"""
DNS Client for the DNS Caching Server (UDP)
Menu:
  1) Resolve
  2) ShowCache
  3) ClearCache
  4) ShowRTT
  5) Exit

Protocol:
  Client -> Server:
    RESOLVE|<hostname>|<record_type>
    SHOWCACHE
    CLEARCACHE
    EXIT

  Server -> Client:
    OK|RESOLVE|hostname|type|ip1;ip2|TTL_LEFT=..|SOURCE=..|TS=..
    OK|SHOWCACHE|n|entry1;entry2;...|TS=..
    OK|CLEARCACHE|TS=..
    OK|EXIT|TS=..
    ERROR|CODE|message|TS=..
"""

import socket
import time

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 5300
BUFFER_SIZE = 4096
SOCKET_TIMEOUT = 2.0


def send_and_receive(sock: socket.socket, msg: str):
    """Send msg to server and return (response_text, rtt_seconds)."""
    data = msg.encode("utf-8")
    t0 = time.perf_counter()
    sock.sendto(data, (SERVER_HOST, SERVER_PORT))
    resp, _ = sock.recvfrom(BUFFER_SIZE)
    t1 = time.perf_counter()
    return resp.decode("utf-8", errors="replace").strip(), (t1 - t0)


def print_menu():
    print("\n==== DNS Client Menu ====")
    print("1) Resolve")
    print("2) ShowCache")
    print("3) ClearCache")
    print("4) ShowRTT")
    print("5) Exit")


def parse_keyvals(parts):

    d = {}
    for p in parts:
        if "=" in p:
            k, v = p.split("=", 1)
            d[k.strip()] = v.strip()
    return d


def handle_resolve(sock, rtt_log):
    hostname = input("Enter hostname (e.g., www.google.com): ").strip()
    if not hostname:
        print("Hostname cannot be empty.")
        return

    record_type = input("Enter record type [A/AAAA/CNAME...] (default A): ").strip().upper()
    if not record_type:
        record_type = "A"

    msg = f"RESOLVE|{hostname}|{record_type}"

    try:
        resp, rtt = send_and_receive(sock, msg)
        rtt_log.append(rtt)
        print(f"\nRTT: {rtt*1000:.3f} ms")
        print(f"Server response: {resp}")

        parts = resp.split("|")
        if parts and parts[0] == "OK" and len(parts) >= 6 and parts[1] == "RESOLVE":
            # OK|RESOLVE|hostname|type|ip_list|TTL_LEFT=..|SOURCE=..|TS=..
            ip_list = parts[4]
            kv = parse_keyvals(parts[5:])
            ttl_left = kv.get("TTL_LEFT", "?")
            source = kv.get("SOURCE", "?")
            print("\n--- Parsed ---")
            print(f"Hostname: {parts[2]}")
            print(f"Type:     {parts[3]}")
            print(f"IP(s):    {ip_list}")
            print(f"TTL left: {ttl_left} seconds")
            print(f"Source:   {source}")
        elif parts and parts[0] == "ERROR":
            # ERROR|CODE|message|TS=..
            code = parts[1] if len(parts) > 1 else "UNKNOWN"
            msg = parts[2] if len(parts) > 2 else ""
            print(f"Error [{code}]: {msg}")

    except socket.timeout:
        print("Timeout: No response from server.")
    except Exception as e:
        print(f"Client error: {e}")


def handle_showcache(sock, rtt_log):
    try:
        resp, rtt = send_and_receive(sock, "SHOWCACHE")
        rtt_log.append(rtt)
        print(f"\nRTT: {rtt*1000:.3f} ms")
        print(f"Server response: {resp}")

        parts = resp.split("|")
        if parts and parts[0] == "OK" and len(parts) >= 3 and parts[1] == "SHOWCACHE":
            n = int(parts[2]) if parts[2].isdigit() else 0
            payload = parts[3] if len(parts) >= 4 else ""
            print(f"\n--- Cache Entries ({n}) ---")
            if not payload:
                print("(empty)")
                return
            entries = payload.split(";")
            for i, entry in enumerate(entries, start=1):
                print(f"{i}. {entry}")

        elif parts and parts[0] == "ERROR":
            code = parts[1] if len(parts) > 1 else "UNKNOWN"
            msg = parts[2] if len(parts) > 2 else ""
            print(f"Error [{code}]: {msg}")

    except socket.timeout:
        print("Timeout: No response from server.")
    except Exception as e:
        print(f"Client error: {e}")


def handle_clearcache(sock, rtt_log):
    try:
        resp, rtt = send_and_receive(sock, "CLEARCACHE")
        rtt_log.append(rtt)
        print(f"\nRTT: {rtt*1000:.3f} ms")
        print(f"Server response: {resp}")

        parts = resp.split("|")
        if parts and parts[0] == "OK" and parts[1] == "CLEARCACHE":
            print("Cache cleared successfully.")
        elif parts and parts[0] == "ERROR":
            code = parts[1] if len(parts) > 1 else "UNKNOWN"
            msg = parts[2] if len(parts) > 2 else ""
            print(f"Error [{code}]: {msg}")

    except socket.timeout:
        print("Timeout: No response from server.")
    except Exception as e:
        print(f"Client error: {e}")


def handle_showrtt(rtt_log):
    print("\n--- RTT Log ---")
    if not rtt_log:
        print("No RTT samples yet.")
        return
    total = 0.0
    for i, rtt in enumerate(rtt_log, start=1):
        ms = rtt * 1000.0
        total += rtt
        print(f"{i}. {ms:.3f} ms")
    avg = (total / len(rtt_log)) * 1000.0
    print(f"Average RTT: {avg:.3f} ms")


def main():
    rtt_log = []

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(SOCKET_TIMEOUT)

    print(f"DNS Client started. Server = {SERVER_HOST}:{SERVER_PORT}")

    while True:
        print_menu()
        choice = input("Choose (1-5): ").strip()

        if choice == "1":
            handle_resolve(sock, rtt_log)
        elif choice == "2":
            handle_showcache(sock, rtt_log)
        elif choice == "3":
            handle_clearcache(sock, rtt_log)
        elif choice == "4":
            handle_showrtt(rtt_log)
        elif choice == "5":
            # Graceful exit: notify server (server keeps running)
            try:
                resp, rtt = send_and_receive(sock, "EXIT")
                rtt_log.append(rtt)
                print(f"Server response: {resp}")
            except Exception:
                pass
            print("Bye!")
            break
        else:
            print("Invalid choice. Please enter 1-5.")

    sock.close()


if __name__ == "__main__":
    main()
