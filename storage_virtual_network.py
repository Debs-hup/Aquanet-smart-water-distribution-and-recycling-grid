import time
import socket
import threading
import pickle
import uuid
import hashlib
from typing import Dict, List, Optional, Tuple, Set
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum, auto
from encapsulation_visualizer import get_visualizer

class FileStatus(Enum):
    UPLOADING = auto()
    STORED = auto()
    REPLICATING = auto()
    FAILED = auto()

class EncapsulationLayer(Enum):
    APPLICATION = "Application Layer"
    TRANSPORT = "Transport Layer (TCP)"
    NETWORK = "Network Layer (IP)"
    DATA_LINK = "Data Link Layer"
    PHYSICAL = "Physical Layer"

@dataclass
class FileMetadata:
    file_id: str
    file_name: str
    file_size: int
    checksum: str
    upload_time: float
    status: FileStatus
    primary_nodes: Set[str]  # Nodes storing the file
    replication_factor: int = 3
    access_count: int = 0
    last_accessed: float = 0

@dataclass
class EncapsulationStep:
    layer: EncapsulationLayer
    action: str
    data_size: int
    headers_added: Dict[str, str]
    timestamp: float

class NetworkController(threading.Thread):
    def __init__(self, host: str = '0.0.0.0', port: int = 5000):
        super().__init__(daemon=True)
        self.host = host
        self.port = port
        self.nodes = {}
        self.lock = threading.Lock()
        self.running = False
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.heartbeat_timeout = 5
        self.transfer_operations = defaultdict(dict)

        # File management
        self.file_registry = {}  # file_id -> FileMetadata
        self.node_files = defaultdict(set)  # node_id -> set of file_ids
        self.replication_queue = []  # Files waiting for replication
        self.encapsulation_logs = defaultdict(list)  # transfer_id -> list of EncapsulationStep

        # Start status display thread
        self.status_thread = threading.Thread(target=self._display_status, daemon=True)
        self.status_thread.start()
        
    def run(self):
        self.running = True
        try:
            self.socket.bind((self.host, self.port))
            self.socket.listen()
            print(f"[Network] Controller started on {self.host}:{self.port}")
            
            while self.running:
                try:
                    conn, addr = self.socket.accept()
                    threading.Thread(
                        target=self._handle_connection,
                        args=(conn,),
                        daemon=True
                    ).start()
                except OSError as e:
                    if self.running:
                        print(f"[Network] Accept error: {e}")
                    break
        except OSError as e:
            print(f"[Network] Failed to start: {e}")
        finally:
            self.socket.close()
            
    def _handle_connection(self, conn):
        try:
            data = conn.recv(4096)
            if not data:
                return

            message = pickle.loads(data)
            with self.lock:
                if message['action'] == 'REGISTER':
                    node_id = message['node_id']
                    if node_id not in self.nodes:
                        print(f"[Cloud Controller] 🔗 Node {node_id} CONNECTED to cloud")
                        print(f"[Cloud Controller] 📊 Total nodes: {len(self.nodes) + 1}")
                    self.nodes[node_id] = {
                        'host': message['host'],
                        'port': message['port'],
                        'file_port': message.get('file_port', message['port']),
                        'capacity': message['capacity'],
                        'last_seen': 0,  # 0 means registered but not yet active
                        'status': 'registered',
                        'connect_time': time.time()
                    }
                    conn.sendall(pickle.dumps({'status': 'OK'}))

                elif message['action'] == 'ACTIVE_NOTIFICATION':
                    node_id = message['node_id']
                    if node_id in self.nodes:
                        if self.nodes[node_id]['status'] != 'active':
                            print(f"[Cloud Controller] ✅ Node {node_id} is now ACTIVE and ready")
                        self.nodes[node_id]['status'] = 'active'
                        self.nodes[node_id]['last_seen'] = time.time()
                        conn.sendall(pickle.dumps({'status': 'ACK'}))

                elif message['action'] == 'HEARTBEAT':
                    node_id = message['node_id']
                    if node_id in self.nodes:
                        if self.nodes[node_id]['status'] == 'registered':
                            print(f"[Network] Node {node_id} is now ACTIVE")
                            self.nodes[node_id]['status'] = 'active'
                        self.nodes[node_id]['last_seen'] = time.time()
                        conn.sendall(pickle.dumps({'status': 'ACK'}))
                    else:
                        conn.sendall(pickle.dumps({
                            'status': 'ERROR',
                            'error': 'Node not registered'
                        }))

                elif message['action'] == 'UPLOAD_FILE':
                    response = self._handle_file_upload(message)
                    conn.sendall(pickle.dumps(response))

                elif message['action'] == 'DOWNLOAD_FILE':
                    response = self._handle_file_download(message)
                    conn.sendall(pickle.dumps(response))

                elif message['action'] == 'LIST_FILES':
                    response = self._handle_list_files(message)
                    conn.sendall(pickle.dumps(response))

                elif message['action'] == 'FILE_STORED':
                    response = self._handle_file_stored_notification(message)
                    conn.sendall(pickle.dumps(response))

                elif message['action'] == 'REPLICATE_FILE':
                    response = self._handle_replication_request(message)
                    conn.sendall(pickle.dumps(response))

                elif message['action'] == 'DISCOVER_FILE':
                    response = self._handle_file_discovery(message)
                    conn.sendall(pickle.dumps(response))

                elif message['action'] == 'GET_NODE_HEALTH':
                    response = self._handle_node_health_request(message)
                    conn.sendall(pickle.dumps(response))

                elif message['action'] == 'GET_NODE_INFO':
                    response = self._handle_get_node_info(message)
                    conn.sendall(pickle.dumps(response))

                elif message['action'] == 'REGISTER_LOCAL_FILES':
                    response = self._handle_register_local_files(message)
                    conn.sendall(pickle.dumps(response))
        except Exception as e:
            print(f"[Network] Connection error: {e}")
        finally:
            conn.close()

    def _handle_file_upload(self, message):
        """Handle file upload request from a node"""
        try:
            file_name = message['file_name']
            file_size = message['file_size']
            file_checksum = message.get('checksum', '')
            requesting_node = message['node_id']

            # Generate unique file ID
            file_id = str(uuid.uuid4())

            # Select nodes for storage (including replication)
            storage_nodes = self._select_storage_nodes(file_size, exclude_node=requesting_node)

            if not storage_nodes:
                return {
                    'status': 'ERROR',
                    'error': 'No available storage nodes'
                }

            # Create file metadata
            file_metadata = FileMetadata(
                file_id=file_id,
                file_name=file_name,
                file_size=file_size,
                checksum=file_checksum,
                upload_time=time.time(),
                status=FileStatus.UPLOADING,
                primary_nodes=set(storage_nodes)
            )

            self.file_registry[file_id] = file_metadata

            # Log encapsulation process
            transfer_id = f"upload_{file_id}"
            self._log_encapsulation_process(transfer_id, file_size, "UPLOAD")

            # Start visualization
            visualizer = get_visualizer()
            visualizer.start_transfer_visualization(transfer_id, "FILE UPLOAD", file_name, file_size)

            print(f"[Cloud] File '{file_name}' saved in cloud storage ☁️")
            print(f"[Cloud] File is now available for download from any node")

            # Complete visualization after a short delay (simulating processing)
            threading.Timer(1.0, lambda: get_visualizer().complete_transfer_visualization(transfer_id, True)).start()

            return {
                'status': 'OK',
                'file_id': file_id,
                'storage_nodes': storage_nodes,
                'transfer_id': transfer_id
            }

        except Exception as e:
            return {
                'status': 'ERROR',
                'error': str(e)
            }

    def _handle_file_download(self, message):
        """Handle file download request"""
        try:
            file_id = message.get('file_id')
            file_name = message.get('file_name')
            requesting_node = message['node_id']

            # Find file by ID or name
            target_file = None
            if file_id and file_id in self.file_registry:
                target_file = self.file_registry[file_id]
            elif file_name:
                for fid, metadata in self.file_registry.items():
                    if metadata.file_name == file_name and metadata.status == FileStatus.STORED:
                        target_file = metadata
                        file_id = fid
                        break

            if not target_file:
                return {
                    'status': 'ERROR',
                    'error': 'File not found'
                }

            # Find available nodes with the file
            available_nodes = [node for node in target_file.primary_nodes
                             if node in self.nodes and self.nodes[node]['status'] == 'active']

            if not available_nodes:
                return {
                    'status': 'ERROR',
                    'error': 'File not available (all storage nodes offline)'
                }

            # Select best node for download (load balancing)
            source_node = self._select_download_node(available_nodes)

            # Update access statistics
            target_file.access_count += 1
            target_file.last_accessed = time.time()

            # Log encapsulation process
            transfer_id = f"download_{file_id}_{time.time()}"
            self._log_encapsulation_process(transfer_id, target_file.file_size, "DOWNLOAD")

            # Start visualization
            visualizer = get_visualizer()
            visualizer.start_transfer_visualization(transfer_id, "FILE DOWNLOAD", target_file.file_name, target_file.file_size)

            print(f"[Cloud] Serving file '{target_file.file_name}' from cloud storage ☁️")
            print(f"[Cloud] File retrieved and ready for download")

            # Complete visualization after a short delay (simulating processing)
            threading.Timer(1.5, lambda: get_visualizer().complete_transfer_visualization(transfer_id, True)).start()

            return {
                'status': 'OK',
                'file_id': file_id,
                'file_name': target_file.file_name,
                'file_size': target_file.file_size,
                'source_node': source_node,
                'source_host': self.nodes[source_node]['host'],
                'source_port': self.nodes[source_node]['file_port'],
                'transfer_id': transfer_id
            }

        except Exception as e:
            return {
                'status': 'ERROR',
                'error': str(e)
            }

    def _handle_list_files(self, message):
        """Handle request to list available files"""
        try:
            files_list = []
            for file_id, metadata in self.file_registry.items():
                if metadata.status == FileStatus.STORED:
                    available_nodes = [node for node in metadata.primary_nodes
                                     if node in self.nodes and self.nodes[node]['status'] == 'active']

                    files_list.append({
                        'file_id': file_id,
                        'file_name': metadata.file_name,
                        'file_size': metadata.file_size,
                        'upload_time': metadata.upload_time,
                        'access_count': metadata.access_count,
                        'available_copies': len(available_nodes)
                    })

            return {
                'status': 'OK',
                'files': files_list
            }
        except Exception as e:
            return {
                'status': 'ERROR',
                'error': str(e)
            }

    def _handle_file_stored_notification(self, message):
        """Handle notification that a file has been successfully stored"""
        try:
            file_id = message['file_id']
            node_id = message['node_id']

            if file_id in self.file_registry:
                metadata = self.file_registry[file_id]
                self.node_files[node_id].add(file_id)

                # Check if all primary nodes have stored the file
                stored_nodes = sum(1 for node in metadata.primary_nodes
                                 if file_id in self.node_files[node])

                if stored_nodes >= metadata.replication_factor:
                    metadata.status = FileStatus.STORED
                    print(f"[Network] File {metadata.file_name} successfully stored with {stored_nodes} replicas")

                return {'status': 'OK'}
            else:
                return {'status': 'ERROR', 'error': 'File not found'}

        except Exception as e:
            return {'status': 'ERROR', 'error': str(e)}

    def _handle_replication_request(self, message):
        """Handle file replication request"""
        try:
            file_id = message['file_id']
            source_node = message['source_node']
            target_node = message['target_node']

            if file_id in self.file_registry:
                metadata = self.file_registry[file_id]
                metadata.primary_nodes.add(target_node)

                print(f"[Network] File {metadata.file_name} replicated from {source_node} to {target_node}")

                return {'status': 'OK'}
            else:
                return {'status': 'ERROR', 'error': 'File not found'}

        except Exception as e:
            return {'status': 'ERROR', 'error': str(e)}

    def _handle_file_discovery(self, message):
        """Handle file discovery request"""
        try:
            file_name = message['file_name']
            requesting_node = message['node_id']

            locations = []

            # Search through all files to find matches
            for file_id, metadata in self.file_registry.items():
                if metadata.file_name == file_name and metadata.status == FileStatus.STORED:
                    # Find all active nodes storing this file
                    for node_id in metadata.primary_nodes:
                        if node_id in self.nodes and self.nodes[node_id]['status'] == 'active':
                            node_info = self.nodes[node_id]
                            locations.append({
                                'file_id': file_id,
                                'node_id': node_id,
                                'host': node_info['host'],
                                'port': node_info['file_port'],
                                'last_seen': node_info['last_seen'],
                                'health_score': self._calculate_node_health(node_id)
                            })

            # Sort by health score (best first)
            locations.sort(key=lambda x: x['health_score'], reverse=True)

            print(f"[Network] File discovery for '{file_name}': found {len(locations)} locations")

            return {
                'status': 'OK',
                'file_name': file_name,
                'locations': locations,
                'total_locations': len(locations)
            }

        except Exception as e:
            return {
                'status': 'ERROR',
                'error': str(e)
            }

    def _handle_node_health_request(self, message):
        """Handle node health status request"""
        try:
            requesting_node = message['node_id']

            health_info = {}
            for node_id, node_info in self.nodes.items():
                if node_info['status'] == 'active':
                    health_info[node_id] = {
                        'health_score': self._calculate_node_health(node_id),
                        'last_seen': node_info['last_seen'],
                        'files_stored': len(self.node_files[node_id]),
                        'storage_capacity': node_info['capacity']['storage'],
                        'bandwidth_capacity': node_info['capacity']['bandwidth']
                    }

            return {
                'status': 'OK',
                'nodes': health_info
            }

        except Exception as e:
            return {
                'status': 'ERROR',
                'error': str(e)
            }

    def _handle_get_node_info(self, message):
        """Handle request for node connection information"""
        try:
            target_node = message['target_node']

            if target_node in self.nodes:
                node_info = self.nodes[target_node]
                return {
                    'status': 'OK',
                    'node_info': {
                        'host': node_info['host'],
                        'port': node_info['port'],
                        'file_port': node_info['file_port'],
                        'status': node_info['status']
                    }
                }
            else:
                return {
                    'status': 'ERROR',
                    'error': f'Node {target_node} not found'
                }

        except Exception as e:
            return {
                'status': 'ERROR',
                'error': str(e)
            }

    def _handle_register_local_files(self, message):
        """Handle registration of local files as cloud files"""
        try:
            node_id = message['node_id']
            local_files = message['local_files']

            registered_count = 0
            for file_info in local_files:
                file_name = file_info['name']
                file_size = file_info['size']
                file_path = file_info['path']

                # Create a unique file ID for this local file
                file_id = f"local_{node_id}_{file_name}_{hash(file_path)}"

                # Check if file already registered
                if file_id not in self.file_registry:
                    # Create file metadata
                    file_metadata = FileMetadata(
                        file_id=file_id,
                        file_name=file_name,
                        file_size=file_size,
                        checksum="",
                        upload_time=time.time(),
                        status=FileStatus.STORED,
                        primary_nodes={node_id},
                        replication_factor=1
                    )

                    self.file_registry[file_id] = file_metadata
                    self.node_files[node_id].add(file_id)
                    registered_count += 1

            print(f"[Cloud] Registered {registered_count} local files from {node_id} as cloud files")

            return {
                'status': 'OK',
                'registered_files': registered_count
            }

        except Exception as e:
            return {
                'status': 'ERROR',
                'error': str(e)
            }

    def _calculate_node_health(self, node_id: str) -> float:
        """Calculate health score for a node (0-100)"""
        if node_id not in self.nodes:
            return 0.0

        node_info = self.nodes[node_id]

        # Factors affecting health:
        # 1. How recently the node was seen (recency score)
        current_time = time.time()
        time_since_seen = current_time - node_info['last_seen']
        recency_score = max(0, 100 - (time_since_seen * 10))  # Decrease by 10 per second

        # 2. Storage utilization (lower is better)
        files_stored = len(self.node_files[node_id])
        total_storage = node_info['capacity']['storage']
        used_storage = sum(self.file_registry[fid].file_size
                          for fid in self.node_files[node_id]
                          if fid in self.file_registry)
        storage_util = (used_storage / total_storage) * 100 if total_storage > 0 else 100
        storage_score = max(0, 100 - storage_util)

        # 3. Active transfers (fewer is better for load balancing)
        active_transfers = sum(1 for transfers in self.transfer_operations.values()
                             if node_id in transfers)
        transfer_score = max(0, 100 - (active_transfers * 20))

        # Weighted average
        health_score = (recency_score * 0.4 + storage_score * 0.4 + transfer_score * 0.2)

        return min(100.0, max(0.0, health_score))

    def check_node_status(self):
        """Check which nodes are offline"""
        current_time = time.time()
        offline_nodes = []

        with self.lock:
            for node_id, info in list(self.nodes.items()):
                if info['status'] == 'registered':
                    continue  # New node not yet active

                if current_time - info['last_seen'] > self.heartbeat_timeout:
                    offline_nodes.append(node_id)
                    print(f"[Cloud Controller] ❌ Node {node_id} DISCONNECTED from cloud")
                    print(f"[Cloud Controller] 📊 Remaining nodes: {len(self.nodes) - 1}")

                    # Handle file replication for offline node
                    self._handle_node_failure(node_id)

                    del self.nodes[node_id]

        return offline_nodes

    def _display_status(self):
        """Display cloud controller status periodically"""
        while self.running:
            time.sleep(10)  # Update every 10 seconds
            if self.running:
                with self.lock:
                    active_nodes = sum(1 for n in self.nodes.values() if n['status'] == 'active')
                    total_files = len(self.file_registry)
                    stored_files = sum(1 for f in self.file_registry.values() if f.status == FileStatus.STORED)

                    print(f"\n[Cloud Controller] 📊 Status Update:")
                    print(f"  🖥️  Connected Nodes: {active_nodes}")
                    print(f"  📁 Total Files: {total_files}")
                    print(f"  💾 Stored Files: {stored_files}")
                    print(f"  🔄 Replication Queue: {len(self.replication_queue)}")

    def _select_storage_nodes(self, file_size, exclude_node=None, replication_factor=3):
        """Select optimal nodes for file storage"""
        available_nodes = []

        for node_id, info in self.nodes.items():
            if info['status'] == 'active' and node_id != exclude_node:
                # Check if node has enough storage capacity
                used_storage = sum(self.file_registry[fid].file_size
                                 for fid in self.node_files[node_id]
                                 if fid in self.file_registry)
                available_storage = info['capacity']['storage'] - used_storage

                if available_storage >= file_size:
                    available_nodes.append((node_id, available_storage))

        # Sort by available storage (descending) and select top nodes
        available_nodes.sort(key=lambda x: x[1], reverse=True)
        selected_nodes = [node[0] for node in available_nodes[:replication_factor]]

        return selected_nodes

    def _select_download_node(self, available_nodes):
        """Select best node for download based on advanced load balancing"""
        if not available_nodes:
            return None

        if len(available_nodes) == 1:
            return available_nodes[0]

        # Advanced load balancing: consider multiple factors
        node_scores = {}

        for node_id in available_nodes:
            # Calculate health score
            health_score = self._calculate_node_health(node_id)

            # Consider active transfers
            active_transfers = sum(1 for transfers in self.transfer_operations.values()
                                 if node_id in transfers)
            transfer_penalty = active_transfers * 10

            # Consider recent access (to distribute load)
            current_time = time.time()
            last_seen = self.nodes[node_id]['last_seen']
            recency_bonus = min(10, current_time - last_seen)

            # Final score (higher is better)
            final_score = health_score - transfer_penalty + recency_bonus
            node_scores[node_id] = final_score

        # Select node with highest score
        best_node = max(node_scores.keys(), key=lambda x: node_scores[x])

        print(f"[Network] Load balancing selected {best_node} (score: {node_scores[best_node]:.1f})")
        return best_node

    def _log_encapsulation_process(self, transfer_id, data_size, operation):
        """Log the encapsulation/decapsulation process"""
        visualizer = get_visualizer()

        if operation == "UPLOAD":
            # Encapsulation process (adding headers)

            # Application Layer
            visualizer.add_encapsulation_layer(
                transfer_id,
                "Application Layer",
                0,
                {"Content-Type": "application/octet-stream", "Operation": "File Upload"}
            )

            # Transport Layer (TCP)
            visualizer.add_encapsulation_layer(
                transfer_id,
                "TCP Header",
                20,
                {
                    "Source Port": "random",
                    "Dest Port": "5000",
                    "Sequence Number": "auto",
                    "Acknowledgment": "auto",
                    "Window Size": "65535"
                }
            )

            # Network Layer (IP)
            visualizer.add_encapsulation_layer(
                transfer_id,
                "IP Header",
                20,
                {
                    "Version": "4",
                    "Protocol": "TCP (6)",
                    "Source IP": "192.168.1.x",
                    "Dest IP": "192.168.1.y",
                    "TTL": "64"
                }
            )

            # Data Link Layer
            visualizer.add_encapsulation_layer(
                transfer_id,
                "Ethernet Header",
                14,
                {
                    "Source MAC": "xx:xx:xx:xx:xx:xx",
                    "Dest MAC": "yy:yy:yy:yy:yy:yy",
                    "EtherType": "0x0800 (IPv4)"
                }
            )

            # Physical Layer (no additional headers, just transmission)
            visualizer.add_encapsulation_layer(
                transfer_id,
                "Physical Layer",
                0,
                {"Medium": "Electrical signals", "Encoding": "Manchester"}
            )

        elif operation == "DOWNLOAD":
            # Decapsulation process (removing headers)

            # Physical Layer
            visualizer.add_decapsulation_layer(
                transfer_id,
                "Physical Layer Processing",
                0,
                {"Action": "Signal reception and decoding"}
            )

            # Data Link Layer
            visualizer.add_decapsulation_layer(
                transfer_id,
                "Ethernet Header",
                14,
                {"Action": "Frame validation and MAC address check"}
            )

            # Network Layer (IP)
            visualizer.add_decapsulation_layer(
                transfer_id,
                "IP Header",
                20,
                {"Action": "Routing validation and TTL check"}
            )

            # Transport Layer (TCP)
            visualizer.add_decapsulation_layer(
                transfer_id,
                "TCP Header",
                20,
                {"Action": "Segment reassembly and error checking"}
            )

            # Application Layer
            visualizer.add_decapsulation_layer(
                transfer_id,
                "Application Layer",
                0,
                {"Action": "File data extraction and validation"}
            )

        # Store in logs for later retrieval
        self.encapsulation_logs[transfer_id] = {
            'operation': operation,
            'data_size': data_size,
            'timestamp': time.time()
        }

    def _handle_node_failure(self, failed_node_id):
        """Handle file synchronization when a node fails"""
        affected_files = self.node_files[failed_node_id].copy()
        files_removed = 0
        files_replicated = 0

        print(f"[Cloud] 🔄 Synchronizing cloud files after {failed_node_id} disconnection...")

        for file_id in affected_files:
            if file_id in self.file_registry:
                metadata = self.file_registry[file_id]
                metadata.primary_nodes.discard(failed_node_id)

                # Check if this was a local file (only stored on the failed node)
                if file_id.startswith(f"local_{failed_node_id}_"):
                    # This is a local file from the failed node - remove it from cloud
                    print(f"[Cloud] 📁 Removing '{metadata.file_name}' from cloud (node {failed_node_id} offline)")
                    del self.file_registry[file_id]
                    files_removed += 1
                else:
                    # Check if we need more replicas for uploaded files
                    active_replicas = sum(1 for node in metadata.primary_nodes
                                        if node in self.nodes and self.nodes[node]['status'] == 'active')

                    if active_replicas < metadata.replication_factor:
                        print(f"[Cloud] 🔄 File {metadata.file_name} needs re-replication due to node failure")
                        self.replication_queue.append(file_id)
                        files_replicated += 1
                    elif active_replicas == 0:
                        # No replicas left - remove from cloud
                        print(f"[Cloud] 📁 Removing '{metadata.file_name}' from cloud (no replicas available)")
                        del self.file_registry[file_id]
                        files_removed += 1

        # Clear the failed node's file list
        del self.node_files[failed_node_id]

        print(f"[Cloud] ✅ Synchronization complete: {files_removed} files removed, {files_replicated} files queued for replication")

    def _process_replication_queue(self):
        """Process files waiting for replication"""
        while self.replication_queue:
            file_id = self.replication_queue.pop(0)

            if file_id not in self.file_registry:
                continue

            metadata = self.file_registry[file_id]

            # Find active nodes with the file
            source_nodes = [node for node in metadata.primary_nodes
                          if node in self.nodes and self.nodes[node]['status'] == 'active']

            if not source_nodes:
                print(f"[Network] Cannot replicate {metadata.file_name} - no source nodes available")
                continue

            # Find nodes that need the file
            needed_replicas = metadata.replication_factor - len(source_nodes)
            if needed_replicas <= 0:
                continue

            # Select target nodes for replication
            target_nodes = self._select_replication_targets(metadata, source_nodes, needed_replicas)

            if target_nodes:
                source_node = source_nodes[0]  # Use first available source
                for target_node in target_nodes:
                    self._initiate_replication(file_id, source_node, target_node)

    def _select_replication_targets(self, metadata, exclude_nodes, count):
        """Select nodes for file replication"""
        available_nodes = []

        for node_id, info in self.nodes.items():
            if (info['status'] == 'active' and
                node_id not in exclude_nodes and
                node_id not in metadata.primary_nodes):

                # Check storage capacity
                used_storage = sum(self.file_registry[fid].file_size
                                 for fid in self.node_files[node_id]
                                 if fid in self.file_registry)
                available_storage = info['capacity']['storage'] - used_storage

                if available_storage >= metadata.file_size:
                    available_nodes.append((node_id, available_storage))

        # Sort by available storage and select top nodes
        available_nodes.sort(key=lambda x: x[1], reverse=True)
        return [node[0] for node in available_nodes[:count]]

    def _initiate_replication(self, file_id, source_node, target_node):
        """Initiate file replication between two nodes"""
        try:
            metadata = self.file_registry[file_id]
            source_info = self.nodes[source_node]
            target_info = self.nodes[target_node]

            print(f"[Network] Replicating {metadata.file_name} from {source_node} to {target_node}")

            # Send replication request to target node
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)
                s.connect((target_info['host'], target_info['file_port']))
                s.sendall(pickle.dumps({
                    'action': 'REPLICATE_FILE',
                    'file_id': file_id,
                    'file_name': metadata.file_name,
                    'file_size': metadata.file_size,
                    'source_node': source_node,
                    'source_host': source_info['host'],
                    'source_port': source_info['file_port']
                }))

                response = pickle.loads(s.recv(1024))
                if response['status'] == 'OK':
                    metadata.primary_nodes.add(target_node)
                    self.node_files[target_node].add(file_id)
                    print(f"[Network] Replication successful: {metadata.file_name} -> {target_node}")
                else:
                    print(f"[Network] Replication failed: {response.get('error', 'Unknown error')}")

        except Exception as e:
            print(f"[Network] Replication error: {e}")

    def stop(self):
        self.running = False
        # Create temporary connection to unblock accept()
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((self.host, self.port))
        except:
            pass

class StorageVirtualNetwork:
    def __init__(self, host: str = '0.0.0.0', port: int = 5000):
        self.controller = NetworkController(host, port)
        self.controller.start()
        self.heartbeat_checker = threading.Thread(
            target=self._check_heartbeats,
            daemon=True
        )
        self.heartbeat_checker.start()

        # Start replication manager
        self.replication_manager = threading.Thread(
            target=self._manage_replication,
            daemon=True
        )
        self.replication_manager.start()
        
    def _check_heartbeats(self):
        while self.controller.running:
            self.controller.check_node_status()
            time.sleep(1)

    def _manage_replication(self):
        """Manage file replication in the background"""
        while self.controller.running:
            with self.controller.lock:
                self.controller._process_replication_queue()
            time.sleep(5)  # Check every 5 seconds
            
    def add_node(self, node_id: str, host: str, port: int, capacity: Dict):
        """Manually add a node"""
        with self.controller.lock:
            self.controller.nodes[node_id] = {
                'host': host,
                'port': port,
                'capacity': capacity,
                'last_seen': time.time(),
                'status': 'active'
            }
            print(f"[Network] Manually added node {node_id}")
            
    def connect_nodes(self, node1_id: str, node2_id: str, bandwidth: int):
        """Connect two nodes with specified bandwidth"""
        if node1_id in self.controller.nodes and node2_id in self.controller.nodes:
            self._send_connection_info(node1_id, node2_id, bandwidth)
            self._send_connection_info(node2_id, node1_id, bandwidth)
            return True
        return False
        
    def _send_connection_info(self, target_node: str, peer_node: str, bandwidth: int):
        """Send connection information to a node"""
        peer_info = self.controller.nodes[peer_node]
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.settimeout(2)
                s.connect((peer_info['host'], peer_info['port']))
                s.sendall(pickle.dumps({
                    'action': 'CONNECT',
                    'node_id': peer_node,
                    'host': peer_info['host'],
                    'port': peer_info['port'],
                    'bandwidth': bandwidth
                }))
            except ConnectionRefusedError:
                print(f"[Network] Could not connect to node {peer_node}")

    def upload_file(self, node_id: str, file_name: str, file_size: int, checksum: str = ""):
        """Initiate file upload through the network controller"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)
                s.connect((self.controller.host, self.controller.port))
                s.sendall(pickle.dumps({
                    'action': 'UPLOAD_FILE',
                    'node_id': node_id,
                    'file_name': file_name,
                    'file_size': file_size,
                    'checksum': checksum
                }))
                response = pickle.loads(s.recv(4096))
                return response
        except Exception as e:
            return {'status': 'ERROR', 'error': str(e)}

    def download_file(self, node_id: str, file_id: str = None, file_name: str = None):
        """Initiate file download through the network controller"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)
                s.connect((self.controller.host, self.controller.port))
                s.sendall(pickle.dumps({
                    'action': 'DOWNLOAD_FILE',
                    'node_id': node_id,
                    'file_id': file_id,
                    'file_name': file_name
                }))
                response = pickle.loads(s.recv(4096))
                return response
        except Exception as e:
            return {'status': 'ERROR', 'error': str(e)}

    def list_files(self, node_id: str):
        """List all available files in the network"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)
                s.connect((self.controller.host, self.controller.port))
                s.sendall(pickle.dumps({
                    'action': 'LIST_FILES',
                    'node_id': node_id
                }))
                response = pickle.loads(s.recv(4096))
                return response
        except Exception as e:
            return {'status': 'ERROR', 'error': str(e)}

    def get_encapsulation_log(self, transfer_id: str):
        """Get encapsulation log for a specific transfer"""
        with self.controller.lock:
            return self.controller.encapsulation_logs.get(transfer_id, [])

    def get_visualization_statistics(self):
        """Get visualization and transfer statistics"""
        visualizer = get_visualizer()
        return visualizer.get_transfer_statistics()

    def print_visualization_statistics(self):
        """Print visualization statistics"""
        visualizer = get_visualizer()
        visualizer.print_statistics()

    def get_network_stats(self) -> Dict[str, float]:
        """Get overall network statistics"""
        with self.controller.lock:
            total_bandwidth = sum(n['capacity']['bandwidth'] for n in self.controller.nodes.values())
            used_bandwidth = sum(n['capacity']['bandwidth'] * 0.5 for n in self.controller.nodes.values())  # Simulated
            total_storage = sum(n['capacity']['storage'] for n in self.controller.nodes.values())

            # Calculate actual used storage from file registry
            actual_used_storage = 0
            for file_id, metadata in self.controller.file_registry.items():
                if metadata.status == FileStatus.STORED:
                    actual_used_storage += metadata.file_size * len(metadata.primary_nodes)

            return {
                "total_nodes": len(self.controller.nodes),
                "active_nodes": sum(1 for n in self.controller.nodes.values() if n['status'] == 'active'),
                "total_bandwidth_bps": total_bandwidth,
                "used_bandwidth_bps": used_bandwidth,
                "bandwidth_utilization": (used_bandwidth / total_bandwidth) * 100 if total_bandwidth > 0 else 0,
                "total_storage_bytes": total_storage,
                "used_storage_bytes": actual_used_storage,
                "storage_utilization": (actual_used_storage / total_storage) * 100 if total_storage > 0 else 0,
                "active_transfers": sum(len(t) for t in self.controller.transfer_operations.values()),
                "total_files": len(self.controller.file_registry),
                "stored_files": sum(1 for f in self.controller.file_registry.values() if f.status == FileStatus.STORED),
                "replication_queue_size": len(self.controller.replication_queue)
            }

    def shutdown(self):
        """Graceful shutdown"""
        print("[Network] Shutting down controller...")
        self.controller.stop()
        self.controller.join()
        print("[Network] Controller shutdown complete")