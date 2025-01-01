# Retro Launcher Agent

Python-based agent for monitoring and controlling the VICE C64 emulator on a Raspberry Pi.

## Setup

1. Clone the repository:
```bash
git clone https://github.com/krystof-io/retro-launcher-agent.git
cd retro-launcher-agent
```

2. Create and activate a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Running

Simply run main.py:
```bash
python main.py
```

## Configuration

Create an optional `.env` file to override default settings:
```env
RETRO_AGENT_HOST=127.0.0.1
RETRO_AGENT_PORT=5000
RETRO_AGENT_DEBUG=true
```

## Updating

To update, just pull the latest changes:
```bash
git pull origin main
pip install -r requirements.txt  # In case dependencies changed
```

## Development Endpoints

Test the agent using these endpoints:

```bash
# Get current status
curl http://localhost:5000/status

# Switch to simulated mode
curl -X POST http://localhost:5000/dev/mode \
     -H "Content-Type: application/json" \
     -d '{"mode": "SIMULATED"}'

# Set emulator state
curl -X POST http://localhost:5000/dev/state \
     -H "Content-Type: application/json" \
     -d '{"running": true, "demo": "test.prg"}'
```