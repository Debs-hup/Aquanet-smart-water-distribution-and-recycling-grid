import time
import threading
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum, auto

class VisualizationMode(Enum):
    CONSOLE = auto()
    DETAILED = auto()
    SUMMARY = auto()

@dataclass
class PacketLayer:
    name: str
    header_size: int
    payload_size: int
    headers: Dict[str, str]
    processing_time: float

class EncapsulationVisualizer:
    def __init__(self, mode: VisualizationMode = VisualizationMode.DETAILED):
        self.mode = mode
        self.active_transfers = {}
        self.completed_transfers = {}
        self.lock = threading.Lock()
    
    def start_transfer_visualization(self, transfer_id: str, operation: str, file_name: str, file_size: int):
        """Start visualizing a file transfer operation"""
        with self.lock:
            self.active_transfers[transfer_id] = {
                'operation': operation,
                'file_name': file_name,
                'file_size': file_size,
                'start_time': time.time(),
                'layers': [],
                'current_size': file_size
            }
            
        if self.mode != VisualizationMode.SUMMARY:
            print(f"\n{'='*60}")
            print(f"🌐 {operation} OPERATION STARTED")
            print(f"{'='*60}")
            print(f"📁 File: {file_name}")
            print(f"📊 Size: {self._format_size(file_size)}")
            print(f"🆔 Transfer ID: {transfer_id}")
            print(f"⏰ Started at: {time.strftime('%H:%M:%S')}")
            print(f"{'='*60}\n")
    
    def add_encapsulation_layer(self, transfer_id: str, layer_name: str, header_size: int, headers: Dict[str, str]):
        """Add an encapsulation layer to the visualization"""
        with self.lock:
            if transfer_id not in self.active_transfers:
                return
            
            transfer = self.active_transfers[transfer_id]
            current_size = transfer['current_size']
            new_size = current_size + header_size
            
            layer = PacketLayer(
                name=layer_name,
                header_size=header_size,
                payload_size=current_size,
                headers=headers,
                processing_time=time.time() - transfer['start_time']
            )
            
            transfer['layers'].append(layer)
            transfer['current_size'] = new_size
            
            if self.mode == VisualizationMode.DETAILED:
                self._print_layer_details(layer, len(transfer['layers']))
    
    def add_decapsulation_layer(self, transfer_id: str, layer_name: str, header_size: int, headers: Dict[str, str]):
        """Add a decapsulation layer to the visualization"""
        with self.lock:
            if transfer_id not in self.active_transfers:
                return
            
            transfer = self.active_transfers[transfer_id]
            current_size = transfer['current_size']
            new_size = current_size - header_size
            
            layer = PacketLayer(
                name=f"Remove {layer_name}",
                header_size=-header_size,
                payload_size=new_size,
                headers=headers,
                processing_time=time.time() - transfer['start_time']
            )
            
            transfer['layers'].append(layer)
            transfer['current_size'] = new_size
            
            if self.mode == VisualizationMode.DETAILED:
                self._print_layer_details(layer, len(transfer['layers']))
    
    def complete_transfer_visualization(self, transfer_id: str, success: bool = True):
        """Complete the transfer visualization"""
        with self.lock:
            if transfer_id not in self.active_transfers:
                return
            
            transfer = self.active_transfers[transfer_id]
            transfer['end_time'] = time.time()
            transfer['success'] = success
            transfer['duration'] = transfer['end_time'] - transfer['start_time']
            
            self.completed_transfers[transfer_id] = transfer
            del self.active_transfers[transfer_id]
            
            if self.mode != VisualizationMode.SUMMARY:
                self._print_transfer_summary(transfer)
    
    def _print_layer_details(self, layer: PacketLayer, layer_number: int):
        """Print detailed information about a layer"""
        direction = "📤" if layer.header_size > 0 else "📥"
        action = "Adding" if layer.header_size > 0 else "Removing"
        
        print(f"{direction} Layer {layer_number}: {action} {layer.name}")
        print(f"   ⏱️  Processing Time: {layer.processing_time:.3f}s")
        print(f"   📏 Header Size: {abs(layer.header_size)} bytes")
        print(f"   📦 Payload Size: {self._format_size(layer.payload_size)}")
        
        if layer.headers:
            print(f"   🏷️  Headers:")
            for key, value in layer.headers.items():
                print(f"      • {key}: {value}")
        
        # Visual representation
        if layer.header_size > 0:
            self._print_packet_structure(layer)
        
        print(f"   {'─' * 50}")
    
    def _print_packet_structure(self, layer: PacketLayer):
        """Print a visual representation of the packet structure"""
        total_size = layer.payload_size + abs(layer.header_size)
        header_ratio = abs(layer.header_size) / total_size if total_size > 0 else 0
        payload_ratio = layer.payload_size / total_size if total_size > 0 else 0
        
        # Create visual bar (40 characters wide)
        bar_width = 40
        header_chars = int(header_ratio * bar_width)
        payload_chars = bar_width - header_chars
        
        header_bar = "█" * header_chars
        payload_bar = "░" * payload_chars
        
        print(f"   📊 Packet Structure:")
        print(f"      ┌{'─' * bar_width}┐")
        print(f"      │{header_bar}{payload_bar}│")
        print(f"      └{'─' * bar_width}┘")
        print(f"      Header: {abs(layer.header_size)}B  Payload: {layer.payload_size}B")
    
    def _print_transfer_summary(self, transfer: Dict):
        """Print a summary of the completed transfer"""
        status = "✅ SUCCESS" if transfer['success'] else "❌ FAILED"
        
        print(f"\n{'='*60}")
        print(f"🏁 {transfer['operation']} OPERATION COMPLETED - {status}")
        print(f"{'='*60}")
        print(f"📁 File: {transfer['file_name']}")
        print(f"📊 Original Size: {self._format_size(transfer['file_size'])}")
        print(f"📊 Final Size: {self._format_size(transfer['current_size'])}")
        print(f"⏱️  Total Duration: {transfer['duration']:.3f}s")
        print(f"🔄 Layers Processed: {len(transfer['layers'])}")
        
        if transfer['layers']:
            overhead = transfer['current_size'] - transfer['file_size']
            overhead_percent = (overhead / transfer['file_size']) * 100 if transfer['file_size'] > 0 else 0
            print(f"📈 Protocol Overhead: {overhead} bytes ({overhead_percent:.1f}%)")
        
        print(f"{'='*60}\n")
    
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
    
    def get_transfer_statistics(self) -> Dict:
        """Get statistics about all transfers"""
        with self.lock:
            total_transfers = len(self.completed_transfers)
            successful_transfers = sum(1 for t in self.completed_transfers.values() if t['success'])
            
            if total_transfers == 0:
                return {
                    'total_transfers': 0,
                    'successful_transfers': 0,
                    'success_rate': 0,
                    'average_duration': 0,
                    'total_data_transferred': 0
                }
            
            total_duration = sum(t['duration'] for t in self.completed_transfers.values())
            total_data = sum(t['file_size'] for t in self.completed_transfers.values())
            
            return {
                'total_transfers': total_transfers,
                'successful_transfers': successful_transfers,
                'success_rate': (successful_transfers / total_transfers) * 100,
                'average_duration': total_duration / total_transfers,
                'total_data_transferred': total_data,
                'active_transfers': len(self.active_transfers)
            }
    
    def print_statistics(self):
        """Print transfer statistics"""
        stats = self.get_transfer_statistics()
        
        print(f"\n{'='*50}")
        print(f"📊 TRANSFER STATISTICS")
        print(f"{'='*50}")
        print(f"📈 Total Transfers: {stats['total_transfers']}")
        print(f"✅ Successful: {stats['successful_transfers']}")
        print(f"📊 Success Rate: {stats['success_rate']:.1f}%")
        print(f"⏱️  Average Duration: {stats['average_duration']:.3f}s")
        print(f"📦 Total Data: {self._format_size(stats['total_data_transferred'])}")
        print(f"🔄 Active Transfers: {stats['active_transfers']}")
        print(f"{'='*50}\n")

# Global visualizer instance
visualizer = EncapsulationVisualizer()

def set_visualization_mode(mode: VisualizationMode):
    """Set the global visualization mode"""
    global visualizer
    visualizer.mode = mode

def get_visualizer() -> EncapsulationVisualizer:
    """Get the global visualizer instance"""
    return visualizer
