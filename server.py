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

class TCPTunnel:
    def __init__(self, aws_ip, local_port, remote_port):
        self.aws_ip = aws_ip
        self.local_port = local_port
        self.remote_port = remote_port
        self.server_socket = None
        self.connection_state = "initialized"
        self.active_connections = 0
        logger.info(f"TCPTunnel initialized with local_port={local_port}, remote_port={remote_port}")

    def test_local_connection(self):
        """Test if we can connect to the local server"""
        try:
            logger.debug(f"Testing local connection to 127.0.0.1:{self.local_port}")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            logger.debug("Created test socket")
            
            result = sock.connect_ex(('127.0.0.1', self.local_port))
            logger.debug(f"Connection test result: {result}")
            
            sock.close()
            
            if result == 0:
                logger.info(f"Successfully connected to local server on port {self.local_port}")
                return True
            else:
                logger.error(f"Failed to connect to local server. Error code: {result}")
                return False
        except Exception as e:
            logger.error(f"Error testing local connection: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    def handle_client(self, client_socket, client_addr):
        """Handle individual client connections"""
        try:
            self.active_connections += 1
            logger.debug(f"New connection from {client_addr} (Active connections: {self.active_connections})")
            
            # Create connection to local server
            local_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            local_socket.settimeout(60)
            logger.debug(f"Connecting to local server at 127.0.0.1:{self.local_port}")
            local_socket.connect(('127.0.0.1', self.local_port))
            logger.debug("Connected to local server")
            
            # Set TCP_NODELAY to disable Nagle's algorithm
            client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            local_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            
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
            threading.Thread(target=forward, args=(client_socket, local_socket, "client->local")).start()
            threading.Thread(target=forward, args=(local_socket, client_socket, "local->client")).start()
            
        except Exception as e:
            logger.error(f"Error handling client: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
        finally:
            self.active_connections -= 1
            logger.debug(f"Client connection closed. Active connections: {self.active_connections}")

    def start(self):
        """Start the TCP tunnel server"""
        try:
            self.connection_state = "starting"
            
            # Test local connection first
            if not self.test_local_connection():
                logger.error("Cannot proceed - local server is not accessible")
                self.connection_state = "local_connection_failed"
                return False
            
            # Create server socket
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', self.remote_port))
            self.server_socket.listen(5)
            
            self.connection_state = "running"
            logger.info(f"TCP tunnel server running on {self.aws_ip}:{self.remote_port}")
            logger.info(f"Forwarding to localhost:{self.local_port}")
            
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
            logger.error(f"Failed to start tunnel: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    def stop(self):
        """Stop the TCP tunnel server"""
        self.connection_state = "stopping"
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        self.connection_state = "stopped"
        logger.info("TCP tunnel server stopped")

@click.command()
@click.option('--aws-ip', required=True, help='AWS EC2 instance public IP')
@click.option('--local-port', default=25565, help='Local server port')
@click.option('--remote-port', default=25565, help='Remote port on AWS instance')
def main(aws_ip, local_port, remote_port):
    """Set up a TCP tunnel for any local server"""
    # Load environment variables
    load_dotenv()

    # Create and configure tunnel
    tunnel = TCPTunnel(
        aws_ip=aws_ip,
        local_port=local_port,
        remote_port=remote_port
    )

    try:
        # Start the tunnel
        if not tunnel.start():
            logger.error("Failed to start tunnel")
            sys.exit(1)

        logger.info(f"Tunnel is active. Local server is accessible at {aws_ip}:{remote_port}")
        logger.info("Press Ctrl+C to stop the tunnel")

        # Keep the tunnel running and monitor connection state
        while True:
            time.sleep(1)
            if tunnel.connection_state != "running":
                logger.error(f"Connection state changed to: {tunnel.connection_state}")
                break
            if tunnel.active_connections > 0:
                logger.debug(f"Active connections: {tunnel.active_connections}")

    except KeyboardInterrupt:
        logger.info("Shutting down tunnel...")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
    finally:
        tunnel.stop()

if __name__ == '__main__':
    main()
