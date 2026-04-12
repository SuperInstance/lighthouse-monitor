#!/usr/bin/env python3
"""
Lighthouse Keeper — Fleet Monitor

Watches fleet repos for activity, reports what agents are building,
detects stalled work, and logs everything for the managing director.

Each lighthouse monitors a region of the fleet (a set of repos).
The keeper reports: who's working, what they built, what's stalled,
and what needs attention.

Usage:
  python3 lighthouse-keeper.py [--config keeper.json] [--watch] [--report]
"""

import json
import os
import sys
import time
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict


@dataclass
class RepoActivity:
    """Activity snapshot for a single repo."""
    name: str
    owner: str
    last_commit_date: Optional[str] = None
    last_commit_msg: Optional[str] = None
    last_commit_author: Optional[str] = None
    open_issues: int = 0
    open_prs: int = 0
    branches: int = 0
    stalled_hours: float = 0.0
    health: str = "unknown"  # active, slow, stalled, dead, new
    notes: List[str] = field(default_factory=list)


@dataclass 
class AgentActivity:
    """Activity for an agent across all their repos."""
    agent_name: str
    repos: List[str] = field(default_factory=list)
    last_active: Optional[str] = None
    total_commits_24h: int = 0
    building: List[str] = field(default_factory=list)  # what they're working on
    stalled: List[str] = field(default_factory=list)    # stalled repos
    health: str = "unknown"


@dataclass
class FleetReport:
    """Full fleet status report."""
    timestamp: str
    lighthouse: str
    agents: Dict[str, AgentActivity] = field(default_factory=dict)
    alerts: List[str] = field(default_factory=list)
    summary: str = ""


class LighthouseKeeper:
    """Monitors fleet repos and generates reports."""
    
    # Fleet configuration — which repos belong to which agent
    FLEET_REGISTRY = {
        "Oracle1": {
            "profile": "SuperInstance",
            "repos": [
                "oracle1-vessel", "flux-runtime", "flux-runtime-c", "fleet-mechanic",
                "fleet-org", "fleet-workshop", "iron-to-iron", "captains-log",
                "mesosynchronous", "brothers-keeper", "tender", "ability-transfer",
                "codespace-edge-rd", "cudaclaw", "zeroclaw", "hybridclaw",
                "flux-conformance", "SuperInstance", "greenhorn-onboarding",
                "greenhorn-runtime", "flux-collab", "beachcomb"
            ],
            "role": "Managing Director",
            "expected_activity": "always-on"
        },
        "JetsonClaw1": {
            "profile": "Lucineer",
            "repos": [
                "capitaine", "lighthouse-keeper", "brothers-keeper", "tender",
                "flux-isa-unified", "cuda-trust", "cuda-confidence", "cuda-biology",
                "cuda-energy", "cuda-memory-fabric", "cuda-emotion",
                "cuda-neurotransmitter", "cuda-genepool", "cuda-ghost-tiles",
                "flux-tools", "flux-apps", "fleet-benchmarks"
            ],
            "role": "Hardware Specialist (Vessel)",
            "expected_activity": "always-on"
        },
        "Super Z": {
            "profile": "SuperInstance",
            "repos": ["fleet-mechanic", "flux-runtime"],
            "role": "Fleet Auditor",
            "expected_activity": "30min-cycle"
        },
        "Babel": {
            "profile": "SuperInstance", 
            "repos": ["flux-runtime", "flux-multilingual"],
            "role": "Multilingual Scout",
            "expected_activity": "30min-cycle"
        },
        "Mechanic": {
            "profile": "SuperInstance",
            "repos": ["fleet-mechanic"],
            "role": "Fleet Maintenance",
            "expected_activity": "on-demand"
        }
    }
    
    STALL_THRESHOLDS = {
        "always-on": {"slow": 12, "stalled": 48, "dead": 168},      # hours
        "30min-cycle": {"slow": 2, "stalled": 6, "dead": 24},
        "on-demand": {"slow": 72, "stalled": 336, "dead": 720},     # 3d, 14d, 30d
    }
    
    def __init__(self, token: str, lighthouse_name: str = "Oracle1-Lighthouse"):
        self.token = token
        self.lighthouse_name = lighthouse_name
        self.activities: Dict[str, RepoActivity] = {}
    
    def _api(self, url: str) -> Optional[dict]:
        """Call GitHub API."""
        try:
            result = subprocess.run(
                ["curl", "-s", "-H", f"Authorization: token {self.token}", url],
                capture_output=True, text=True, timeout=15
            )
            return json.loads(result.stdout)
        except Exception:
            return None
    
    def check_repo(self, owner: str, repo: str) -> RepoActivity:
        """Check a single repo's activity."""
        activity = RepoActivity(name=repo, owner=owner)
        
        # Get latest commit
        commits = self._api(f"https://api.github.com/repos/{owner}/{repo}/commits?per_page=1")
        if isinstance(commits, list) and commits:
            c = commits[0]
            activity.last_commit_date = c["commit"]["author"]["date"]
            activity.last_commit_msg = c["commit"]["message"][:100]
            activity.last_commit_author = c["commit"]["author"]["name"]
            
            # Calculate stall time
            commit_time = datetime.fromisoformat(activity.last_commit_date.replace("Z", "+00:00"))
            hours_ago = (datetime.now(timezone.utc) - commit_time).total_seconds() / 3600
            activity.stalled_hours = round(hours_ago, 1)
        
        # Get issue/PR counts
        issues = self._api(f"https://api.github.com/repos/{owner}/{repo}/issues?state=open&per_page=1")
        if isinstance(issues, list):
            activity.open_issues = len(issues)
        
        prs = self._api(f"https://api.github.com/repos/{owner}/{repo}/pulls?state=open&per_page=1")
        if isinstance(prs, list):
            activity.open_prs = len(prs)
        
        return activity
    
    def assess_health(self, activity: RepoActivity, expected: str) -> str:
        """Assess repo health based on stall thresholds."""
        thresholds = self.STALL_THRESHOLDS.get(expected, self.STALL_THRESHOLDS["on-demand"])
        hours = activity.stalled_hours
        
        if hours < thresholds["slow"]:
            return "active"
        elif hours < thresholds["stalled"]:
            return "slow"
        elif hours < thresholds["dead"]:
            return "stalled"
        else:
            return "dead"
    
    def scan_fleet(self) -> FleetReport:
        """Scan the entire fleet and generate a report."""
        report = FleetReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            lighthouse=self.lighthouse_name
        )
        
        for agent_name, config in self.FLEET_REGISTRY.items():
            agent = AgentActivity(
                agent_name=agent_name,
                repos=config["repos"]
            )
            
            for repo in config["repos"]:
                activity = self.check_repo(config["profile"], repo)
                health = self.assess_health(activity, config["expected_activity"])
                activity.health = health
                self.activities[f"{config['profile']}/{repo}"] = activity
                
                if health == "active":
                    agent.building.append(f"{repo}: {activity.last_commit_msg}")
                    agent.total_commits_24h += 1 if activity.stalled_hours < 24 else 0
                elif health in ("stalled", "dead"):
                    agent.stalled.append(repo)
                
                if agent.last_active is None or (activity.last_commit_date and 
                    activity.last_commit_date > (agent.last_active or "")):
                    agent.last_active = activity.last_commit_date
            
            agent.health = "active" if agent.building else ("stalled" if agent.stalled else "idle")
            report.agents[agent_name] = agent
            
            # Generate alerts
            if agent.stalled:
                expected = config["expected_activity"]
                if expected == "always-on" and agent.health != "active":
                    report.alerts.append(
                        f"🔴 {agent_name} ({config['role']}) — always-on agent has stalled repos: {', '.join(agent.stalled)}"
                    )
                elif expected == "30min-cycle" and not agent.building:
                    report.alerts.append(
                        f"🟡 {agent_name} ({config['role']}) — no recent activity, may need re-awakening"
                    )
        
        # Summary
        active = sum(1 for a in report.agents.values() if a.health == "active")
        total = len(report.agents)
        building = []
        for a in report.agents.values():
            building.extend(a.building[:2])
        
        report.summary = (
            f"Fleet: {active}/{total} agents active. "
            f"Building: {'; '.join(building[:6])}. "
            f"Alerts: {len(report.alerts)}"
        )
        
        return report
    
    def format_report(self, report: FleetReport) -> str:
        """Format report as markdown."""
        lines = [
            f"# 🔦 Lighthouse Report — {self.lighthouse_name}",
            f"**{report.timestamp}**\n",
            f"## Summary\n{report.summary}\n",
            "## Agent Status\n"
        ]
        
        for name, agent in report.agents.items():
            emoji = {"active": "🟢", "stalled": "🔴", "idle": "🟡", "unknown": "⚪"}.get(agent.health, "⚪")
            config = self.FLEET_REGISTRY[name]
            lines.append(f"### {emoji} {name} — {config['role']}")
            lines.append(f"- Last active: {agent.last_active or 'never'}")
            lines.append(f"- Repos monitored: {len(agent.repos)}")
            if agent.building:
                lines.append(f"- **Building:**")
                for b in agent.building[:5]:
                    lines.append(f"  - {b}")
            if agent.stalled:
                lines.append(f"- **Stalled:** {', '.join(agent.stalled)}")
            lines.append("")
        
        if report.alerts:
            lines.append("## Alerts\n")
            for alert in report.alerts:
                lines.append(f"- {alert}")
            lines.append("")
        
        lines.append("---")
        lines.append(f"*Report by {self.lighthouse_name} lighthouse keeper*")
        return "\n".join(lines)


def main():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        # Try .bashrc
        import re
        with open(os.path.expanduser("~/.bashrc")) as f:
            for line in f:
                m = re.match(r'export GITHUB_TOKEN=(.+)', line.strip())
                if m:
                    token = m.group(1).strip().strip("'\"")
                    break
    
    if not token:
        print("No GITHUB_TOKEN found", file=sys.stderr)
        sys.exit(1)
    
    keeper = LighthouseKeeper(token)
    report = keeper.scan_fleet()
    
    # Output
    if "--report" in sys.argv or len(sys.argv) == 1:
        print(keeper.format_report(report))
    
    if "--json" in sys.argv:
        # Save as JSON for programmatic use
        out = {
            "timestamp": report.timestamp,
            "lighthouse": report.lighthouse,
            "summary": report.summary,
            "agents": {name: asdict(agent) for name, agent in report.agents.items()},
            "alerts": report.alerts
        }
        print(json.dumps(out, indent=2))
    
    if "--watch" in sys.argv:
        # Continuous mode — scan every 15 min
        while True:
            print(f"\n{'='*60}")
            report = keeper.scan_fleet()
            print(keeper.format_report(report))
            print(f"\nNext scan in 15 minutes...")
            time.sleep(900)


if __name__ == "__main__":
    main()
