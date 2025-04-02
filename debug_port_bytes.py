#!/usr/bin/env python3
import socket
import struct

def main():
    port = 25565
    
    print("==== Python's to_bytes/from_bytes ====")
    # Using to_bytes/from_bytes
    le_bytes = port.to_bytes(4, byteorder='little')
    be_bytes = port.to_bytes(4, byteorder='big')
    
    print(f"Port: {port}")
    print(f"Little-endian bytes: {le_bytes.hex()}")
    print(f"Big-endian bytes: {be_bytes.hex()}")
    
    # Convert back to integer
    le_port = int.from_bytes(le_bytes, byteorder='little')
    be_port = int.from_bytes(be_bytes, byteorder='big')
    wrong_le_port = int.from_bytes(le_bytes, byteorder='big')
    wrong_be_port = int.from_bytes(be_bytes, byteorder='little')
    
    print(f"Little-endian bytes -> little-endian int: {le_port}")
    print(f"Big-endian bytes -> big-endian int: {be_port}")
    print(f"Little-endian bytes -> big-endian int: {wrong_le_port}")
    print(f"Big-endian bytes -> little-endian int: {wrong_be_port}")
    
    print("\n==== struct module ====")
    # Using struct module
    le_packed = struct.pack("<I", port)  # < for little-endian, I for unsigned int
    be_packed = struct.pack(">I", port)  # > for big-endian, I for unsigned int
    
    print(f"Little-endian packed: {le_packed.hex()}")
    print(f"Big-endian packed: {be_packed.hex()}")
    
    # Unpack
    le_unpacked = struct.unpack("<I", le_packed)[0]
    be_unpacked = struct.unpack(">I", be_packed)[0]
    wrong_le_unpacked = struct.unpack(">I", le_packed)[0]
    wrong_be_unpacked = struct.unpack("<I", be_packed)[0]
    
    print(f"Little-endian packed -> little-endian unpack: {le_unpacked}")
    print(f"Big-endian packed -> big-endian unpack: {be_unpacked}")
    print(f"Little-endian packed -> big-endian unpack: {wrong_le_unpacked}")
    print(f"Big-endian packed -> little-endian unpack: {wrong_be_unpacked}")
    
    print("\n==== Testing with known problem value ====")
    problem_value = 109183030
    problem_bytes = problem_value.to_bytes(4, byteorder='little')
    print(f"Problem value: {problem_value}")
    print(f"Problem value as little-endian bytes: {problem_bytes.hex()}")
    print(f"Individual bytes: {[b for b in problem_bytes]}")
    
    # Try different interpretations
    le_problem = int.from_bytes(problem_bytes, byteorder='little')
    be_problem = int.from_bytes(problem_bytes, byteorder='big')
    print(f"Problem bytes -> little-endian int: {le_problem}")
    print(f"Problem bytes -> big-endian int: {be_problem}")
    
    # Check if our port 25565 can be interpreted as 109183030
    port_bytes = port.to_bytes(4, byteorder='little')
    print(f"\nOur port bytes: {port_bytes.hex()}")
    if le_problem == 109183030:
        print(f"Converting back problem bytes to little-endian gives the problem value.")
    if be_problem == port:
        print(f"Converting problem bytes to big-endian gives our port!")

if __name__ == "__main__":
    main() 