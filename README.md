# Minecraft Port Forwarding Solution

A Python-based solution for exposing a locally hosted Minecraft server to the internet when behind a NAT/firewall, without requiring port forwarding on your home router.

## Overview

This application creates a TCP tunnel between your local Minecraft server and an AWS EC2 instance, allowing players to connect to your Minecraft server through the public IP address of your EC2 instance.

Key features:
- Bypasses the need for port forwarding on your home router
- Simple client-server architecture
- Minimizes latency by using direct TCP forwarding
- Maintains persistent connections with heartbeats
- Handles multiple simultaneous player connections

## Requirements

- Python 3.6 or higher
- AWS EC2 instance with a public IP
- Running Minecraft server on your local machine

## Installation

### On Your Local Machine

1. Clone the repository:
```
git clone https://github.com/yourusername/minecraft-port-forwarding.git
cd minecraft-port-forwarding
```

2. Install dependencies:
```
pip install -r requirements.txt
```

### On Your AWS EC2 Instance

1. Clone the repository:
```
git clone https://github.com/yourusername/minecraft-port-forwarding.git
cd minecraft-port-forwarding
```

2. Install dependencies:
```
pip install -r requirements.txt
```

## Usage

### On Your AWS EC2 Instance

1. Run the server:
```
python server.py --port 25566
```

This starts the server component that listens for incoming connections on port 25566.

### On Your Local Machine

1. Start your Minecraft server (typically on port 25565).

2. Run the client, replacing `your-aws-ip` with your EC2 instance's public IP:
```
python client.py --aws-ip your-aws-ip --aws-port 25566 --minecraft-port 25565
```

### Connecting to the Server

Players can connect to your Minecraft server using:
```
your-aws-ip:25566
```

## How It Works

1. The client (on your local machine) connects to the server component on your AWS EC2 instance.
2. When a Minecraft player connects to your AWS EC2 instance, the server notifies the client.
3. The client creates a new connection to the AWS server for data transfer.
4. Data is forwarded bidirectionally between the player and your local Minecraft server.

## Security Considerations

- This application does not include authentication mechanisms - anyone can connect to your Minecraft server if they know the AWS IP address
- The traffic is not encrypted - consider using this in conjunction with a VPN if security is a concern
- Ensure your EC2 security group only allows necessary ports

## Troubleshooting

Common issues:

1. **Connection timeouts**: Ensure your Minecraft server is running and accessible on localhost.
2. **EC2 connectivity issues**: Check that port 25566 is allowed in your EC2 instance's security group.
3. **"Connection refused"**: Make sure the server component is running on your EC2 instance.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgements

This solution was built as an alternative to ngrok or SSH port forwarding for Minecraft servers.