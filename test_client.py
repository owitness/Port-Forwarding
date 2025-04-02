#!/usr/bin/env python3
import socket
import sys

def main():
    aws_ip = "3.145.64.97"
    aws_port = 25566
    minecraft_port = 25565

    # Connect to AWS server
    print(f"Connecting to {aws_ip}:{aws_port}...")
    aws_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    aws_socket.settimeout(60)
    aws_socket.connect((aws_ip, aws_port))
    print("Connected to AWS server")
    
    # Send target port as 4 bytes (little-endian)
    port_bytes = minecraft_port.to_bytes(4, byteorder='little')
    print(f"Sending minecraft port {minecraft_port} as bytes: {port_bytes.hex()}")
    print(f"Individual bytes: {[b for b in port_bytes]}")
    bytes_sent = aws_socket.send(port_bytes)
    print(f"Sent {bytes_sent} bytes")
    
    # Wait for a little bit
    print("Waiting for server response...")
    try:
        data = aws_socket.recv(1024)
        print(f"Received data: {data}")
    except socket.timeout:
        print("Timeout waiting for server response")
    except Exception as e:
        print(f"Error: {str(e)}")
    
    # Close connection
    aws_socket.close()
    print("Connection closed")

if __name__ == "__main__":
    main() 