# Deployment Guide for DigitalOcean

This guide will help you deploy the blockchain monitor on a DigitalOcean droplet.

## Prerequisites

- A DigitalOcean account
- Basic knowledge of Linux and SSH

## Step 1: Create a Droplet

1. Log in to your DigitalOcean account
2. Click "Create" and select "Droplets"
3. Choose an image (Ubuntu 20.04 LTS recommended)
4. Select a plan (Basic plan with 1GB RAM should be sufficient)
5. Choose a datacenter region close to you
6. Add your SSH key or set a root password
7. Click "Create Droplet"

## Step 2: Connect to Your Droplet

```bash
ssh root@your_droplet_ip
```

## Step 3: Install Dependencies

```bash
# Update package lists
apt update

# Install required packages
apt install -y python3-pip python3-venv git

# Create a user for the application
adduser blockchain
usermod -aG sudo blockchain

# Switch to the new user
su - blockchain
```

## Step 4: Clone the Repository

```bash
# Clone the repository
git clone https://github.com/yourusername/blockchain-monitor.git
cd blockchain-monitor

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Step 5: Configure the Application

```bash
# Copy and edit the configuration file
cp config/blockchain_config.example.json config/blockchain_config.json
nano config/blockchain_config.json
```

Edit the configuration file with your API keys, Telegram bot token, and other settings.

## Step 6: Set Up Systemd Service

Create a systemd service file to ensure the monitor runs automatically and restarts if it crashes:

```bash
sudo nano /etc/systemd/system/blockchain-monitor.service
```

Add the following content:

```
[Unit]
Description=Blockchain Monitor Service
After=network.target

[Service]
User=blockchain
Group=blockchain
WorkingDirectory=/home/blockchain/blockchain-monitor
ExecStart=/home/blockchain/blockchain-monitor/venv/bin/python -m src.monitor
Restart=always
RestartSec=10
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=blockchain-monitor

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable blockchain-monitor
sudo systemctl start blockchain-monitor
```

## Step 7: Monitor the Service

Check the status of the service:

```bash
sudo systemctl status blockchain-monitor
```

View the logs:

```bash
# Using journalctl
sudo journalctl -u blockchain-monitor -f

# Or check the application logs
tail -f /home/blockchain/blockchain-monitor/logs/blockchain_monitor.log
```

## Step 8: Set Up Log Rotation (Optional)

The application already includes log rotation, but you can also set up system-level log rotation:

```bash
sudo nano /etc/logrotate.d/blockchain-monitor
```

Add the following content:

```
/home/blockchain/blockchain-monitor/logs/*.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    create 0640 blockchain blockchain
}
```

## Step 9: Set Up Cron Job for Log Cleanup

```bash
# Edit crontab
crontab -e
```

Add the following line to run the cleanup script daily at 1 AM:

```
0 1 * * * /home/blockchain/blockchain-monitor/scripts/cleanup_logs.sh >> /home/blockchain/blockchain-monitor/logs/cleanup.log 2>&1
```

## Updating the Application

To update the application:

```bash
# Switch to the blockchain user
su - blockchain

# Navigate to the application directory
cd blockchain-monitor

# Pull the latest changes
git pull

# Activate the virtual environment
source venv/bin/activate

# Install any new dependencies
pip install -r requirements.txt

# Restart the service
sudo systemctl restart blockchain-monitor
```
