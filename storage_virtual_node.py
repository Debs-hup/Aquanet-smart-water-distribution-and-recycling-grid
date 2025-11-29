import time
import math
import socket
import threading
import random
import pickle
import os
import shutil
from dataclasses import dataclass
from typing import Dict, List, Optional, Union
from enum import Enum, auto
import hashlib

class TransferStatus(Enum):
    PENDING = auto()
    IN_PROGRESS = auto()
    COMPLETED = auto()
    FAILED = auto()

@dataclass
class FileChunk:
    chunk_id: int
    size: int  # in bytes
    checksum: str
    status: TransferStatus = TransferStatus.PENDING
    stored_node: Optional[str] = None

@dataclass
class FileTransfer:
    file_id: str
    file_name: str
    total_size: int  # in bytes
    chunks: List[FileChunk]
    status: TransferStatus = TransferStatus.PENDING
    created_at: float = time.time()
    completed_at: Optional[float] = None

class HeartbeatServer(threading.Thread):
    def __init__(self, node_id: str, port: int = 0):
        super().__init__(daemon=True)
        self.node_id = node_id
        self.port = port if port != 0 else random.randint(5001, 9999)
        self.running = True
        
    def run(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            try:
                s.bind(('0.0.0.0', self.port))
                print(f"Heartbeat server running on port {self.port}")
                while self.running:
                    try:
                        data, addr = s.recvfrom(1024)
                        if data == b'PING':
                            s.sendto(pickle.dumps({
                                'node_id': self.node_id, 
                                'status': 'ALIVE'
                            }), addr)
                    except ConnectionResetError:
                        continue
            except OSError as e:
                print(f"Heartbeat server error: {e}")
                self.port = 0
                    
    def stop(self):
        self.running = False

class HeartbeatSender(threading.Thread):
    def __init__(self, node_id: str, network_host: str, network_port: int, interval: float = 2):
        super().__init__(daemon=True)
        self.node_id = node_id
        self.network_host = network_host
        self.network_port = network_port
        self.interval = interval
        self.running = True
        
    def run(self):
        while self.running:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.settimeout(2)
                    s.connect((self.network_host, self.network_port))
                    s.sendall(pickle.dumps({
                        'action': 'HEARTBEAT',
                        'node_id': self.node_id
                    }))
                    response = pickle.loads(s.recv(1024))
                    if response.get('status') != 'ACK':
                        print(f"Heartbeat failed: {response.get('error', 'Unknown error')}")
                except Exception as e:
                    print(f"Heartbeat error: {e}")
                time.sleep(self.interval)
            
    def stop(self):
        self.running = False

class FileServer(threading.Thread):
    def __init__(self, node, port: int = 0):
        super().__init__(daemon=True)
        self.node = node
        self.port = port if port != 0 else random.randint(6001, 9999)
        self.running = True
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def run(self):
        try:
            self.socket.bind(('0.0.0.0', self.port))
            self.socket.listen(5)
            print(f"[Node {self.node.node_id}] File server running on port {self.port}")

            while self.running:
                try:
                    conn, addr = self.socket.accept()
                    threading.Thread(
                        target=self._handle_file_request,
                        args=(conn,),
                        daemon=True
                    ).start()
                except OSError as e:
                    if self.running:
                        print(f"[Node {self.node.node_id}] File server error: {e}")
                    break
        except OSError as e:
            print(f"[Node {self.node.node_id}] Failed to start file server: {e}")
            self.port = 0
        finally:
            self.socket.close()

    def _handle_file_request(self, conn):
        try:
            data = conn.recv(4096)
            if not data:
                return

            message = pickle.loads(data)

            if message['action'] == 'STORE_FILE':
                response = self.node._handle_store_file_request(message)
                conn.sendall(pickle.dumps(response))

            elif message['action'] == 'RETRIEVE_FILE':
                response = self.node._handle_retrieve_file_request(message)
                conn.sendall(pickle.dumps(response))

                # If successful, send file data
                if response['status'] == 'OK':
                    self._send_file_data(conn, message['file_id'])

            elif message['action'] == 'REPLICATE_FILE':
                response = self.node._handle_replicate_file_request(message)
                conn.sendall(pickle.dumps(response))

        except Exception as e:
            print(f"[Node {self.node.node_id}] File request error: {e}")
        finally:
            conn.close()

    def _send_file_data(self, conn, file_id):
        """Send actual file data to the requesting node"""
        try:
            if file_id in self.node.stored_files:
                file_transfer = self.node.stored_files[file_id]
                # Simulate sending file chunks
                for chunk in file_transfer.chunks:
                    chunk_data = {
                        'chunk_id': chunk.chunk_id,
                        'size': chunk.size,
                        'checksum': chunk.checksum,
                        'data': b'0' * chunk.size  # Simulated file data
                    }
                    conn.sendall(pickle.dumps(chunk_data))
                    time.sleep(0.01)  # Simulate network delay
        except Exception as e:
            print(f"[Node {self.node.node_id}] Error sending file data: {e}")

    def stop(self):
        self.running = False
        try:
            # Create temporary connection to unblock accept()
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect(('localhost', self.port))
        except:
            pass

class StorageVirtualNode:
    def __init__(
        self,
        node_id: str,
        cpu_capacity: int,
        memory_capacity: int,
        storage_capacity: int,
        bandwidth: int,
        network_host: str = 'localhost',
        network_port: int = 5000,
        heartbeat_port: int = 0
    ):
        self.node_id = node_id
        self.cpu_capacity = cpu_capacity
        self.memory_capacity = memory_capacity
        self.total_storage = storage_capacity * 1024 ** 3
        self.bandwidth = bandwidth * 1000000
        self.network_host = network_host
        self.network_port = network_port
        
        # Resource tracking
        self.used_storage = 0
        self.active_transfers = {}
        self.stored_files = {}
        self.network_utilization = 0
        self.connections = {}
        
        # Metrics
        self.total_requests_processed = 0
        self.total_data_transferred = 0
        self.failed_transfers = 0
        self.start_time = time.time()
        
        # Initialize heartbeat components
        self.heartbeat_server = HeartbeatServer(node_id, heartbeat_port)
        self.heartbeat_server.start()

        # Wait for heartbeat server to initialize
        start_time = time.time()
        while self.heartbeat_server.port == 0 and time.time() - start_time < 5:
            time.sleep(0.1)

        if self.heartbeat_server.port == 0:
            raise RuntimeError("Failed to initialize heartbeat server")

        # Initialize file server
        self.file_server = FileServer(self)
        self.file_server.start()

        # Wait for file server to initialize
        start_time = time.time()
        while self.file_server.port == 0 and time.time() - start_time < 5:
            time.sleep(0.1)

        if self.file_server.port == 0:
            raise RuntimeError("Failed to initialize file server")

        # Start heartbeat sender
        self.heartbeat_sender = HeartbeatSender(
            node_id=node_id,
            network_host=network_host,
            network_port=network_port
        )
        self.heartbeat_sender.start()

        # Register with network
        self._register_with_network()
        self._notify_active()

    def _register_with_network(self):
        """Register this node with the network controller"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.settimeout(5)
                s.connect((self.network_host, self.network_port))
                s.sendall(pickle.dumps({
                    'action': 'REGISTER',
                    'node_id': self.node_id,
                    'host': 'localhost',
                    'port': self.heartbeat_server.port,
                    'file_port': self.file_server.port,
                    'capacity': {
                        'cpu': self.cpu_capacity,
                        'memory': self.memory_capacity,
                        'storage': self.total_storage,
                        'bandwidth': self.bandwidth
                    }
                }))
                response = pickle.loads(s.recv(4096))
                if response.get('status') != 'OK':
                    raise RuntimeError(f"Registration failed: {response.get('error', 'Unknown error')}")
                print(f"[Node {self.node_id}] ✅ Connected to cloud successfully")
            except Exception as e:
                raise RuntimeError(f"Failed to connect to cloud: {e}")
            
    def _notify_active(self):
        """Send explicit active notification"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.settimeout(3)
                s.connect((self.network_host, self.network_port))
                s.sendall(pickle.dumps({
                    'action': 'ACTIVE_NOTIFICATION',
                    'node_id': self.node_id
                }))
                response = pickle.loads(s.recv(1024))
                if response.get('status') != 'ACK':
                    print(f"[Node {self.node_id}] Active notification failed")
            except Exception as e:
                print(f"[Node {self.node_id}] Active notification error: {e}")

    def add_connection(self, node_id: str, host: str, port: int, bandwidth: int):
        """Add a network connection to another node"""
        self.connections[node_id] = {
            'host': host,
            'port': port,
            'bandwidth': bandwidth * 1000000
        }

    def _calculate_chunk_size(self, file_size: int) -> int:
        """Determine optimal chunk size based on file size"""
        if file_size < 10 * 1024 * 1024:  # < 10MB
            return 512 * 1024  # 512KB chunks
        elif file_size < 100 * 1024 * 1024:  # < 100MB
            return 2 * 1024 * 1024  # 2MB chunks
        else:
            return 10 * 1024 * 1024  # 10MB chunks

    def _generate_chunks(self, file_id: str, file_size: int) -> List[FileChunk]:
        """Break file into chunks for transfer"""
        chunk_size = self._calculate_chunk_size(file_size)
        num_chunks = math.ceil(file_size / chunk_size)
        
        chunks = []
        for i in range(num_chunks):
            fake_checksum = hashlib.md5(f"{file_id}-{i}".encode()).hexdigest()
            actual_chunk_size = min(chunk_size, file_size - i * chunk_size)
            chunks.append(FileChunk(
                chunk_id=i,
                size=actual_chunk_size,
                checksum=fake_checksum
            ))
        
        return chunks

    def initiate_file_transfer(
        self,
        file_id: str,
        file_name: str,
        file_size: int,
        source_node: Optional[str] = None
    ) -> Optional[FileTransfer]:
        """Initiate a file storage request to this node"""
        if self.used_storage + file_size > self.total_storage:
            return None
        
        chunks = self._generate_chunks(file_id, file_size)
        transfer = FileTransfer(
            file_id=file_id,
            file_name=file_name,
            total_size=file_size,
            chunks=chunks
        )
        
        self.active_transfers[file_id] = transfer
        return transfer

    def process_chunk_transfer(
        self,
        file_id: str,
        chunk_id: int,
        source_node: str
    ) -> bool:
        """Process an incoming file chunk"""
        if file_id not in self.active_transfers:
            return False
        
        transfer = self.active_transfers[file_id]
        
        try:
            chunk = next(c for c in transfer.chunks if c.chunk_id == chunk_id)
        except StopIteration:
            return False
        
        # Simulate network transfer
        chunk_size_bits = chunk.size * 8
        available_bandwidth = min(
            self.bandwidth - self.network_utilization,
            self.connections.get(source_node, {}).get('bandwidth', 0)
        )
        
        if available_bandwidth <= 0:
            return False
        
        transfer_time = chunk_size_bits / available_bandwidth
        time.sleep(transfer_time)
        
        # Update status
        chunk.status = TransferStatus.COMPLETED
        chunk.stored_node = self.node_id
        self.network_utilization += available_bandwidth * 0.8
        self.total_data_transferred += chunk.size
        
        # Check if transfer complete
        if all(c.status == TransferStatus.COMPLETED for c in transfer.chunks):
            transfer.status = TransferStatus.COMPLETED
            transfer.completed_at = time.time()
            self.used_storage += transfer.total_size
            self.stored_files[file_id] = transfer
            del self.active_transfers[file_id]
            self.total_requests_processed += 1
        
        return True

    def upload_file_to_cloud(self, file_name: str, file_size: int, file_data: bytes = None) -> Dict:
        """Upload a file to the cloud storage network"""
        try:
            # Calculate file checksum
            checksum = hashlib.md5(file_data if file_data else b'0' * file_size).hexdigest()

            # Request upload from network controller
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(10)
                s.connect((self.network_host, self.network_port))
                s.sendall(pickle.dumps({
                    'action': 'UPLOAD_FILE',
                    'node_id': self.node_id,
                    'file_name': file_name,
                    'file_size': file_size,
                    'checksum': checksum
                }))
                response = pickle.loads(s.recv(4096))

            if response['status'] != 'OK':
                return response

            file_id = response['file_id']
            storage_nodes = response['storage_nodes']
            transfer_id = response['transfer_id']

            print(f"[Node {self.node_id}] ☁️  Uploading {file_name} to cloud storage")
            print(f"[Node {self.node_id}] 🔍 Transfer ID: {transfer_id}")
            print(f"[Node {self.node_id}] 📤 File being saved in cloud...")

            # Send file to each storage node
            successful_uploads = 0
            for node_id in storage_nodes:
                if self._send_file_to_node(node_id, file_id, file_name, file_size, file_data):
                    successful_uploads += 1
                    # Notify network controller that file was stored
                    self._notify_file_stored_on_node(file_id, node_id)

            if successful_uploads > 0:
                print(f"[Node {self.node_id}] File {file_name} uploaded successfully to {successful_uploads} nodes")
                return {
                    'status': 'OK',
                    'file_id': file_id,
                    'uploaded_to': successful_uploads,
                    'transfer_id': transfer_id
                }
            else:
                return {
                    'status': 'ERROR',
                    'error': 'Failed to upload to any storage nodes'
                }

        except Exception as e:
            return {
                'status': 'ERROR',
                'error': str(e)
            }

    def download_file_from_cloud(self, file_name: str = None, file_id: str = None) -> Dict:
        """Download a file from the cloud storage network"""
        try:
            # Request download from network controller
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(10)
                s.connect((self.network_host, self.network_port))
                s.sendall(pickle.dumps({
                    'action': 'DOWNLOAD_FILE',
                    'node_id': self.node_id,
                    'file_id': file_id,
                    'file_name': file_name
                }))
                response = pickle.loads(s.recv(4096))

            if response['status'] != 'OK':
                return response

            source_node = response['source_node']
            source_host = response['source_host']
            source_port = response['source_port']
            file_info = {
                'file_id': response['file_id'],
                'file_name': response['file_name'],
                'file_size': response['file_size']
            }
            transfer_id = response['transfer_id']

            print(f"[Node {self.node_id}] ☁️  Downloading {file_info['file_name']} from cloud")
            print(f"[Node {self.node_id}] 🔍 Transfer ID: {transfer_id}")
            print(f"[Node {self.node_id}] 📥 File being retrieved from cloud...")

            # Download file from source node
            file_data = self._retrieve_file_from_node(source_host, source_port, file_info['file_id'])

            if file_data:
                print(f"[Node {self.node_id}] File {file_info['file_name']} downloaded successfully")
                return {
                    'status': 'OK',
                    'file_data': file_data,
                    'file_info': file_info,
                    'transfer_id': transfer_id
                }
            else:
                return {
                    'status': 'ERROR',
                    'error': 'Failed to download file data'
                }

        except Exception as e:
            return {
                'status': 'ERROR',
                'error': str(e)
            }

    def list_cloud_files(self) -> Dict:
        """List all files available in the cloud"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)
                s.connect((self.network_host, self.network_port))
                s.sendall(pickle.dumps({
                    'action': 'LIST_FILES',
                    'node_id': self.node_id
                }))
                response = pickle.loads(s.recv(4096))
                return response
        except Exception as e:
            return {
                'status': 'ERROR',
                'error': str(e)
            }

    def retrieve_file(
        self,
        file_id: str,
        destination_node: str
    ) -> Optional[FileTransfer]:
        """Initiate file retrieval to another node"""
        if file_id not in self.stored_files:
            return None
        
        file_transfer = self.stored_files[file_id]
        return FileTransfer(
            file_id=f"retr-{file_id}-{time.time()}",
            file_name=file_transfer.file_name,
            total_size=file_transfer.total_size,
            chunks=[
                FileChunk(
                    chunk_id=c.chunk_id,
                    size=c.size,
                    checksum=c.checksum,
                    stored_node=destination_node
                )
                for c in file_transfer.chunks
            ]
        )

    def _send_file_to_node(self, node_id: str, file_id: str, file_name: str, file_size: int, file_data: bytes = None) -> bool:
        """Send file data to a specific storage node"""
        try:
            # Get node connection info from network controller
            node_info = self._get_node_info(node_id)
            if not node_info:
                print(f"[Node {self.node_id}] Could not get info for {node_id}")
                return False

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(10)
                s.connect((node_info['host'], node_info['file_port']))

                # Send store file request
                s.sendall(pickle.dumps({
                    'action': 'STORE_FILE',
                    'file_id': file_id,
                    'file_name': file_name,
                    'file_size': file_size,
                    'source_node': self.node_id
                }))

                response = pickle.loads(s.recv(1024))
                if response['status'] != 'OK':
                    return False

                # Send file chunks
                chunks = self._generate_chunks(file_id, file_size)
                for chunk in chunks:
                    chunk_data = file_data[chunk.chunk_id * chunk.size:(chunk.chunk_id + 1) * chunk.size] if file_data else b'0' * chunk.size
                    s.sendall(pickle.dumps({
                        'chunk_id': chunk.chunk_id,
                        'data': chunk_data,
                        'checksum': chunk.checksum
                    }))
                    time.sleep(0.01)  # Simulate network delay

                return True

        except Exception as e:
            print(f"[Node {self.node_id}] Failed to send file to {node_id}: {e}")
            return False

    def _retrieve_file_from_node(self, host: str, port: int, file_id: str) -> Optional[bytes]:
        """Retrieve file data from a storage node"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(10)
                s.connect((host, port))

                # Send retrieve file request
                s.sendall(pickle.dumps({
                    'action': 'RETRIEVE_FILE',
                    'file_id': file_id,
                    'requesting_node': self.node_id
                }))

                response = pickle.loads(s.recv(1024))
                if response['status'] != 'OK':
                    return None

                # Receive file chunks
                file_data = b''
                while True:
                    try:
                        chunk_data = pickle.loads(s.recv(4096))
                        file_data += chunk_data['data']
                    except:
                        break

                return file_data

        except Exception as e:
            print(f"[Node {self.node_id}] Failed to retrieve file from {host}:{port}: {e}")
            return None

    def _handle_store_file_request(self, message) -> Dict:
        """Handle incoming file storage request"""
        try:
            file_id = message['file_id']
            file_name = message['file_name']
            file_size = message['file_size']
            source_node = message['source_node']

            # Check if we have enough storage
            if self.used_storage + file_size > self.total_storage:
                return {
                    'status': 'ERROR',
                    'error': 'Insufficient storage space'
                }

            # Create file transfer record
            transfer = self.initiate_file_transfer(file_id, file_name, file_size, source_node)
            if not transfer:
                return {
                    'status': 'ERROR',
                    'error': 'Failed to initiate transfer'
                }

            print(f"[Node {self.node_id}] Accepting file storage: {file_name} from {source_node}")

            return {
                'status': 'OK',
                'message': 'Ready to receive file'
            }

        except Exception as e:
            return {
                'status': 'ERROR',
                'error': str(e)
            }

    def _handle_retrieve_file_request(self, message) -> Dict:
        """Handle incoming file retrieval request"""
        try:
            file_id = message['file_id']
            requesting_node = message['requesting_node']

            if file_id not in self.stored_files:
                return {
                    'status': 'ERROR',
                    'error': 'File not found'
                }

            file_transfer = self.stored_files[file_id]
            print(f"[Node {self.node_id}] Serving file: {file_transfer.file_name} to {requesting_node}")

            return {
                'status': 'OK',
                'file_name': file_transfer.file_name,
                'file_size': file_transfer.total_size
            }

        except Exception as e:
            return {
                'status': 'ERROR',
                'error': str(e)
            }

    def _handle_replicate_file_request(self, message) -> Dict:
        """Handle file replication request from another node"""
        try:
            file_id = message['file_id']
            file_name = message['file_name']
            file_size = message['file_size']
            source_node = message['source_node']
            source_host = message['source_host']
            source_port = message['source_port']

            print(f"[Node {self.node_id}] Replication request for {file_name} from {source_node}")

            # Check storage capacity
            if self.used_storage + file_size > self.total_storage:
                return {
                    'status': 'ERROR',
                    'error': 'Insufficient storage space'
                }

            # Download file from source node
            file_data = self._retrieve_file_from_node(source_host, source_port, file_id)

            if file_data:
                # Store the replicated file
                transfer = self.initiate_file_transfer(file_id, file_name, file_size, source_node)
                if transfer:
                    # Mark transfer as completed
                    transfer.status = TransferStatus.COMPLETED
                    transfer.completed_at = time.time()
                    self.used_storage += transfer.total_size
                    self.stored_files[file_id] = transfer

                    # Notify network controller
                    self._notify_file_stored(file_id)

                    print(f"[Node {self.node_id}] File {file_name} replicated successfully")

                    return {
                        'status': 'OK',
                        'message': 'Replication completed'
                    }

            return {
                'status': 'ERROR',
                'error': 'Failed to retrieve file for replication'
            }

        except Exception as e:
            return {
                'status': 'ERROR',
                'error': str(e)
            }

    def _notify_file_stored(self, file_id: str):
        """Notify network controller that file has been stored"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)
                s.connect((self.network_host, self.network_port))
                s.sendall(pickle.dumps({
                    'action': 'FILE_STORED',
                    'node_id': self.node_id,
                    'file_id': file_id
                }))
                response = pickle.loads(s.recv(1024))
                if response['status'] != 'OK':
                    print(f"[Node {self.node_id}] Failed to notify file storage: {response.get('error')}")
        except Exception as e:
            print(f"[Node {self.node_id}] Error notifying file storage: {e}")

    def _notify_file_stored_on_node(self, file_id: str, storage_node: str):
        """Notify network controller that file has been stored on a specific node"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)
                s.connect((self.network_host, self.network_port))
                s.sendall(pickle.dumps({
                    'action': 'FILE_STORED',
                    'node_id': storage_node,
                    'file_id': file_id
                }))
                response = pickle.loads(s.recv(1024))
                if response['status'] != 'OK':
                    print(f"[Node {self.node_id}] Failed to notify file storage on {storage_node}: {response.get('error')}")
        except Exception as e:
            print(f"[Node {self.node_id}] Error notifying file storage on {storage_node}: {e}")

    def _get_node_info(self, node_id: str) -> Optional[Dict]:
        """Get connection information for a specific node from network controller"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)
                s.connect((self.network_host, self.network_port))
                s.sendall(pickle.dumps({
                    'action': 'GET_NODE_INFO',
                    'node_id': self.node_id,
                    'target_node': node_id
                }))
                response = pickle.loads(s.recv(4096))

                if response['status'] == 'OK':
                    return response['node_info']
                else:
                    return None
        except Exception as e:
            print(f"[Node {self.node_id}] Error getting node info for {node_id}: {e}")
            return None

    def discover_file_locations(self, file_name: str) -> Dict:
        """Discover all locations where a file is stored"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)
                s.connect((self.network_host, self.network_port))
                s.sendall(pickle.dumps({
                    'action': 'DISCOVER_FILE',
                    'node_id': self.node_id,
                    'file_name': file_name
                }))
                response = pickle.loads(s.recv(4096))
                return response
        except Exception as e:
            return {
                'status': 'ERROR',
                'error': str(e)
            }

    def download_with_fallback(self, file_name: str) -> Dict:
        """Download file with automatic fallback to other nodes if primary fails"""
        try:
            # First, discover all locations of the file
            discovery_result = self.discover_file_locations(file_name)

            if discovery_result['status'] != 'OK':
                return discovery_result

            file_locations = discovery_result.get('locations', [])

            if not file_locations:
                return {
                    'status': 'ERROR',
                    'error': 'File not found in any location'
                }

            # Try downloading from each location until successful
            for location in file_locations:
                print(f"[Node {self.node_id}] Attempting download from {location['node_id']}")

                try:
                    file_data = self._retrieve_file_from_node(
                        location['host'],
                        location['port'],
                        location['file_id']
                    )

                    if file_data:
                        print(f"[Node {self.node_id}] Successfully downloaded {file_name} from {location['node_id']}")
                        return {
                            'status': 'OK',
                            'file_data': file_data,
                            'source_node': location['node_id'],
                            'file_info': {
                                'file_id': location['file_id'],
                                'file_name': file_name,
                                'file_size': len(file_data)
                            }
                        }
                except Exception as e:
                    print(f"[Node {self.node_id}] Failed to download from {location['node_id']}: {e}")
                    continue

            return {
                'status': 'ERROR',
                'error': 'Failed to download from all available locations'
            }

        except Exception as e:
            return {
                'status': 'ERROR',
                'error': str(e)
            }

    def get_node_health_status(self) -> Dict:
        """Get health status of this node"""
        storage_util = self.get_storage_utilization()
        network_util = self.get_network_utilization()

        # Calculate health score (0-100)
        storage_health = 100 - storage_util['utilization_percent']
        network_health = 100 - network_util['utilization_percent']

        # Simple average for overall health
        overall_health = (storage_health + network_health) / 2

        return {
            'node_id': self.node_id,
            'overall_health': overall_health,
            'storage_health': storage_health,
            'network_health': network_health,
            'files_stored': storage_util['files_stored'],
            'active_transfers': storage_util['active_transfers'],
            'uptime': time.time() - getattr(self, 'start_time', time.time())
        }

    def get_storage_utilization(self) -> Dict[str, Union[int, float]]:
        return {
            "used_bytes": self.used_storage,
            "total_bytes": self.total_storage,
            "utilization_percent": (self.used_storage / self.total_storage) * 100,
            "files_stored": len(self.stored_files),
            "active_transfers": len(self.active_transfers)
        }

    def get_network_utilization(self) -> Dict[str, Union[int, float, List[str]]]:
        return {
            "current_utilization_bps": self.network_utilization,
            "max_bandwidth_bps": self.bandwidth,
            "utilization_percent": (self.network_utilization / self.bandwidth) * 100,
            "connections": list(self.connections.keys())
        }

    def get_performance_metrics(self) -> Dict[str, int]:
        return {
            "total_requests_processed": self.total_requests_processed,
            "total_data_transferred_bytes": self.total_data_transferred,
            "failed_transfers": self.failed_transfers,
            "current_active_transfers": len(self.active_transfers)
        }

    def shutdown(self):
        """Graceful shutdown procedure"""
        print(f"[Node {self.node_id}] Shutting down...")
        self.heartbeat_sender.stop()
        self.heartbeat_server.stop()
        self.file_server.stop()
        self.heartbeat_sender.join()
        self.heartbeat_server.join()
        self.file_server.join()
        print(f"[Node {self.node_id}] Shutdown complete")