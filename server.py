#!/usr/bin/env python3
import os
import sys
import time
import logging
import socket
import click
import threading
import traceback
from dotenv import load_dotenv
import queue

# Configure logging with more detail
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('port_forwarder.log')
    ]
)
logger = logging.getLogger(__name__)

class TunnelServer:
    def __init__(self, port):
        self.port = port
        self.server_socket = None
        self.connection_state = "initialized"
        self.active_connections = 0
        self.tunnel_clients = {}  # Maps port -> connection
        logger.info(f"TunnelServer initialized on port {port}")

    def handle_minecraft_client(self, client_socket, client_addr, target_port):
        """Handle connections from Minecraft clients to the tunnel"""
        try:
            self.active_connections += 1
            logger.debug(f"New Minecraft client connection from {client_addr} (Active connections: {self.active_connections})")
            
            # Check if we have a tunnel client for this port
            if target_port not in self.tunnel_clients:
                logger.error(f"No active tunnel for port {target_port}")
                client_socket.close()
                return
                
            # Get the tunnel client connection
            tunnel_socket, _ = self.tunnel_clients[target_port]
            
            # Set TCP_NODELAY to disable Nagle's algorithm
            client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            
            # Signal to the tunnel client that we have a new connection
            # Send a special byte to indicate a new connection
            tunnel_socket.send(b'\x01')
            
            # Create bidirectional pipe
            client_to_tunnel_queue = queue.Queue()
            tunnel_to_client_queue = queue.Queue()
            
            def forward_client_to_tunnel():
                try:
                    while True:
                        data = client_socket.recv(4096)
                        if not data:
                            break
                        logger.debug(f"Forwarding {len(data)} bytes from Minecraft client to tunnel")
                        tunnel_socket.send(data)
                except Exception as e:
                    logger.error(f"Error in client->tunnel forwarding: {str(e)}")
                finally:
                    try:
                        client_socket.close()
                    except:
                        pass
            
            def forward_tunnel_to_client():
                try:
                    while True:
                        data = tunnel_socket.recv(4096)
                        if not data:
                            break
                        logger.debug(f"Forwarding {len(data)} bytes from tunnel to Minecraft client")
                        client_socket.send(data)
                except Exception as e:
                    logger.error(f"Error in tunnel->client forwarding: {str(e)}")
                finally:
                    try:
                        tunnel_socket.close()
                    except:
                        pass
            
            # Start bidirectional forwarding
            threading.Thread(target=forward_client_to_tunnel).start()
            threading.Thread(target=forward_tunnel_to_client).start()
            
        except Exception as e:
            logger.error(f"Error handling Minecraft client: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
        finally:
            self.active_connections -= 1
            logger.debug(f"Minecraft client connection closed. Active connections: {self.active_connections}")

    def handle_tunnel_client(self, client_socket, client_addr):
        """Handle connections from the tunnel client"""
        try:
            self.active_connections += 1
            logger.debug(f"New tunnel connection from {client_addr} (Active connections: {self.active_connections})")
            
            # Wait for the client to send the target port (4 bytes)
            port_bytes = client_socket.recv(4)
            logger.debug(f"Received port bytes: {port_bytes.hex()}")
            logger.debug(f"Individual bytes: {[b for b in port_bytes]}")
            if len(port_bytes) != 4:
                logger.error(f"Invalid port data received: {len(port_bytes)} bytes")
                return
                
            # Convert bytes to integer (little-endian)
            target_port = int.from_bytes(port_bytes, byteorder='little')
            logger.debug(f"Converted port bytes to integer: {target_port}")
            
            # Try big-endian conversion as well to check if that's the issue
            big_endian_port = int.from_bytes(port_bytes, byteorder='big')
            logger.debug(f"Big-endian interpretation: {big_endian_port}")
            
            # Validate port number
            if not (0 <= target_port <= 65535):
                logger.error(f"Invalid port number received: {target_port}")
                return
                
            logger.debug(f"Tunnel client requested connection to port {target_port}")
            
            # Store the tunnel client connection
            self.tunnel_clients[target_port] = (client_socket, client_addr)
            logger.info(f"Registered tunnel for port {target_port}")
            
            # Set TCP_NODELAY to disable Nagle's algorithm
            client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            
            # Keep the connection alive until closed
            while True:
                try:
                    # Just check if the connection is still alive
                    client_socket.settimeout(30)
                    data = client_socket.recv(1)
                    if not data:
                        break
                except socket.timeout:
                    # Send a heartbeat
                    try:
                        client_socket.send(b'\x00')
                    except:
                        break
                except Exception as e:
                    logger.error(f"Error in tunnel client connection: {str(e)}")
                    break
            
            # Remove the tunnel client when disconnected
            logger.info(f"Tunnel client for port {target_port} disconnected")
            if target_port in self.tunnel_clients:
                del self.tunnel_clients[target_port]
            
        except Exception as e:
            logger.error(f"Error handling tunnel client: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
        finally:
            self.active_connections -= 1
            logger.debug(f"Tunnel client connection closed. Active connections: {self.active_connections}")

    def start(self):
        """Start the tunnel server"""
        try:
            self.connection_state = "starting"
            
            # Create server socket
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', self.port))
            self.server_socket.listen(5)
            
            self.connection_state = "running"
            logger.info(f"Tunnel server running on port {self.port}")
            
            # Accept connections
            while self.connection_state == "running":
                try:
                    client_socket, client_addr = self.server_socket.accept()
                    
                    # Determine if this is a tunnel client or a Minecraft client
                    # Peek at the first byte without removing it from the buffer
                    client_socket.settimeout(5)
                    try:
                        first_byte = client_socket.recv(1, socket.MSG_PEEK)
                        
                        # If the connection is closed or the first byte is not received
                        if not first_byte:
                            logger.error("Connection was closed immediately")
                            client_socket.close()
                            continue
                            
                        # Check for data connection identifier byte (0x02)
                        if first_byte == b'\x02':
                            # This is a data connection from the tunnel client
                            # Read the identifier byte to remove it from the buffer
                            client_socket.recv(1)
                            
                            # Find the appropriate tunnel client
                            # For now, we'll just use the first one if available
                            port_to_use = None
                            if self.tunnel_clients:
                                port_to_use = list(self.tunnel_clients.keys())[0]
                                
                            if port_to_use:
                                logger.debug(f"New data connection from {client_addr}, handling for port {port_to_use}")
                                # The tunnel client has connected a data socket
                                # This would normally be paired with a Minecraft client
                                # But there's no immediate action needed here, as the client will wait for data
                                # We can close this or keep it open for debugging
                                client_socket.close()
                            else:
                                logger.error(f"No tunnel available for data connection from {client_addr}")
                                client_socket.close()
                                
                        # Minecraft protocol has a specific format for the first byte
                        # Tunnel clients will send 4 bytes for the port
                        # For now, we'll use a simple heuristic: check if it's a valid ASCII character
                        elif first_byte[0] >= 32 and first_byte[0] <= 126:
                            # Likely a Minecraft client - find the appropriate tunnel
                            port_to_use = None
                            # Use the first registered tunnel
                            if self.tunnel_clients:
                                port_to_use = list(self.tunnel_clients.keys())[0]
                                
                            if port_to_use:
                                logger.debug(f"New Minecraft client connection from {client_addr}, routing to port {port_to_use}")
                                threading.Thread(target=self.handle_minecraft_client, 
                                                args=(client_socket, client_addr, port_to_use)).start()
                            else:
                                logger.error(f"No tunnel available for Minecraft client from {client_addr}")
                                client_socket.close()
                        else:
                            # Likely a tunnel client
                            logger.debug(f"New tunnel client connection from {client_addr}")
                            threading.Thread(target=self.handle_tunnel_client, 
                                            args=(client_socket, client_addr)).start()
                    except socket.timeout:
                        logger.error(f"Timeout while determining client type from {client_addr}")
                        client_socket.close()
                    except Exception as e:
                        logger.error(f"Error determining client type: {str(e)}")
                        client_socket.close()
                        
                except Exception as e:
                    if self.connection_state == "running":
                        logger.error(f"Error accepting connection: {str(e)}")
                        logger.error(f"Traceback: {traceback.format_exc()}")
            
            return True
        except Exception as e:
            self.connection_state = "failed"
            logger.error(f"Failed to start server: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    def stop(self):
        """Stop the tunnel server"""
        self.connection_state = "stopping"
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        self.connection_state = "stopped"
        logger.info("Tunnel server stopped")

@click.command()
@click.option('--port', default=25566, help='Port to listen on')
def main(port):
    """Run the tunnel server on AWS"""
    # Load environment variables
    load_dotenv()

    # Create and configure server
    server = TunnelServer(port=port)

    try:
        # Start the server
        if not server.start():
            logger.error("Failed to start server")
            sys.exit(1)

        logger.info(f"Server is running on port {port}")
        logger.info("Press Ctrl+C to stop the server")

        # Keep the server running and monitor connection state
        while True:
            time.sleep(1)
            if server.connection_state != "running":
                logger.error(f"Connection state changed to: {server.connection_state}")
                break
            if server.active_connections > 0:
                logger.debug(f"Active connections: {server.active_connections}")

    except KeyboardInterrupt:
        logger.info("Shutting down server...")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
    finally:
        server.stop()

if __name__ == '__main__':
    main()
