import argparse
import time
from storage_virtual_node import StorageVirtualNode
from storage_virtual_network import StorageVirtualNetwork

def run_node(node_id, cpu, memory, storage, bandwidth, network_host, network_port):
    try:
        print(f"Starting node {node_id}...")
        node = StorageVirtualNode(
            node_id=node_id,
            cpu_capacity=cpu,
            memory_capacity=memory,
            storage_capacity=storage,
            bandwidth=bandwidth,
            network_host=network_host,
            network_port=network_port
        )
        
        print(f"Node {node_id} running. Press Ctrl+C to stop.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        node.shutdown()
    except Exception as e:
        print(f"Node startup failed: {e}")

def run_network(host, port):
    try:
        print("🌐 Starting Cloud Storage Controller...")
        print(f"📡 Architecture: Node ↔ Cloud ↔ Node")
        print(f"🔗 Listening on {host}:{port}")
        network = StorageVirtualNetwork(host=host, port=port)

        print(f"\n✅ Cloud Storage Controller is running!")
        print(f"📊 Waiting for nodes to connect...")
        print(f"🛑 Press Ctrl+C to stop the cloud controller")
        print("=" * 60)

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\n🛑 Shutting down Cloud Storage Controller...")
        network.shutdown()
        print("✅ Cloud Controller shutdown complete")
    except Exception as e:
        print(f"❌ Cloud Controller startup failed: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Distributed Cloud Storage System')
    parser.add_argument('--node', action='store_true', help='Run as a storage node (deprecated - use interactive_node.py)')
    parser.add_argument('--network', action='store_true', help='Run as cloud storage controller')
    parser.add_argument('--node-id', type=str, help='Node ID (deprecated)')
    parser.add_argument('--cpu', type=int, default=4, help='CPU capacity (deprecated)')
    parser.add_argument('--memory', type=int, default=16, help='Memory capacity (GB) (deprecated)')
    parser.add_argument('--storage', type=int, default=500, help='Storage capacity (GB) (deprecated)')
    parser.add_argument('--bandwidth', type=int, default=1000, help='Bandwidth (Mbps) (deprecated)')
    parser.add_argument('--network-host', type=str, default='localhost', help='Network controller host (deprecated)')
    parser.add_argument('--network-port', type=int, default=5000, help='Network controller port')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='Host to bind to (for cloud controller)')

    args = parser.parse_args()

    if args.network:
        run_network(args.host, args.network_port)
    elif args.node and args.node_id:
        print("⚠️  WARNING: Direct node mode is deprecated!")
        print("💡 Please use: python interactive_node.py --node-id <your_node_id>")
        print("🎯 This provides a better interactive experience with menus and commands")
        print()
        response = input("Continue with deprecated mode? (y/N): ").strip().lower()
        if response == 'y':
            run_node(
                args.node_id,
                args.cpu,
                args.memory,
                args.storage,
                args.bandwidth,
                args.network_host,
                args.network_port
            )
        else:
            print("👍 Use interactive_node.py instead!")
    else:
        print("🌐 Distributed Cloud Storage System")
        print("=" * 40)
        print("📋 Usage:")
        print("  🔧 Start Cloud Controller:")
        print("     python main.py --network")
        print()
        print("  🖥️  Start Interactive Node:")
        print("     python interactive_node.py --node-id node1")
        print()
        print("  🌐 gRPC Version (Recommended):")
        print("     python grpc_cloud_controller.py")
        print("     python grpc_interactive_node.py --node-id node1")
        print()
        print("🔄 Features:")
        print("  • Automatic file synchronization")
        print("  • Files removed when nodes go offline")
        print("  • Real-time cloud file list updates")
        print("  • Node ↔ Cloud ↔ Node architecture")
        print()
        print("💡 Start the cloud controller first, then connect nodes!")