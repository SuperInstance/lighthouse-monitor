# lighthouse-monitor

**Automated monitoring and alerting for the Cocapn fleet.** Watches services, detects anomalies, and signals alerts across the fleet — like a lighthouse beacon for distributed systems.

## Brand Line
> The fleet's immune system — monitor, diagnose, and signal alerts across every agent and service.

## Installation
```bash
pip install cocapn-lighthouse-monitor
# or
git clone https://github.com/SuperInstance/lighthouse-monitor
cd lighthouse-monitor
pip install -e .
```

## Quick Start
```bash
python lighthouse-keeper.py --config config/ rules verify  # Validate your config
python lighthouse-keeper.py --config config/ beacon status  # Check fleet health
python lighthouse-keeper.py --config config/ beacon alert --level critical --target brothers-keeper  # Send alert
```

## Features
- **Service Health Monitoring**: Periodic checks on fleet services (keeper, agent-api, holodeck, seed-mcp)
- **Anomaly Detection**: Configurable thresholds for response time, error rates, and availability
- **Beacon System**: Fleet-wide alert propagation — when one lighthouse sees trouble, all lighthouses know
- **Escalation Policies**: Tiered alerts (warn → critical → emergency) with configurable routing
- **Integration**: Works with brothers-keeper for automated remediation

## Fleet Context
Part of the Cocapn fleet. Related repos:
- [plato-server](https://github.com/SuperInstance/plato-server) — Knowledge system that powers fleet-wide learning
- [open-agents](https://github.com/SuperInstance/open-agents) — Core agent runtime with fleet communication tools
- [vessel-equipment-agent-skills](https://github.com/SuperInstance/vessel-equipment-agent-skills) — Four-layer agent architecture reference implementation

---
🦐 Cocapn fleet — lighthouse keeper architecture
