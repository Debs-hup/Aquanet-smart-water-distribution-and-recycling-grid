#!/usr/bin/env python3
"""
Interactive Cloud Storage Node
Each node acts as both client and server with an interactive menu interface.
"""

import os
import sys
import time
import threading
import tempfile
from storage_virtual_node import StorageVirtualNode
from encapsulation_visualizer import set_visualization_mode, VisualizationMode

class InteractiveCloudNode:
    def __init__(self, node_id: str, network_host: str = 'localhost', network_port: int = 5000):
        self.node_id = node_id
        self.network_host = network_host
        self.network_port = network_port
        self.node = None
        self.running = True
        self.local_files = {}  # Track local files available for upload
        
        # Create a local directory for this node
        self.local_dir = f"node_{node_id}_files"
        os.makedirs(self.local_dir, exist_ok=True)
        
        # Create some sample files
        self._create_sample_files()
        
    def _create_sample_files(self):
        """Create sample files for demonstration"""
        sample_files = [
            ("document.txt", "This is a sample document from node " + self.node_id),
            ("data.csv", "Name,Age,City\nJohn,25,NYC\nJane,30,LA\nBob,35,Chicago"),
            ("config.json", '{"node_id": "' + self.node_id + '", "type": "storage_node"}')
        ]
        
        for filename, content in sample_files:
            filepath = os.path.join(self.local_dir, filename)
            with open(filepath, 'w') as f:
                f.write(content)
            self.local_files[filename] = filepath
    
    def start_node(self):
        """Start the cloud storage node"""
        try:
            print(f"🚀 Starting cloud storage node: {self.node_id}")
            print(f"🔗 Connecting to cloud at {self.network_host}:{self.network_port}")
            
            self.node = StorageVirtualNode(
                node_id=self.node_id,
                cpu_capacity=4,
                memory_capacity=16,
                storage_capacity=1000,  # 1TB
                bandwidth=1000,  # 1Gbps
                network_host=self.network_host,
                network_port=self.network_port
            )
            
            print(f"✅ Node {self.node_id} connected to cloud successfully!")
            print(f"📁 Local files directory: {self.local_dir}")

            # Register local files with cloud
            self._register_local_files_with_cloud()

            return True
            
        except Exception as e:
            print(f"❌ Failed to start node: {e}")
            return False

    def _register_local_files_with_cloud(self):
        """Register local files with the cloud so they appear as cloud files"""
        try:
            import socket
            import pickle
            import os

            # Prepare local files info
            local_files_info = []
            for filename, filepath in self.local_files.items():
                if os.path.exists(filepath):
                    file_size = os.path.getsize(filepath)
                    local_files_info.append({
                        'name': filename,
                        'size': file_size,
                        'path': filepath
                    })

            # Send to cloud controller
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)
                s.connect((self.network_host, self.network_port))
                s.sendall(pickle.dumps({
                    'action': 'REGISTER_LOCAL_FILES',
                    'node_id': self.node_id,
                    'local_files': local_files_info
                }))
                response = pickle.loads(s.recv(4096))

                if response['status'] == 'OK':
                    print(f"☁️  Registered {response['registered_files']} local files with cloud")
                    print(f"📋 These files are now available for download from any node")
                else:
                    print(f"❌ Failed to register local files: {response['error']}")

        except Exception as e:
            print(f"❌ Error registering local files: {e}")
    
    def show_menu(self):
        """Display the interactive menu"""
        print(f"\n{'='*60}")
        print(f"🌐 CLOUD STORAGE NODE: {self.node_id}")
        print(f"{'='*60}")
        print("📋 Available Commands:")
        print("  1. ls        - List local files available for upload")
        print("  2. upload    - Upload a file to the cloud")
        print("  3. download  - Download a file from the cloud")
        print("  4. cloud-ls  - List all files in the cloud")
        print("  5. discover  - Discover file locations in cloud")
        print("  6. stats     - Show node statistics")
        print("  7. cloud-stats - Show cloud network statistics")
        print("  8. help      - Show this menu")
        print("  9. exit      - Shutdown node and exit")
        print(f"{'='*60}")
    
    def cmd_ls(self):
        """List local files available for upload"""
        print(f"\n📁 Local files in {self.node_id}:")
        print("=" * 50)
        
        if not self.local_files:
            print("📭 No local files available")
            return
        
        print(f"{'File Name':<20} {'Size':<10} {'Path'}")
        print("-" * 50)
        
        for filename, filepath in self.local_files.items():
            if os.path.exists(filepath):
                size = os.path.getsize(filepath)
                size_str = self._format_size(size)
                print(f"{filename:<20} {size_str:<10} {filepath}")
            else:
                print(f"{filename:<20} {'MISSING':<10} {filepath}")
        
        print("=" * 50)
    
    def cmd_upload(self):
        """Upload a file to the cloud"""
        if not self.node:
            print("❌ Node not connected to cloud")
            return
        
        print("\n📤 Upload File to Cloud")
        print("Available files:")
        
        files_list = list(self.local_files.keys())
        for i, filename in enumerate(files_list, 1):
            print(f"  {i}. {filename}")
        
        try:
            choice = input("\nEnter file number (or filename): ").strip()
            
            # Handle numeric choice
            if choice.isdigit():
                choice_num = int(choice)
                if 1 <= choice_num <= len(files_list):
                    filename = files_list[choice_num - 1]
                else:
                    print("❌ Invalid file number")
                    return
            else:
                filename = choice
            
            if filename not in self.local_files:
                print(f"❌ File '{filename}' not found")
                return
            
            filepath = self.local_files[filename]
            if not os.path.exists(filepath):
                print(f"❌ File '{filepath}' does not exist")
                return
            
            # Read file data
            file_size = os.path.getsize(filepath)
            with open(filepath, 'rb') as f:
                file_data = f.read()
            
            print(f"📤 Uploading {filename} ({self._format_size(file_size)}) to cloud...")
            
            # Upload to cloud
            result = self.node.upload_file_to_cloud(filename, file_size, file_data)
            
            if result['status'] == 'OK':
                print(f"✅ Upload successful!")
                print(f"🆔 File ID: {result['file_id']}")
                print(f"📍 Replicated to {result['uploaded_to']} nodes")
            else:
                print(f"❌ Upload failed: {result['error']}")
                
        except KeyboardInterrupt:
            print("\n❌ Upload cancelled")
        except Exception as e:
            print(f"❌ Upload error: {e}")
    
    def cmd_download(self):
        """Download a file from the cloud"""
        if not self.node:
            print("❌ Node not connected to cloud")
            return
        
        print("\n📥 Download File from Cloud")
        filename = input("Enter filename to download: ").strip()
        
        if not filename:
            print("❌ No filename provided")
            return
        
        try:
            print(f"📥 Downloading {filename} from cloud...")
            
            result = self.node.download_file_from_cloud(file_name=filename)
            
            if result['status'] == 'OK':
                file_info = result['file_info']
                file_data = result['file_data']
                
                # Save to local directory
                output_path = os.path.join(self.local_dir, f"downloaded_{filename}")
                with open(output_path, 'wb') as f:
                    f.write(file_data)
                
                print(f"✅ Download successful!")
                print(f"📁 Saved to: {output_path}")
                print(f"📊 Size: {self._format_size(file_info['file_size'])}")
                
                # Add to local files list
                self.local_files[f"downloaded_{filename}"] = output_path
                
            else:
                print(f"❌ Download failed: {result['error']}")
                
        except KeyboardInterrupt:
            print("\n❌ Download cancelled")
        except Exception as e:
            print(f"❌ Download error: {e}")
    
    def cmd_cloud_ls(self):
        """List all files in the cloud"""
        if not self.node:
            print("❌ Node not connected to cloud")
            return
        
        try:
            print("\n☁️  Files in Cloud Storage:")
            print("=" * 70)
            
            result = self.node.list_cloud_files()
            
            if result['status'] == 'OK':
                files = result['files']
                
                if not files:
                    print("📭 No files found in cloud storage")
                    return
                
                print(f"{'File Name':<25} {'Size':<12} {'Copies':<8} {'Uploaded':<20}")
                print("-" * 70)
                
                for file_info in files:
                    upload_time = time.strftime('%Y-%m-%d %H:%M:%S', 
                                               time.localtime(file_info['upload_time']))
                    print(f"{file_info['file_name']:<25} "
                          f"{self._format_size(file_info['file_size']):<12} "
                          f"{file_info['available_copies']:<8} "
                          f"{upload_time:<20}")
                
                print("=" * 70)
            else:
                print(f"❌ Failed to list files: {result['error']}")
                
        except Exception as e:
            print(f"❌ Error listing files: {e}")
    
    def cmd_discover(self):
        """Discover file locations in cloud"""
        if not self.node:
            print("❌ Node not connected to cloud")
            return
        
        print("\n🔍 Discover File Locations")
        filename = input("Enter filename to discover: ").strip()
        
        if not filename:
            print("❌ No filename provided")
            return
        
        try:
            result = self.node.discover_file_locations(filename)
            
            if result['status'] == 'OK':
                locations = result['locations']
                
                if not locations:
                    print(f"📭 File '{filename}' not found in any location")
                    return
                
                print(f"\n📍 Found {len(locations)} locations for '{filename}':")
                print("=" * 60)
                print(f"{'Node ID':<15} {'Health':<8} {'Host:Port':<20} {'Last Seen'}")
                print("-" * 60)
                
                for location in locations:
                    last_seen = time.strftime('%H:%M:%S', 
                                            time.localtime(location['last_seen']))
                    print(f"{location['node_id']:<15} "
                          f"{location['health_score']:.1f}%{'':<3} "
                          f"{location['host']}:{location['port']:<15} "
                          f"{last_seen}")
                
                print("=" * 60)
            else:
                print(f"❌ Discovery failed: {result['error']}")
                
        except Exception as e:
            print(f"❌ Discovery error: {e}")
    
    def cmd_stats(self):
        """Show node statistics"""
        if not self.node:
            print("❌ Node not connected to cloud")
            return
        
        try:
            storage_util = self.node.get_storage_utilization()
            network_util = self.node.get_network_utilization()
            performance = self.node.get_performance_metrics()
            health = self.node.get_node_health_status()
            
            print(f"\n📊 Node Statistics: {self.node_id}")
            print("=" * 50)
            print(f"💾 Storage Used: {self._format_size(storage_util['used_bytes'])} / "
                  f"{self._format_size(storage_util['total_bytes'])} "
                  f"({storage_util['utilization_percent']:.1f}%)")
            print(f"🌐 Network Utilization: {network_util['utilization_percent']:.1f}%")
            print(f"📁 Files Stored: {storage_util['files_stored']}")
            print(f"🔄 Active Transfers: {storage_util['active_transfers']}")
            print(f"📈 Requests Processed: {performance['total_requests_processed']}")
            print(f"📊 Data Transferred: {self._format_size(performance['total_data_transferred_bytes'])}")
            print(f"💚 Health Score: {health['overall_health']:.1f}%")
            print(f"⏰ Uptime: {health['uptime']:.1f} seconds")
            print(f"📂 Local Files: {len(self.local_files)}")
            print("=" * 50)
            
        except Exception as e:
            print(f"❌ Error getting stats: {e}")
    
    def cmd_cloud_stats(self):
        """Show cloud network statistics"""
        print("\n☁️  Cloud Network Statistics")
        print("=" * 50)
        print("📊 This feature requires network controller API access")
        print("💡 Use the network controller terminal to see cloud stats")
        print("=" * 50)
    
    def _format_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
    
    def run_interactive_mode(self):
        """Run the interactive command loop"""
        if not self.start_node():
            return
        
        print(f"\n🎉 Welcome to Cloud Storage Node: {self.node_id}")
        print("💡 Type 'help' to see available commands")
        
        self.show_menu()
        
        while self.running:
            try:
                command = input(f"\n[{self.node_id}]> ").strip().lower()
                
                if command in ['exit', 'quit', 'q']:
                    break
                elif command in ['help', 'h', '?']:
                    self.show_menu()
                elif command == 'ls':
                    self.cmd_ls()
                elif command == 'upload':
                    self.cmd_upload()
                elif command == 'download':
                    self.cmd_download()
                elif command == 'cloud-ls':
                    self.cmd_cloud_ls()
                elif command == 'discover':
                    self.cmd_discover()
                elif command == 'stats':
                    self.cmd_stats()
                elif command == 'cloud-stats':
                    self.cmd_cloud_stats()
                elif command == '':
                    continue
                else:
                    print(f"❌ Unknown command: {command}")
                    print("💡 Type 'help' to see available commands")
                    
            except KeyboardInterrupt:
                print("\n👋 Shutting down...")
                break
            except EOFError:
                print("\n👋 Shutting down...")
                break
            except Exception as e:
                print(f"❌ Error: {e}")
        
        self.shutdown()
    
    def shutdown(self):
        """Shutdown the node"""
        self.running = False
        if self.node:
            print(f"🔌 Disconnecting node {self.node_id} from cloud...")
            print(f"📁 Local files will be removed from cloud file list...")
            self.node.shutdown()
            print("✅ Node shutdown complete")
            print("💡 Files from this node are no longer available in cloud")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Interactive Cloud Storage Node')
    parser.add_argument('--node-id', type=str, required=True, help='Node ID')
    parser.add_argument('--network-host', type=str, default='localhost', help='Cloud controller host')
    parser.add_argument('--network-port', type=int, default=5000, help='Cloud controller port')
    parser.add_argument('--visualization', choices=['console', 'detailed', 'summary'], 
                       default='detailed', help='Visualization mode')
    
    args = parser.parse_args()
    
    # Set visualization mode
    mode_map = {
        'console': VisualizationMode.CONSOLE,
        'detailed': VisualizationMode.DETAILED,
        'summary': VisualizationMode.SUMMARY
    }
    set_visualization_mode(mode_map[args.visualization])
    
    # Create and run interactive node
    node = InteractiveCloudNode(args.node_id, args.network_host, args.network_port)
    node.run_interactive_mode()

if __name__ == '__main__':
    main()
