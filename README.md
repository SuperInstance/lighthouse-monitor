# lighthouse-monitor

**Automated monitoring and alerting for the Cocapn fleet.** Watches services, detects anomalies, and signals alerts across the fleet — like a lighthouse beacon for distributed systems.

## Architecture

```
lighthouse-monitor/
├── src/              ← Monitoring logic
├── config/           ← Alert rules and escalation policies
└── README.md         ← You are here
```

## Features

- **Service Health Monitoring**: Periodic checks on fleet services (keeper, agent-api, holodeck, seed-mcp)
- **Anomaly Detection**: Configurable thresholds for response time, error rates, and availability
- **Beacon System**: Fleet-wide alert propagation — when one lighthouse sees trouble, all lighthouses know
- **Escalation Policies**: Tiered alerts (warn → critical → emergency) with configurable routing
- **Integration**: Works with brothers-keeper for automated remediation

## Fleet Role

lighthouse-monitor pairs with:
- **brothers-keeper** — Automated remediation (restart, scale, heal)
- **lighthouse-keeper** — Agent learning and challenge suite
- **fleet-mechanic** — Diagnostics and repair scripts

Together they form the fleet's immune system: monitor (lighthouse-monitor) → diagnose (fleet-mechanic) → heal (brothers-keeper).

## License

MIT
