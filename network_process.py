#!/usr/bin/env python3
# network_process.py
import socket
import threading
import json
import struct

HOST = "127.0.0.1"
PORT = 5000

# Map node_id -> (conn, addr)
nodes = {}
nodes_lock = threading.Lock()

def recv_json(conn):
    # read 4-byte length prefix
    raw = conn.recv(4)
    if not raw:
        return None
    (length,) = struct.unpack("!I", raw)
    data = b""
    while len(data) < length:
        packet = conn.recv(length - len(data))
        if not packet:
            return None
        data += packet
    return json.loads(data.decode())

def send_json(conn, obj):
    data = json.dumps(obj).encode()
    conn.sendall(struct.pack("!I", len(data)) + data)

def handle_client(conn, addr):
    try:
        # First message must be a register message
        msg = recv_json(conn)
        if msg is None or msg.get("type") != "register":
            conn.close()
            return
        node_id = msg.get("node_id")
        print(f"[network] Node registered: {node_id} from {addr}")
        with nodes_lock:
            nodes[node_id] = (conn, addr)

        # Main loop: receive messages and forward as appropriate
        while True:
            msg = recv_json(conn)
            if msg is None:
                print(f"[network] Connection closed by {node_id}")
                break

            mtype = msg.get("type")
            # If message has 'target', forward to that node
            target = msg.get("target")
            if target:
                with nodes_lock:
                    entry = nodes.get(target)
                if not entry:
                    # send error back to sender
                    send_json(conn, {"type":"error", "error":"target_unreachable", "target": target})
                else:
                    target_conn, _ = entry
                    # attach origin
                    msg["from"] = node_id
                    try:
                        send_json(target_conn, msg)
                    except Exception as e:
                        print(f"[network] Failed to forward to {target}: {e}")
                        send_json(conn, {"type":"error", "error":"forward_failed", "target": target})
            else:
                # messages with no target can be broadcast or handled locally (not used here)
                print(f"[network] Received message with no target from {node_id}: {mtype}")
    except Exception as e:
        print(f"[network] Exception: {e}")
    finally:
        # cleanup
        with nodes_lock:
            for nid, (c, _) in list(nodes.items()):
                if c is conn:
                    print(f"[network] Removing node {nid}")
                    del nodes[nid]
                    break
        conn.close()

def main():
    print(f"[network] Starting network relay on {HOST}:{PORT}")
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen()
    try:
        while True:
            conn, addr = srv.accept()
            t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            t.start()
    except KeyboardInterrupt:
        print("[network] Shutting down")
    finally:
        srv.close()

if __name__ == "__main__":
    main()
