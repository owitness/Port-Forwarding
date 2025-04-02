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
    def __init__(self, aws_ip, aws_port, minecraft_port):
        self.aws_ip = aws_ip
        self.aws_port = aws_port
        self.minecraft_port = minecraft_port  # Port where Minecraft server is running
        self.aws_socket = None
        self.connection_state = "initialized"
        self.active_connections = 0
        self.forward_threads = []
        self._stop_event = threading.Event()
        logger.info(f"TunnelClient initialized: {aws_ip}:{aws_port} -> localhost:{minecraft_port}")

    def handle_minecraft_connection(self, aws_data_socket):
        """Handle a new Minecraft connection from the AWS server"""
        try:
            self.active_connections += 1
            logger.debug(f"New Minecraft connection request (Active connections: {self.active_connections})")
            
            # Connect to local Minecraft server
            minecraft_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            minecraft_socket.settimeout(10)
            logger.debug(f"Connecting to Minecraft server at localhost:{self.minecraft_port}")
            try:
                minecraft_socket.connect(('127.0.0.1', self.minecraft_port))
                logger.debug("Connected to Minecraft server")
            except Exception as e:
                logger.error(f"Failed to connect to Minecraft server: {str(e)}")
                aws_data_socket.close()
                return
            
            # Set TCP_NODELAY to disable Nagle's algorithm
            minecraft_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            aws_data_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            
            # Create bidirectional pipe
            def forward(source, destination, direction, is_minecraft_to_aws=False):
                source_name = "Minecraft" if is_minecraft_to_aws else "AWS"
                dest_name = "AWS" if is_minecraft_to_aws else "Minecraft"
                try:
                    source.settimeout(300)  # 5 minute timeout
                    while not self._stop_event.is_set():
                        try:
                            data = source.recv(4096)
                            if not data:
                                logger.debug(f"{source_name} connection closed")
                                break
                            logger.debug(f"Forwarding {len(data)} bytes {direction}")
                            destination.send(data)
                        except socket.timeout:
                            # Try sending a heartbeat if it's from AWS to Minecraft
                            if not is_minecraft_to_aws:
                                try:
                                    destination.send(b'\x00')  # Heartbeat
                                    logger.debug(f"Sent heartbeat to {dest_name}")
                                except:
                                    break
                            continue
                        except Exception as e:
                            if not self._stop_event.is_set():
                                logger.error(f"Error in {direction} forwarding: {str(e)}")
                            break
                except Exception as e:
                    if not self._stop_event.is_set():
                        logger.error(f"Error in {direction} forwarding: {str(e)}")
                finally:
                    try:
                        if not source.fileno() == -1:
                            source.close()
                    except:
                        pass
                    try:
                        if not destination.fileno() == -1:
                            destination.close()
                    except:
                        pass
                    logger.debug(f"Forwarding thread {direction} stopped")
            
            # Start bidirectional forwarding
            thread1 = threading.Thread(target=forward, args=(minecraft_socket, aws_data_socket, "minecraft->aws", True))
            thread2 = threading.Thread(target=forward, args=(aws_data_socket, minecraft_socket, "aws->minecraft", False))
            thread1.daemon = True
            thread2.daemon = True
            thread1.start()
            thread2.start()
            self.forward_threads.extend([thread1, thread2])
            
            # Wait for either thread to finish
            while thread1.is_alive() and thread2.is_alive() and not self._stop_event.is_set():
                time.sleep(1)
            
            logger.debug("One of the forwarding threads has stopped")
            
        except Exception as e:
            logger.error(f"Error handling Minecraft connection: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
        finally:
            # Close both sockets if they're still open
            try:
                if 'minecraft_socket' in locals() and minecraft_socket.fileno() != -1:
                    minecraft_socket.close()
            except:
                pass
            try:
                if 'aws_data_socket' in locals() and aws_data_socket.fileno() != -1:
                    aws_data_socket.close()
            except:
                pass
            self.active_connections -= 1
            logger.debug(f"Minecraft connection closed. Active connections: {self.active_connections}")

    def maintain_tunnel(self):
        """Maintain the tunnel connection to the AWS server"""
        try:
            # Connect to AWS server
            self.aws_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.aws_socket.settimeout(60)
            logger.debug(f"Connecting to AWS server at {self.aws_ip}:{self.aws_port}")
            self.aws_socket.connect((self.aws_ip, self.aws_port))
            logger.debug("Connected to AWS server")
            
            # Send target port as 4 bytes (little-endian)
            port_bytes = self.minecraft_port.to_bytes(4, byteorder='little')
            logger.debug(f"Sending minecraft port {self.minecraft_port} as bytes: {port_bytes.hex()}")
            logger.debug(f"Individual bytes: {[b for b in port_bytes]}")
            bytes_sent = self.aws_socket.send(port_bytes)
            logger.debug(f"Sent {bytes_sent} bytes")
            
            # Set TCP_NODELAY to disable Nagle's algorithm
            self.aws_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            
            # Wait for new connection signals
            while not self._stop_event.is_set():
                try:
                    # Use a smaller buffer size for control messages
                    # The control byte is followed by the connection ID
                    self.aws_socket.settimeout(60)
                    data = self.aws_socket.recv(1)
                    if not data:
                        logger.error("AWS server closed the connection")
                        break
                    
                    # Check if it's a new connection signal
                    if data == b'\x01':
                        # Read the connection ID (up to 36 bytes)
                        try:
                            connection_id_bytes = self.aws_socket.recv(36)
                            connection_id = connection_id_bytes.decode('utf-8')
                            logger.debug(f"Received new connection signal from AWS for ID: {connection_id}")
                            
                            # Create a new socket for this connection's data
                            aws_data_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            aws_data_socket.connect((self.aws_ip, self.aws_port))
                            
                            # Send a special byte to identify this as a data socket, followed by the connection ID
                            aws_data_socket.send(b'\x02' + connection_id_bytes)
                            
                            # Start a thread to handle this connection
                            threading.Thread(target=self.handle_minecraft_connection, args=(aws_data_socket,)).start()
                        except Exception as e:
                            logger.error(f"Error reading connection ID: {str(e)}")
                            
                    # Ignore heartbeat signals
                    elif data == b'\x00':
                        logger.debug("Received heartbeat from AWS")
                    # Log unknown signals but don't treat them as errors
                    else:
                        hex_value = data.hex()
                        if len(hex_value) > 0 and all(c in '0123456789abcdef' for c in hex_value):
                            logger.debug(f"Received control byte from AWS: {hex_value}")
                        else:
                            logger.warning(f"Received unknown signal from AWS: {hex_value}")
                        
                except socket.timeout:
                    # Send heartbeat
                    try:
                        self.aws_socket.send(b'\x00')
                        logger.debug("Sent heartbeat to AWS")
                    except:
                        break
                    continue
                except Exception as e:
                    if not self._stop_event.is_set():
                        logger.error(f"Error maintaining tunnel: {str(e)}")
                        logger.error(f"Traceback: {traceback.format_exc()}")
                    break
            
            logger.info("Tunnel maintenance thread stopping")
            
        except Exception as e:
            logger.error(f"Error in tunnel maintenance: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            self.connection_state = "error"

    def start(self):
        """Start the tunnel client"""
        try:
            self.connection_state = "starting"
            
            # Start the tunnel maintenance thread
            threading.Thread(target=self.maintain_tunnel).start()
            
            self.connection_state = "running"
            logger.info(f"Tunnel client running. Connected to {self.aws_ip}:{self.aws_port}")
            logger.info(f"Forwarding connections to localhost:{self.minecraft_port}")
            
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
        
        # Close AWS socket
        if self.aws_socket:
            try:
                self.aws_socket.close()
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
@click.option('--minecraft-port', default=25565, help='Port where Minecraft server is running')
def main(aws_ip, aws_port, minecraft_port):
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
        minecraft_port=minecraft_port
    )

    try:
        # Start the client
        if not client.start():
            logger.error("Failed to start client")
            sys.exit(1)

        logger.info(f"Client is running. Tunneling {aws_ip}:{aws_port} -> localhost:{minecraft_port}")
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