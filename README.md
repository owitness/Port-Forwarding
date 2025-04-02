# Minecraft Server Port Forwarding

A Python-based command-line tool that sets up a reverse SSH tunnel between your local Minecraft server and an AWS EC2 instance, enabling external access without using ngrok.

## Prerequisites

- Python 3.x installed on your local machine
- An AWS EC2 instance with a public IP
- SSH key pair for AWS instance authentication
- Minecraft server running locally

## AWS EC2 Setup

1. Ensure your EC2 instance has the following security group rules:
   - Allow incoming traffic on port 25565 (or your chosen Minecraft port)
   - Allow SSH (port 22) for establishing the reverse tunnel

2. Make sure your EC2 instance's SSH server is configured to permit TCP port forwarding.

## Installation

1. Clone this repository:
```bash
git clone <repository-url>
cd <repository-directory>
```

2. Install the required dependencies:
```bash
pip install -r requirements.txt
```

## Usage

Run the script with the required parameters:

```bash
python server.py --aws-ip YOUR_AWS_IP --ssh-key-path /path/to/your/key.pem
```

Optional parameters:
- `--aws-username`: AWS instance SSH username (default: ec2-user)
- `--local-port`: Local Minecraft server port (default: 25565)
- `--remote-port`: Remote port on AWS instance (default: 25565)

Example with all parameters:
```bash
python server.py \
    --aws-ip 54.123.45.67 \
    --aws-username ec2-user \
    --ssh-key-path ~/.ssh/my-key.pem \
    --local-port 25565 \
    --remote-port 25565
```

## How It Works

1. The script establishes an SSH connection to your AWS EC2 instance
2. It sets up a reverse tunnel that forwards traffic from the AWS instance's public port to your local Minecraft server
3. External players can now connect to your Minecraft server using the AWS instance's public IP and port

## Security Considerations

- Keep your SSH private key secure and never share it
- Regularly update your AWS security group rules
- Monitor your AWS instance for any suspicious activity
- Consider implementing additional security measures like firewall rules

## Troubleshooting

1. Connection Issues:
   - Verify your AWS instance is running
   - Check security group rules
   - Ensure your SSH key has the correct permissions (chmod 600)

2. Port Forwarding Issues:
   - Verify the ports are not in use
   - Check if your local Minecraft server is running
   - Ensure the AWS instance's SSH server allows port forwarding