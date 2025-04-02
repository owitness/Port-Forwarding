#!/usr/bin/env python3
import os
import sys
import time
import logging
import socket
import click
import threading
import traceback
import signal
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

class TunnelClient:
    def __init__(self, aws_ip, aws_port, local_port, minecraft_port):
        self.aws_ip = aws_ip
        self.aws_port = aws_port
        self.local_port = local_port  # Port we listen on locally
        self.minecraft_port = minecraft_port  # Port where Minecraft server is running
        self.server_socket = None
        self.connection_state = "initialized"
        self.active_connections = 0
        self.forward_threads = []
        self._stop_event = threading.Event()
        logger.info(f"TunnelClient initialized: {aws_ip}:{aws_port} -> localhost:{minecraft_port} (via {local_port})")

    def handle_local_connection(self, local_socket, local_addr):
        """Handle connections from local server"""
        try:
            self.active_connections += 1
            logger.debug(f"New local connection from {local_addr} (Active connections: {self.active_connections})")
            
            # Connect to AWS server
            aws_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            aws_socket.settimeout(60)
            logger.debug(f"Connecting to AWS server at {self.aws_ip}:{self.aws_port}")
            aws_socket.connect((self.aws_ip, self.aws_port))
            logger.debug("Connected to AWS server")
            
            # Send target port as 4 bytes (little-endian)
            port_bytes = self.minecraft_port.to_bytes(4, byteorder='little')
            aws_socket.send(port_bytes)
            
            # Set TCP_NODELAY to disable Nagle's algorithm
            local_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            aws_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            
            # Create bidirectional pipe
            def forward(source, destination, direction):
                try:
                    while not self._stop_event.is_set():
                        try:
                            data = source.recv(4096)
                            if not data:
                                break
                            logger.debug(f"Forwarding {len(data)} bytes {direction}")
                            destination.send(data)
                        except socket.timeout:
                            continue
                except Exception as e:
                    logger.error(f"Error in {direction} forwarding: {str(e)}")
                finally:
                    try:
                        source.close()
                        destination.close()
                    except:
                        pass
            
            # Start bidirectional forwarding
            thread1 = threading.Thread(target=forward, args=(local_socket, aws_socket, "local->aws"))
            thread2 = threading.Thread(target=forward, args=(aws_socket, local_socket, "aws->local"))
            thread1.daemon = True
            thread2.daemon = True
            thread1.start()
            thread2.start()
            self.forward_threads.extend([thread1, thread2])
            
        except Exception as e:
            logger.error(f"Error handling local connection: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
        finally:
            self.active_connections -= 1
            logger.debug(f"Local connection closed. Active connections: {self.active_connections}")

    def start(self):
        """Start the tunnel client"""
        try:
            self.connection_state = "starting"
            
            # Create server socket to listen for local connections
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('127.0.0.1', self.local_port))
            self.server_socket.listen(5)
            
            self.connection_state = "running"
            logger.info(f"Tunnel client running. Listening on localhost:{self.local_port}")
            logger.info(f"Forwarding to {self.aws_ip}:{self.aws_port} -> localhost:{self.minecraft_port}")
            
            # Accept connections
            while self.connection_state == "running" and not self._stop_event.is_set():
                try:
                    self.server_socket.settimeout(1)  # Add timeout to allow checking stop_event
                    local_socket, local_addr = self.server_socket.accept()
                    threading.Thread(target=self.handle_local_connection, args=(local_socket, local_addr)).start()
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.connection_state == "running" and not self._stop_event.is_set():
                        logger.error(f"Error accepting connection: {str(e)}")
                        logger.error(f"Traceback: {traceback.format_exc()}")
            
            return True
        except Exception as e:
            self.connection_state = "failed"
            logger.error(f"Failed to start client: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    def stop(self):
        """Stop the tunnel client"""
        logger.info("Stopping tunnel client...")
        self._stop_event.set()
        self.connection_state = "stopping"
        
        # Close server socket
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        
        # Wait for all forward threads to finish
        for thread in self.forward_threads:
            try:
                thread.join(timeout=1)
            except:
                pass
        
        self.connection_state = "stopped"
        logger.info("Tunnel client stopped")

def signal_handler(signum, frame):
    """Handle Ctrl+C"""
    logger.info("Received shutdown signal")
    if client:
        client.stop()
    sys.exit(0)

@click.command()
@click.option('--aws-ip', required=True, help='AWS EC2 instance public IP')
@click.option('--aws-port', default=25566, help='Port on AWS instance')
@click.option('--local-port', default=25567, help='Local port to listen on')
@click.option('--minecraft-port', default=25565, help='Port where Minecraft server is running')
def main(aws_ip, aws_port, local_port, minecraft_port):
    """Run the tunnel client on your local machine"""
    global client
    
    # Load environment variables
    load_dotenv()

    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Create and configure client
    client = TunnelClient(
        aws_ip=aws_ip,
        aws_port=aws_port,
        local_port=local_port,
        minecraft_port=minecraft_port
    )

    try:
        # Start the client
        if not client.start():
            logger.error("Failed to start client")
            sys.exit(1)

        logger.info(f"Client is running. Forwarding localhost:{local_port} to {aws_ip}:{aws_port} -> localhost:{minecraft_port}")
        logger.info("Press Ctrl+C to stop the client")

        # Keep the client running and monitor connection state
        while not client._stop_event.is_set():
            time.sleep(1)
            if client.connection_state != "running":
                logger.error(f"Connection state changed to: {client.connection_state}")
                break
            if client.active_connections > 0:
                logger.debug(f"Active connections: {client.active_connections}")

    except KeyboardInterrupt:
        logger.info("Shutting down client...")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
    finally:
        client.stop()

if __name__ == '__main__':
    main() 