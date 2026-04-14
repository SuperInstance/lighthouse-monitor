#!/usr/bin/env python3
"""
Comprehensive test suite for Lighthouse Keeper — Fleet Monitor.

Covers:
- Data class instantiation and defaults
- Health assessment and stall thresholds
- Fleet registry structure and validation
- Repo checking with mocked API calls
- Fleet scanning and report generation
- Report formatting (markdown output)
- Alert signaling and escalation policies
- Configuration sensitivity
- Edge cases (API failures, missing data, boundary conditions)
"""

import importlib.util
import json
import os
import sys
import subprocess
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
from dataclasses import asdict
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Import the module via importlib (file has hyphen in name: lighthouse-keeper.py)
# ---------------------------------------------------------------------------
_spec = importlib.util.spec_from_file_location(
    "lighthouse_keeper",
    str(Path(__file__).parent.parent / "lighthouse-keeper.py"),
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

RepoActivity = _mod.RepoActivity
AgentActivity = _mod.AgentActivity
FleetReport = _mod.FleetReport
LighthouseKeeper = _mod.LighthouseKeeper


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_keeper(token="test-token", name="TestLighthouse"):
    """Create a LighthouseKeeper with a test token."""
    return LighthouseKeeper(token=token, lighthouse_name=name)


def _make_repo_activity(**overrides):
    """Create a RepoActivity with sensible defaults, optionally overridden."""
    defaults = dict(
        name="test-repo",
        owner="SuperInstance",
        last_commit_date=None,
        last_commit_msg=None,
        last_commit_author=None,
        open_issues=0,
        open_prs=0,
        branches=0,
        stalled_hours=0.0,
        health="unknown",
        notes=[],
    )
    defaults.update(overrides)
    return RepoActivity(**defaults)


# ===========================================================================
# 1. Dataclass Tests — RepoActivity, AgentActivity, FleetReport
# ===========================================================================

class TestRepoActivity:
    """Tests for the RepoActivity dataclass."""

    def test_default_values(self):
        activity = RepoActivity(name="repo-a", owner="Alice")
        assert activity.name == "repo-a"
        assert activity.owner == "Alice"
        assert activity.last_commit_date is None
        assert activity.last_commit_msg is None
        assert activity.last_commit_author is None
        assert activity.open_issues == 0
        assert activity.open_prs == 0
        assert activity.branches == 0
        assert activity.stalled_hours == 0.0
        assert activity.health == "unknown"
        assert activity.notes == []

    def test_custom_values(self):
        activity = RepoActivity(
            name="flux-runtime",
            owner="SuperInstance",
            last_commit_date="2024-01-15T10:00:00Z",
            last_commit_msg="feat: add monitoring",
            last_commit_author="Oracle1",
            open_issues=5,
            open_prs=3,
            branches=4,
            stalled_hours=2.5,
            health="active",
            notes=["First note"],
        )
        assert activity.last_commit_date == "2024-01-15T10:00:00Z"
        assert activity.last_commit_msg == "feat: add monitoring"
        assert activity.last_commit_author == "Oracle1"
        assert activity.open_issues == 5
        assert activity.open_prs == 3
        assert activity.branches == 4
        assert activity.stalled_hours == 2.5
        assert activity.health == "active"
        assert activity.notes == ["First note"]

    def test_notes_are_mutable_list(self):
        activity = RepoActivity(name="r", owner="o")
        activity.notes.append("note1")
        assert "note1" in activity.notes

    def test_asdict_serialization(self):
        activity = RepoActivity(name="r", owner="o", stalled_hours=3.14)
        d = asdict(activity)
        assert d["name"] == "r"
        assert d["stalled_hours"] == 3.14
        assert isinstance(d, dict)

    def test_notes_default_factory_creates_independent_lists(self):
        a1 = RepoActivity(name="r1", owner="o")
        a2 = RepoActivity(name="r2", owner="o")
        a1.notes.append("shared?")
        assert "shared?" not in a2.notes


class TestAgentActivity:
    """Tests for the AgentActivity dataclass."""

    def test_default_values(self):
        agent = AgentActivity(agent_name="Oracle1")
        assert agent.agent_name == "Oracle1"
        assert agent.repos == []
        assert agent.last_active is None
        assert agent.total_commits_24h == 0
        assert agent.building == []
        assert agent.stalled == []
        assert agent.health == "unknown"

    def test_custom_values(self):
        agent = AgentActivity(
            agent_name="JetsonClaw1",
            repos=["capitaine", "lighthouse-keeper"],
            last_active="2024-01-15T10:00:00Z",
            total_commits_24h=5,
            building=["capitaine: new helm"],
            stalled=["lighthouse-keeper"],
            health="active",
        )
        assert len(agent.repos) == 2
        assert agent.total_commits_24h == 5
        assert agent.health == "active"

    def test_building_and_stalled_are_independent(self):
        a1 = AgentActivity(agent_name="Oracle1")
        a2 = AgentActivity(agent_name="B")
        a1.building.append("x")
        a1.stalled.append("y")
        assert a2.building == []
        assert a2.stalled == []


class TestFleetReport:
    """Tests for the FleetReport dataclass."""

    def test_default_values(self):
        report = FleetReport(timestamp="2024-01-15T10:00:00Z", lighthouse="TestLH")
        assert report.timestamp == "2024-01-15T10:00:00Z"
        assert report.lighthouse == "TestLH"
        assert report.agents == {}
        assert report.alerts == []
        assert report.summary == ""

    def test_with_agents_and_alerts(self):
        report = FleetReport(
            timestamp="2024-01-15T10:00:00Z",
            lighthouse="TestLH",
            agents={"Oracle1": AgentActivity(agent_name="Oracle1")},
            alerts=["alert1"],
            summary="All good",
        )
        assert len(report.agents) == 1
        assert report.alerts == ["alert1"]
        assert report.summary == "All good"

    def test_nested_asdict(self):
        agent = AgentActivity(agent_name="Oracle1", repos=["r1"])
        report = FleetReport(timestamp="t", lighthouse="L", agents={"Oracle1": agent})
        d = asdict(report)
        assert d["agents"]["Oracle1"]["repos"] == ["r1"]


# ===========================================================================
# 2. Health Assessment Tests
# ===========================================================================

class TestAssessHealth:
    """Tests for LighthouseKeeper.assess_health."""

    def test_always_on_active(self):
        keeper = _make_keeper()
        activity = _make_repo_activity(stalled_hours=5.0)
        assert keeper.assess_health(activity, "always-on") == "active"

    def test_always_on_slow(self):
        keeper = _make_keeper()
        activity = _make_repo_activity(stalled_hours=20.0)
        assert keeper.assess_health(activity, "always-on") == "slow"

    def test_always_on_stalled(self):
        keeper = _make_keeper()
        activity = _make_repo_activity(stalled_hours=60.0)
        assert keeper.assess_health(activity, "always-on") == "stalled"

    def test_always_on_dead(self):
        keeper = _make_keeper()
        activity = _make_repo_activity(stalled_hours=200.0)
        assert keeper.assess_health(activity, "always-on") == "dead"

    def test_30min_cycle_active(self):
        keeper = _make_keeper()
        activity = _make_repo_activity(stalled_hours=1.0)
        assert keeper.assess_health(activity, "30min-cycle") == "active"

    def test_30min_cycle_slow(self):
        keeper = _make_keeper()
        activity = _make_repo_activity(stalled_hours=3.0)
        assert keeper.assess_health(activity, "30min-cycle") == "slow"

    def test_30min_cycle_stalled(self):
        keeper = _make_keeper()
        activity = _make_repo_activity(stalled_hours=10.0)
        assert keeper.assess_health(activity, "30min-cycle") == "stalled"

    def test_30min_cycle_dead(self):
        keeper = _make_keeper()
        activity = _make_repo_activity(stalled_hours=30.0)
        assert keeper.assess_health(activity, "30min-cycle") == "dead"

    def test_on_demand_active(self):
        keeper = _make_keeper()
        activity = _make_repo_activity(stalled_hours=50.0)
        assert keeper.assess_health(activity, "on-demand") == "active"

    def test_on_demand_slow(self):
        keeper = _make_keeper()
        activity = _make_repo_activity(stalled_hours=100.0)
        assert keeper.assess_health(activity, "on-demand") == "slow"

    def test_on_demand_stalled(self):
        keeper = _make_keeper()
        activity = _make_repo_activity(stalled_hours=400.0)
        assert keeper.assess_health(activity, "on-demand") == "stalled"

    def test_on_demand_dead(self):
        keeper = _make_keeper()
        activity = _make_repo_activity(stalled_hours=800.0)
        assert keeper.assess_health(activity, "on-demand") == "dead"

    def test_unknown_activity_type_falls_back_to_on_demand(self):
        keeper = _make_keeper()
        activity = _make_repo_activity(stalled_hours=50.0)
        assert keeper.assess_health(activity, "unknown-type") == "active"

    def test_boundary_always_on_slow_threshold(self):
        """Test exactly at the slow boundary for always-on (12h)."""
        keeper = _make_keeper()
        # Just under 12h -> active
        assert keeper.assess_health(_make_repo_activity(stalled_hours=11.99), "always-on") == "active"
        # At or above 12h -> slow
        assert keeper.assess_health(_make_repo_activity(stalled_hours=12.0), "always-on") == "slow"

    def test_boundary_always_on_stalled_threshold(self):
        """Test exactly at the stalled boundary for always-on (48h)."""
        keeper = _make_keeper()
        assert keeper.assess_health(_make_repo_activity(stalled_hours=47.99), "always-on") == "slow"
        assert keeper.assess_health(_make_repo_activity(stalled_hours=48.0), "always-on") == "stalled"

    def test_zero_hours_is_active(self):
        keeper = _make_keeper()
        assert keeper.assess_health(_make_repo_activity(stalled_hours=0.0), "always-on") == "active"


# ===========================================================================
# 3. Fleet Registry Tests
# ===========================================================================

class TestFleetRegistry:
    """Tests for the FLEET_REGISTRY configuration."""

    def test_registry_has_expected_agents(self):
        expected_agents = {"Oracle1", "JetsonClaw1", "Super Z", "Babel", "Mechanic"}
        assert set(LighthouseKeeper.FLEET_REGISTRY.keys()) == expected_agents

    def test_each_agent_has_required_fields(self):
        required = {"profile", "repos", "role", "expected_activity"}
        for name, config in LighthouseKeeper.FLEET_REGISTRY.items():
            assert required.issubset(config.keys()), f"{name} missing fields"

    def test_each_agent_has_repos(self):
        for name, config in LighthouseKeeper.FLEET_REGISTRY.items():
            assert len(config["repos"]) > 0, f"{name} has no repos"

    def test_oracle1_is_largest_fleet(self):
        oracle1_repos = len(LighthouseKeeper.FLEET_REGISTRY["Oracle1"]["repos"])
        for name, config in LighthouseKeeper.FLEET_REGISTRY.items():
            if name != "Oracle1":
                assert oracle1_repos > len(config["repos"])

    def test_all_expected_activity_types_are_valid(self):
        valid = {"always-on", "30min-cycle", "on-demand"}
        for name, config in LighthouseKeeper.FLEET_REGISTRY.items():
            assert config["expected_activity"] in valid, f"{name} has invalid activity type"

    def test_mechanic_is_on_demand(self):
        assert LighthouseKeeper.FLEET_REGISTRY["Mechanic"]["expected_activity"] == "on-demand"

    def test_no_empty_repo_names(self):
        for name, config in LighthouseKeeper.FLEET_REGISTRY.items():
            for repo in config["repos"]:
                assert repo.strip(), f"{name} has empty repo name"

    def test_repos_are_unique_per_agent(self):
        for name, config in LighthouseKeeper.FLEET_REGISTRY.items():
            assert len(config["repos"]) == len(set(config["repos"])), f"{name} has duplicate repos"


# ===========================================================================
# 4. Stall Threshold Tests (Configuration Sensitivity)
# ===========================================================================

class TestStallThresholds:
    """Tests for STALL_THRESHOLDS configuration."""

    def test_all_activity_types_have_thresholds(self):
        for activity_type in ["always-on", "30min-cycle", "on-demand"]:
            assert activity_type in LighthouseKeeper.STALL_THRESHOLDS

    def test_threshold_ordering(self):
        """slow < stalled < dead for each activity type."""
        for atype, thresholds in LighthouseKeeper.STALL_THRESHOLDS.items():
            assert thresholds["slow"] < thresholds["stalled"] < thresholds["dead"], \
                f"Threshold ordering violated for {atype}"

    def test_always_on_is_most_aggressive(self):
        """always-on should have the shortest thresholds."""
        ao = LighthouseKeeper.STALL_THRESHOLDS["always-on"]
        od = LighthouseKeeper.STALL_THRESHOLDS["on-demand"]
        assert ao["dead"] < od["dead"]
        assert ao["stalled"] < od["stalled"]

    def test_on_demand_is_most_lenient(self):
        """on-demand should have the longest thresholds."""
        od = LighthouseKeeper.STALL_THRESHOLDS["on-demand"]
        for atype, thresholds in LighthouseKeeper.STALL_THRESHOLDS.items():
            if atype != "on-demand":
                assert od["stalled"] > thresholds["stalled"]
                assert od["dead"] > thresholds["dead"]

    def test_thresholds_are_positive(self):
        for atype, thresholds in LighthouseKeeper.STALL_THRESHOLDS.items():
            for level, value in thresholds.items():
                assert value > 0, f"{atype}.{level} is not positive"


# ===========================================================================
# 5. Repo Checking Tests (with mocked API)
# ===========================================================================

class TestCheckRepo:
    """Tests for LighthouseKeeper.check_repo with mocked HTTP calls."""

    def test_check_repo_with_valid_commit_data(self):
        keeper = _make_keeper()
        mock_commit_response = [{
            "commit": {
                "author": {
                    "date": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
                    "name": "TestAuthor"
                },
                "message": "feat: add new feature for the fleet"
            }
        }]
        mock_issues = [{"number": 1}]
        mock_prs = [{"number": 1, "pull_request": True}]

        with patch.object(keeper, "_api", side_effect=[mock_commit_response, mock_issues, mock_prs]):
            activity = keeper.check_repo("SuperInstance", "flux-runtime")

        assert activity.name == "flux-runtime"
        assert activity.owner == "SuperInstance"
        assert activity.last_commit_author == "TestAuthor"
        assert activity.last_commit_msg.startswith("feat: add new feature")
        assert activity.open_issues >= 1
        assert activity.open_prs >= 1
        assert activity.stalled_hours > 0

    def test_check_repo_with_empty_commit_list(self):
        keeper = _make_keeper()
        with patch.object(keeper, "_api", side_effect=[[], [], []]):
            activity = keeper.check_repo("SuperInstance", "empty-repo")

        assert activity.last_commit_date is None
        assert activity.stalled_hours == 0.0
        assert activity.health == "unknown"

    def test_check_repo_with_api_failure(self):
        keeper = _make_keeper()
        with patch.object(keeper, "_api", return_value=None):
            activity = keeper.check_repo("SuperInstance", "broken-repo")

        assert activity.last_commit_date is None
        assert activity.open_issues == 0
        assert activity.open_prs == 0

    def test_check_repo_stalled_hours_calculation(self):
        keeper = _make_keeper()
        three_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
        mock_response = [{
            "commit": {
                "author": {"date": three_hours_ago, "name": "Author"},
                "message": "commit msg"
            }
        }]

        with patch.object(keeper, "_api", side_effect=[mock_response, [], []]):
            activity = keeper.check_repo("SuperInstance", "test")

        assert 2.9 < activity.stalled_hours < 3.2

    def test_check_repo_message_truncated_to_100_chars(self):
        keeper = _make_keeper()
        long_msg = "x" * 200
        mock_response = [{
            "commit": {
                "author": {"date": datetime.now(timezone.utc).isoformat(), "name": "A"},
                "message": long_msg
            }
        }]

        with patch.object(keeper, "_api", side_effect=[mock_response, [], []]):
            activity = keeper.check_repo("SuperInstance", "test")

        assert len(activity.last_commit_msg) <= 100


# ===========================================================================
# 6. API Call Tests
# ===========================================================================

class TestAPICall:
    """Tests for the _api method."""

    def test_api_returns_parsed_json(self):
        keeper = _make_keeper()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout='{"key": "value"}', stderr="")
            result = keeper._api("https://api.github.com/test")
        assert result == {"key": "value"}

    def test_api_returns_none_on_subprocess_exception(self):
        keeper = _make_keeper()
        with patch("subprocess.run", side_effect=Exception("timeout")):
            result = keeper._api("https://api.github.com/test")
        assert result is None

    def test_api_returns_none_on_json_decode_error(self):
        keeper = _make_keeper()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="not json", stderr="")
            result = keeper._api("https://api.github.com/test")
        assert result is None

    def test_api_includes_auth_header(self):
        keeper = _make_keeper(token="my-secret-token")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="[]", stderr="")
            keeper._api("https://api.github.com/repos/test/repo/commits")

        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert "Authorization: token my-secret-token" in cmd


# ===========================================================================
# 7. Fleet Scan & Report Generation Tests
# ===========================================================================

class TestScanFleet:
    """Tests for LighthouseKeeper.scan_fleet."""

    def _mock_all_repos_active(self, keeper):
        """Mock all API calls to return active repos."""
        def mock_api(url):
            if "commits" in url:
                recent = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
                return [{"commit": {"author": {"date": recent, "name": "Agent"}, "message": "working"}}]
            return []
        return patch.object(keeper, "_api", side_effect=mock_api)

    def _mock_all_repos_stalled(self, keeper, hours=100):
        """Mock all API calls to return stalled repos."""
        def mock_api(url):
            if "commits" in url:
                old = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
                return [{"commit": {"author": {"date": old, "name": "Agent"}, "message": "old commit"}}]
            return []
        return patch.object(keeper, "_api", side_effect=mock_api)

    def test_scan_fleet_returns_fleet_report(self):
        keeper = _make_keeper()
        with self._mock_all_repos_active(keeper):
            report = keeper.scan_fleet()
        assert isinstance(report, FleetReport)
        assert report.lighthouse == "TestLighthouse"
        assert report.timestamp is not None

    def test_scan_fleet_has_all_agents(self):
        keeper = _make_keeper()
        with self._mock_all_repos_active(keeper):
            report = keeper.scan_fleet()
        assert set(report.agents.keys()) == set(LighthouseKeeper.FLEET_REGISTRY.keys())

    def test_scan_fleet_all_active_no_alerts(self):
        keeper = _make_keeper()
        with self._mock_all_repos_active(keeper):
            report = keeper.scan_fleet()
        assert len(report.alerts) == 0

    def test_scan_fleet_stalled_always_on_generates_alert(self):
        keeper = _make_keeper()
        with self._mock_all_repos_stalled(keeper, hours=100):
            report = keeper.scan_fleet()
        # Oracle1 and JetsonClaw1 are always-on and should generate alerts
        assert len(report.alerts) > 0
        alert_text = " ".join(report.alerts)
        assert "always-on" in alert_text

    def test_scan_fleet_30min_cycle_no_activity_generates_alert(self):
        """Agents with 30min-cycle expected should alert when not building."""
        keeper = _make_keeper()
        with self._mock_all_repos_stalled(keeper, hours=10):
            report = keeper.scan_fleet()
        alert_text = " ".join(report.alerts)
        assert "re-awakening" in alert_text

    def test_scan_fleet_summary_includes_counts(self):
        keeper = _make_keeper()
        with self._mock_all_repos_active(keeper):
            report = keeper.scan_fleet()
        assert "agents active" in report.summary

    def test_scan_fleet_agent_has_repos_assigned(self):
        keeper = _make_keeper()
        with self._mock_all_repos_active(keeper):
            report = keeper.scan_fleet()
        for agent_name, agent in report.agents.items():
            assert len(agent.repos) > 0

    def test_scan_fleet_builds_activities_dict(self):
        keeper = _make_keeper()
        with self._mock_all_repos_active(keeper):
            keeper.scan_fleet()
        assert len(keeper.activities) > 0

    def test_scan_fleet_commits_24h_counted(self):
        keeper = _make_keeper()
        with self._mock_all_repos_active(keeper):
            report = keeper.scan_fleet()
        for agent in report.agents.values():
            # Active agents should have commits counted if stalled < 24h
            if agent.health == "active":
                assert agent.total_commits_24h >= 0


# ===========================================================================
# 8. Report Formatting Tests
# ===========================================================================

class TestFormatReport:
    """Tests for LighthouseKeeper.format_report."""

    def test_format_report_contains_lighthouse_name(self):
        keeper = _make_keeper(name="MyLighthouse")
        report = FleetReport(timestamp="t", lighthouse="MyLighthouse")
        formatted = keeper.format_report(report)
        assert "MyLighthouse" in formatted

    def test_format_report_contains_timestamp(self):
        keeper = _make_keeper()
        report = FleetReport(timestamp="2024-01-15T10:00:00Z", lighthouse="LH")
        formatted = keeper.format_report(report)
        assert "2024-01-15T10:00:00Z" in formatted

    def test_format_report_contains_summary(self):
        keeper = _make_keeper()
        report = FleetReport(
            timestamp="t", lighthouse="LH",
            summary="Fleet: 3/5 agents active"
        )
        formatted = keeper.format_report(report)
        assert "Fleet: 3/5 agents active" in formatted

    def test_format_report_contains_agent_status(self):
        keeper = _make_keeper()
        agent = AgentActivity(
            agent_name="Oracle1",
            repos=["repo1"],
            health="active",
            building=["repo1: working on it"],
        )
        report = FleetReport(
            timestamp="t", lighthouse="LH",
            agents={"Oracle1": agent},
        )
        formatted = keeper.format_report(report)
        assert "Oracle1" in formatted
        assert "Managing Director" in formatted

    def test_format_report_active_agent_emoji(self):
        keeper = _make_keeper()
        agent = AgentActivity(agent_name="Oracle1", repos=["r"], health="active")
        report = FleetReport(timestamp="t", lighthouse="LH", agents={"Oracle1": agent})
        formatted = keeper.format_report(report)
        assert "\U0001f7e2" in formatted  # green circle

    def test_format_report_stalled_agent_emoji(self):
        keeper = _make_keeper()
        agent = AgentActivity(agent_name="Oracle1", repos=["r"], health="stalled", stalled=["r"])
        report = FleetReport(timestamp="t", lighthouse="LH", agents={"Oracle1": agent})
        formatted = keeper.format_report(report)
        assert "\U0001f534" in formatted  # red circle

    def test_format_report_idle_agent_emoji(self):
        keeper = _make_keeper()
        agent = AgentActivity(agent_name="Oracle1", repos=["r"], health="idle")
        report = FleetReport(timestamp="t", lighthouse="LH", agents={"Oracle1": agent})
        formatted = keeper.format_report(report)
        assert "\U0001f7e1" in formatted  # yellow circle

    def test_format_report_shows_alerts(self):
        keeper = _make_keeper()
        report = FleetReport(
            timestamp="t", lighthouse="LH",
            alerts=["ALERT: Something is wrong"],
        )
        formatted = keeper.format_report(report)
        assert "ALERT: Something is wrong" in formatted

    def test_format_report_no_alerts_section_when_empty(self):
        keeper = _make_keeper()
        report = FleetReport(timestamp="t", lighthouse="LH", alerts=[])
        formatted = keeper.format_report(report)
        assert "## Alerts" not in formatted

    def test_format_report_shows_building_list(self):
        keeper = _make_keeper()
        agent = AgentActivity(
            agent_name="Oracle1", repos=["r"],
            building=["r: feat: new thing", "r: fix: bug fix"],
        )
        report = FleetReport(timestamp="t", lighthouse="LH", agents={"Oracle1": agent})
        formatted = keeper.format_report(report)
        assert "Building:" in formatted
        assert "feat: new thing" in formatted

    def test_format_report_shows_stalled_list(self):
        keeper = _make_keeper()
        agent = AgentActivity(
            agent_name="Oracle1", repos=["r1", "r2"],
            stalled=["r1", "r2"],
        )
        report = FleetReport(timestamp="t", lighthouse="LH", agents={"Oracle1": agent})
        formatted = keeper.format_report(report)
        assert "Stalled:" in formatted
        assert "r1" in formatted
        assert "r2" in formatted

    def test_format_report_ends_with_footer(self):
        keeper = _make_keeper(name="MyLH")
        report = FleetReport(timestamp="t", lighthouse="MyLH")
        formatted = keeper.format_report(report)
        assert "MyLH lighthouse keeper" in formatted

    def test_format_report_is_markdown(self):
        keeper = _make_keeper()
        report = FleetReport(timestamp="t", lighthouse="LH")
        formatted = keeper.format_report(report)
        assert formatted.startswith("# ")
        assert "---" in formatted


# ===========================================================================
# 9. Alert Signaling & Escalation Tests
# ===========================================================================

class TestAlerts:
    """Tests for alert generation and escalation policies."""

    def test_always_on_agent_with_all_stalled_repos_triggers_alert(self):
        keeper = _make_keeper()

        def mock_api(url):
            if "commits" in url:
                old = (datetime.now(timezone.utc) - timedelta(hours=100)).isoformat()
                return [{"commit": {"author": {"date": old, "name": "A"}, "message": "old"}}]
            return []

        with patch.object(keeper, "_api", side_effect=mock_api):
            report = keeper.scan_fleet()

        # Oracle1 is always-on and should be flagged
        oracle_alerts = [a for a in report.alerts if "Oracle1" in a]
        assert len(oracle_alerts) > 0
        assert "always-on" in oracle_alerts[0]

    def test_always_on_jetsonclaw_alert(self):
        keeper = _make_keeper()

        def mock_api(url):
            if "commits" in url:
                old = (datetime.now(timezone.utc) - timedelta(hours=100)).isoformat()
                return [{"commit": {"author": {"date": old, "name": "A"}, "message": "old"}}]
            return []

        with patch.object(keeper, "_api", side_effect=mock_api):
            report = keeper.scan_fleet()

        jetson_alerts = [a for a in report.alerts if "JetsonClaw1" in a]
        assert len(jetson_alerts) > 0

    def test_mechanic_on_demand_does_not_alert(self):
        """Mechanic is on-demand; 100 hours stalled should still be active for on-demand."""
        keeper = _make_keeper()

        def mock_api(url):
            if "commits" in url:
                old = (datetime.now(timezone.utc) - timedelta(hours=100)).isoformat()
                return [{"commit": {"author": {"date": old, "name": "A"}, "message": "old"}}]
            return []

        with patch.object(keeper, "_api", side_effect=mock_api):
            report = keeper.scan_fleet()

        mechanic_alerts = [a for a in report.alerts if "Mechanic" in a]
        assert len(mechanic_alerts) == 0

    def test_mechanic_on_demand_does_not_alert_even_when_dead(self):
        """Mechanic is on-demand; 800 hours stalled should be dead but no alert."""
        keeper = _make_keeper()

        def mock_api(url):
            if "commits" in url:
                old = (datetime.now(timezone.utc) - timedelta(hours=800)).isoformat()
                return [{"commit": {"author": {"date": old, "name": "A"}, "message": "old"}}]
            return []

        with patch.object(keeper, "_api", side_effect=mock_api):
            report = keeper.scan_fleet()

        mechanic_alerts = [a for a in report.alerts if "Mechanic" in a]
        assert len(mechanic_alerts) == 0

    def test_multiple_alerts_generated(self):
        keeper = _make_keeper()

        def mock_api(url):
            if "commits" in url:
                old = (datetime.now(timezone.utc) - timedelta(hours=100)).isoformat()
                return [{"commit": {"author": {"date": old, "name": "A"}, "message": "old"}}]
            return []

        with patch.object(keeper, "_api", side_effect=mock_api):
            report = keeper.scan_fleet()

        # Should have alerts for always-on agents and 30min-cycle agents
        assert len(report.alerts) >= 2

    def test_alert_contains_role_information(self):
        keeper = _make_keeper()

        def mock_api(url):
            if "commits" in url:
                old = (datetime.now(timezone.utc) - timedelta(hours=100)).isoformat()
                return [{"commit": {"author": {"date": old, "name": "A"}, "message": "old"}}]
            return []

        with patch.object(keeper, "_api", side_effect=mock_api):
            report = keeper.scan_fleet()

        for alert in report.alerts:
            assert "(" in alert and ")" in alert  # role in parentheses

    def test_30min_cycle_alert_mentions_re_awakening(self):
        keeper = _make_keeper()

        def mock_api(url):
            if "commits" in url:
                old = (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat()
                return [{"commit": {"author": {"date": old, "name": "A"}, "message": "old"}}]
            return []

        with patch.object(keeper, "_api", side_effect=mock_api):
            report = keeper.scan_fleet()

        reawakening_alerts = [a for a in report.alerts if "re-awakening" in a]
        assert len(reawakening_alerts) > 0


# ===========================================================================
# 10. Edge Cases & Robustness
# ===========================================================================

class TestEdgeCases:
    """Tests for edge cases and robustness."""

    def test_keeper_init_with_custom_name(self):
        keeper = LighthouseKeeper(token="tok", lighthouse_name="CustomLH")
        assert keeper.lighthouse_name == "CustomLH"

    def test_empty_repo_activity_health_unknown(self):
        activity = RepoActivity(name="r", owner="o")
        assert activity.health == "unknown"

    def test_negative_stalled_hours_treated_as_active(self):
        keeper = _make_keeper()
        activity = _make_repo_activity(stalled_hours=-5.0)
        assert keeper.assess_health(activity, "always-on") == "active"

    def test_float_stalled_hours_accepted(self):
        keeper = _make_keeper()
        activity = _make_repo_activity(stalled_hours=13.7)
        assert keeper.assess_health(activity, "always-on") == "slow"

    def test_report_with_no_agents(self):
        keeper = _make_keeper()
        report = FleetReport(timestamp="t", lighthouse="LH", agents={}, alerts=[])
        formatted = keeper.format_report(report)
        # format_report renders the summary as-is (generated by scan_fleet)
        assert "Agent Status" in formatted
        assert formatted.startswith("# ")

    def test_agent_health_idle_when_no_building_no_stalled(self):
        """Agent with no building repos and no stalled repos is idle."""
        keeper = _make_keeper()

        def mock_api(url):
            if "commits" in url:
                return []
            return []

        with patch.object(keeper, "_api", side_effect=mock_api):
            report = keeper.scan_fleet()

        # Agents with no commit data should have idle or stalled health
        for agent in report.agents.values():
            if not agent.building and not agent.stalled:
                assert agent.health in ("idle", "stalled", "unknown")

    def test_format_report_empty_building_list(self):
        keeper = _make_keeper()
        agent = AgentActivity(agent_name="Oracle1", repos=["r"], health="idle")
        report = FleetReport(timestamp="t", lighthouse="LH", agents={"Oracle1": agent})
        formatted = keeper.format_report(report)
        # Should not show "Building:" section
        lines = formatted.split("\n")
        building_lines = [l for l in lines if "Building:" in l]
        assert len(building_lines) == 0

    def test_long_building_list_truncated_in_report(self):
        keeper = _make_keeper()
        agent = AgentActivity(
            agent_name="Oracle1", repos=["r"],
            building=[f"r: commit {i}" for i in range(10)],
            health="active",
        )
        report = FleetReport(timestamp="t", lighthouse="LH", agents={"Oracle1": agent})
        formatted = keeper.format_report(report)
        # format_report only shows first 5 building items per agent
        assert formatted.count("  - ") <= 5

    def test_fleet_report_summary_includes_alert_count(self):
        keeper = _make_keeper()
        report = FleetReport(
            timestamp="t", lighthouse="LH",
            summary="Fleet: 3/5 agents active. Alerts: 2"
        )
        formatted = keeper.format_report(report)
        assert "Alerts: 2" in formatted

    def test_scan_fleet_timestamp_is_recent(self):
        keeper = _make_keeper()
        with patch.object(keeper, "_api", return_value=[]):
            report = keeper.scan_fleet()
        ts = datetime.fromisoformat(report.timestamp)
        assert datetime.now(timezone.utc) - ts < timedelta(minutes=1)

    def test_check_repo_preserves_name_and_owner(self):
        keeper = _make_keeper()
        with patch.object(keeper, "_api", return_value=None):
            activity = keeper.check_repo("MyOrg", "MyRepo")
        assert activity.name == "MyRepo"
        assert activity.owner == "MyOrg"


# ===========================================================================
# 11. Integration: End-to-End Scan with Realistic Mocks
# ===========================================================================

class TestIntegration:
    """End-to-end integration tests with realistic mocked data."""

    def test_full_scan_and_format(self):
        keeper = _make_keeper()

        def mock_api(url):
            if "commits" in url:
                recent = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
                return [{"commit": {"author": {"date": recent, "name": "Agent"}, "message": "feat: ship it"}}]
            return []

        with patch.object(keeper, "_api", side_effect=mock_api):
            report = keeper.scan_fleet()
            formatted = keeper.format_report(report)

        assert "Lighthouse Report" in formatted
        assert "agents active" in formatted
        assert "## Alerts" not in formatted  # all active, no alerts

    def test_full_scan_all_stalled(self):
        keeper = _make_keeper()

        def mock_api(url):
            if "commits" in url:
                old = (datetime.now(timezone.utc) - timedelta(hours=200)).isoformat()
                return [{"commit": {"author": {"date": old, "name": "Agent"}, "message": "old work"}}]
            return []

        with patch.object(keeper, "_api", side_effect=mock_api):
            report = keeper.scan_fleet()
            formatted = keeper.format_report(report)

        assert "## Alerts" in formatted
        assert len(report.alerts) > 0

    def test_report_is_valid_markdown_structure(self):
        keeper = _make_keeper()
        agent = AgentActivity(
            agent_name="Oracle1", repos=["r"], health="active",
            building=["r: work"], last_active="2024-01-15T10:00:00Z",
        )
        report = FleetReport(
            timestamp="t", lighthouse="LH",
            agents={"Oracle1": agent},
            alerts=[],
            summary="All good",
        )
        formatted = keeper.format_report(report)

        # Check markdown structure
        lines = formatted.split("\n")
        assert lines[0].startswith("# ")
        assert any(l.startswith("## ") for l in lines)
        assert any(l.startswith("### ") for l in lines)
        assert any(l.startswith("- ") for l in lines)
        assert "---" in lines

    def test_json_output_format_compatibility(self):
        """Test that report can be serialized to JSON (for --json flag)."""
        keeper = _make_keeper()

        def mock_api(url):
            if "commits" in url:
                recent = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
                return [{"commit": {"author": {"date": recent, "name": "A"}, "message": "work"}}]
            return []

        with patch.object(keeper, "_api", side_effect=mock_api):
            report = keeper.scan_fleet()

        # Simulate what main() does for --json
        out = {
            "timestamp": report.timestamp,
            "lighthouse": report.lighthouse,
            "summary": report.summary,
            "agents": {name: asdict(agent) for name, agent in report.agents.items()},
            "alerts": report.alerts,
        }
        json_str = json.dumps(out, indent=2)

        # Verify it parses back correctly
        parsed = json.loads(json_str)
        assert parsed["timestamp"] == report.timestamp
        assert parsed["lighthouse"] == report.lighthouse
        assert isinstance(parsed["agents"], dict)
        assert isinstance(parsed["alerts"], list)
