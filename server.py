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
        logger.info(f"TunnelServer initialized on port {port}")

    def handle_client(self, client_socket, client_addr):
        """Handle individual client connections"""
        try:
            self.active_connections += 1
            logger.debug(f"New connection from {client_addr} (Active connections: {self.active_connections})")
            
            # Create connection to target port (25565 for Minecraft)
            target_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target_socket.settimeout(60)
            logger.debug(f"Connecting to target port 25565")
            target_socket.connect(('127.0.0.1', 25565))
            logger.debug("Connected to target port")
            
            # Set TCP_NODELAY to disable Nagle's algorithm
            client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            target_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            
            # Create bidirectional pipe
            def forward(source, destination, direction):
                try:
                    while True:
                        data = source.recv(4096)
                        if not data:
                            break
                        logger.debug(f"Forwarding {len(data)} bytes {direction}")
                        destination.send(data)
                except Exception as e:
                    logger.error(f"Error in {direction} forwarding: {str(e)}")
                finally:
                    try:
                        source.close()
                        destination.close()
                    except:
                        pass
            
            # Start bidirectional forwarding
            threading.Thread(target=forward, args=(client_socket, target_socket, "client->target")).start()
            threading.Thread(target=forward, args=(target_socket, client_socket, "target->client")).start()
            
        except Exception as e:
            logger.error(f"Error handling client: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
        finally:
            self.active_connections -= 1
            logger.debug(f"Client connection closed. Active connections: {self.active_connections}")

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
                    threading.Thread(target=self.handle_client, args=(client_socket, client_addr)).start()
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
