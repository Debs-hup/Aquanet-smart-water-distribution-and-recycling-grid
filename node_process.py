import socket
import threading
import argparse
import struct
import json
import time
from storage_virtual_node import StorageVirtualNode

HOST = "127.0.0.1"
PORT = 5000


def send_json(conn, obj):
    data = json.dumps(obj).encode()
    conn.sendall(struct.pack("!I", len(data)) + data)


def recv_json(conn):
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


class NodeProcess:
    def __init__(self, node_id, cpu, mem, storage_gb, bandwidth_mbps, net_host, net_port):
        self.node_id = node_id
        self.node = StorageVirtualNode(node_id, cpu, mem, storage_gb, bandwidth_mbps)
        self.net_host = net_host
        self.net_port = net_port
        self.conn = None
        self.listener_thread = None
        self.lock = threading.Lock()
        self._last_accept = None  # Fix silent crash

    def connect_to_network(self):
        try:
            self.conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.conn.connect((self.net_host, self.net_port))
            send_json(self.conn, {"type": "register", "node_id": self.node_id})

            self.listener_thread = threading.Thread(target=self._listen_from_network, daemon=True)
            self.listener_thread.start()

            print(f"[{self.node_id}] Connected to network {self.net_host}:{self.net_port}")
        except Exception as e:
            print(f"[{self.node_id}] ERROR: Cannot connect to network → {e}")

    def _listen_from_network(self):
        try:
            while True:
                msg = recv_json(self.conn)
                if msg is None:
                    print(f"[{self.node_id}] Lost connection to network")
                    break
                self._handle_message(msg)
        except Exception as e:
            print(f"[{self.node_id}] Listener crashed → {e}")

    def _handle_message(self, msg):
        mtype = msg.get("type")
        origin = msg.get("from")

        # ---------------------- STORE REQUEST RECEIVED ----------------------
        if mtype == "request_store":
            file_name = msg["file_name"]
            file_size = msg["file_size"]
            file_id = msg.get("file_id") or f"{file_name}-{time.time()}"

            with self.lock:
                transfer = self.node.initiate_file_transfer(file_id, file_name, file_size)

            if not transfer:
                send_json(self.conn, {"type": "reject", "target": origin, "reason": "insufficient_space"})
                print(f"[{self.node_id}] REJECTED store request from {origin}")
                return

            send_json(self.conn, {
                "type": "accept",
                "target": origin,
                "file_id": transfer.file_id,
                "chunk_count": len(transfer.chunks)
            })
            print(f"[{self.node_id}] ACCEPTED store request from {origin} → {file_name}")

        # ---------------------- CHUNK RECEIVED ----------------------
        elif mtype == "chunk":
            file_id = msg["file_id"]
            chunk_id = msg["chunk_id"]

            with self.lock:
                ok = self.node.process_chunk_transfer(file_id, chunk_id, origin)

            send_json(self.conn, {"type": "chunk_ack", "target": origin, "file_id": file_id, "chunk_id": chunk_id, "ok": ok})

            if ok:
                print(f"[{self.node_id}] Stored chunk {chunk_id} of file {file_id}")
            else:
                print(f"[{self.node_id}] FAILED chunk {chunk_id} of file {file_id}")

        # ---------------------- ACCEPT RECEIVED ----------------------
        elif mtype == "accept":
            print(f"[{self.node_id}] ACCEPT received from {origin}")
            with self.lock:
                self._last_accept = {
                    "file_id": msg["file_id"],
                    "chunk_count": msg["chunk_count"],
                    "target": origin
                }

        # ---------------------- ACK RECEIVED ----------------------
        elif mtype == "chunk_ack":
            print(f"[{self.node_id}] ACK from {origin}: file {msg['file_id']} chunk {msg['chunk_id']}")

        elif mtype == "reject":
            print(f"[{self.node_id}] REQUEST REJECTED → {msg.get('reason')}")

        else:
            print(f"[{self.node_id}] Unknown message: {msg}")

    # ---------------------- SEND STORE REQUEST ----------------------
    def request_store_on_target(self, target_node_id, file_name, file_size):
        if file_size <= 0:
            print("[ERROR] File size must be > 0")
            return

        send_json(self.conn, {
            "type": "request_store",
            "target": target_node_id,
            "file_name": file_name,
            "file_size": file_size
        })
        print(f"[{self.node_id}] Sent store request to {target_node_id}")

    # ---------------------- SEND CHUNKS ----------------------
    def send_chunks_to_target(self, target_node_id, file_id, file_size):
        chunk_size = (
            512 * 1024 if file_size < 10 * 1024 * 1024 else
            2 * 1024 * 1024 if file_size < 100 * 1024 * 1024 else
            10 * 1024 * 1024
        )

        num_chunks = (file_size + chunk_size - 1) // chunk_size
        print(f"[{self.node_id}] Sending {num_chunks} chunks...")

        for chunk_id in range(num_chunks):
            send_json(self.conn, {
                "type": "chunk",
                "target": target_node_id,
                "file_id": file_id,
                "chunk_id": chunk_id
            })
            time.sleep(0.01)

    # ---------------------- MAIN LOOP ----------------------
    def run(self):
        try:
            while True:
                cmd = input(f"[{self.node_id}] > ").strip()

                if cmd == "help":
                    print("Commands:\n request TARGET FNAME FSIZE\n status\n quit")

                elif cmd.startswith("request"):
                    parts = cmd.split()
                    if len(parts) != 4:
                        print("Usage: request TARGET FILENAME SIZE")
                    else:
                        _, tgt, fname, size = parts
                        self.request_store_on_target(tgt, fname, int(size))

                elif cmd == "status":
                    print("Storage:", self.node.get_storage_utilization())
                    print("Performance:", self.node.get_performance_metrics())

                elif cmd == "quit":
                    break

                else:
                    print("Unknown command")

        except KeyboardInterrupt:
            pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True)
    parser.add_argument("--cpu", type=int, default=2)
    parser.add_argument("--mem", type=int, default=4)
    parser.add_argument("--storage", type=int, default=50)
    parser.add_argument("--bw", type=int, default=100)
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)

    parser.add_argument("--auto-request", nargs=3, metavar=("TARGET", "FNAME", "FSIZE"))

    args = parser.parse_args()

    nodeproc = NodeProcess(args.id, args.cpu, args.mem, args.storage, args.bw, args.host, args.port)
    nodeproc.connect_to_network()

    # ---------------------- AUTO REQUEST MODE ----------------------
    if args.auto_request:
        target, fname, fsize_s = args.auto_request
        fsize = int(fsize_s)

        print(f"[{args.id}] AUTO REQUEST → {target}, file={fname}, size={fsize}")
        nodeproc.request_store_on_target(target, fname, fsize)

        # wait for accept
        for _ in range(50):
            time.sleep(0.2)
            if nodeproc._last_accept:
                nodeproc.send_chunks_to_target(target, nodeproc._last_accept["file_id"], fsize)
                break
        else:
            print(f"[{args.id}] TIMEOUT: no accept received")

    nodeproc.run()


if __name__ == "__main__":
    main()
