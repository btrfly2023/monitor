# Blockchain Monitor

A monitoring system for blockchain data with Telegram notifications and customizable alerts.

## Features

- Monitor multiple blockchain networks (Ethereum, Polygon, BSC, etc.)
- Track token balances and other on-chain data
- Customizable alerts based on thresholds, ratios, and percent changes
- Telegram notifications with sound alerts
- Automatic log rotation to prevent disk space issues
- Secure configuration with environment variables or secure files
- Improved error handling and proxy support
- Query isolation to prevent one failing query from affecting others

## Installation

### Standard Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/blockchain-monitor.git
cd blockchain-monitor

# Install dependencies
pip install -r requirements.txt

# Set up secure configuration
./scripts/secure_config.sh
# Follow the prompts to set up your API keys and tokens

# Configure your settings
cp config/blockchain_config.example.json config/blockchain_config.json
# Edit the config file with your alert settings
```

### Docker Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/blockchain-monitor.git
cd blockchain-monitor

# Set up secure configuration
./scripts/secure_config.sh
# Follow the prompts to set up your API keys and tokens

# Configure your settings
cp config/blockchain_config.example.json config/blockchain_config.json
# Edit the config file with your alert settings

# Start with Docker Compose
docker-compose up -d
```

## Configuration

### Main Configuration

Edit `config/blockchain_config.json` to set up your monitoring targets and alert conditions.

### Secure Configuration

You have two options for storing sensitive information:

1. **Environment Variables**: Create a `.env` file in the project root
2. **Secure JSON**: Create a `config/secure/keys.json` file

Use the `./scripts/secure_config.sh` script to help set up these files.

## Usage

### Starting the Monitor

```bash
# Using the start script
./scripts/start.sh

# Or manually
python -m src.monitor
```

### Stopping the Monitor

```bash
# Using the stop script
./scripts/stop.sh
```

### Restarting the Monitor

```bash
# Using the restart script
./scripts/restart.sh
```

### Managing Debug Level

```bash
# Toggle between DEBUG and INFO logging levels
./scripts/toggle_debug.sh
```

### Managing Proxy Settings

```bash
# Configure proxy settings
./scripts/configure_proxy.sh
```

### Checking API Health

```bash
# Check the health of your API connections
./scripts/check_api_health.sh
```

## Logs

Logs are stored in the `logs/` directory and automatically rotated to prevent excessive disk usage.

## Deployment on DigitalOcean

See the [deployment guide](docs/deployment.md) for instructions on setting up the monitor on a DigitalOcean droplet.
