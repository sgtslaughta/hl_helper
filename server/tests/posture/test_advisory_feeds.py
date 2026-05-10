"""Tests for advisory feed sources, parsing, and scheduler."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from server.app.advisory.feeds import (
    FeedAdvisory,
    FeedAffected,
)
from server.app.advisory.feeds.osv import parse_osv_record
from server.app.advisory.feeds.epss import EPSSScoreFeed, parse_epss_csv
from server.app.advisory.feeds.kev import KEVScoreFeed, parse_kev_json
from server.app.advisory.store import upsert_advisories, apply_scores
from server.app.advisory.worker import AdvisoryWorker
from server.app.settings.config import FleetSettings
from server.app.models import Advisory, AffectedPackage


class TestParseOSVRecord:
    """Tests for OSV record parsing."""

    def test_parse_osv_record_minimal(self):
        """Parse a minimal OSV dict with id, summary, affected[1]."""
        osv_dict = {
            "id": "GHSA-xxxx-yyyy-zzzz",
            "summary": "Test vulnerability",
            "affected": [
                {
                    "package": {"name": "package-a", "ecosystem": "npm"},
                    "ranges": [{"type": "ECOSYSTEM", "events": [{"fixed": "1.0.0"}]}],
                }
            ],
            "references": [{"url": "https://example.com"}],
        }
        result = parse_osv_record(osv_dict)
        assert result is not None
        assert result.id == "GHSA-xxxx-yyyy-zzzz"
        assert result.summary == "Test vulnerability"
        assert len(result.affected) == 1
        assert result.affected[0].package == "package-a"
        assert result.affected[0].ecosystem == "npm"

    def test_parse_osv_record_severity_mapping(self):
        """Parse OSV with CVSS_V3 severity mapping."""
        osv_dict = {
            "id": "CVE-2024-1234",
            "summary": "Critical issue",
            "severity": [{"type": "CVSS_V3", "score": "9.8"}],
            "affected": [
                {
                    "package": {"name": "pkg", "ecosystem": "pypi"},
                    "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}]}],
                }
            ],
            "aliases": ["GHSA-abcd-efgh-ijkl"],
            "published": "2024-01-01T00:00:00Z",
            "modified": "2024-01-02T00:00:00Z",
        }
        result = parse_osv_record(osv_dict)
        assert result is not None
        assert result.id == "CVE-2024-1234"
        assert result.cvss_v3 == "9.8"
        assert "GHSA-abcd-efgh-ijkl" in result.aliases
        assert result.published is not None

    def test_parse_osv_record_no_affected_skipped(self):
        """Records without affected array should be skipped."""
        osv_dict = {
            "id": "GHSA-skip-this-one",
            "summary": "No packages affected",
        }
        result = parse_osv_record(osv_dict)
        assert result is None


class TestParseEPSSCSV:
    """Tests for EPSS CSV parsing."""

    def test_parse_epss_csv(self):
        """Parse synthetic EPSS CSV with header and data rows."""
        csv_text = """\
# EPSS CSV Header
cve,epss,percentile
CVE-2024-0001,0.95,99.0
CVE-2024-0002,0.45,50.0
CVE-2024-0003,0.05,5.0
"""
        result = parse_epss_csv(csv_text)
        assert result == {
            "CVE-2024-0001": 0.95,
            "CVE-2024-0002": 0.45,
            "CVE-2024-0003": 0.05,
        }


class TestParseKEVJSON:
    """Tests for KEV JSON parsing."""

    def test_parse_kev_json(self):
        """Parse KEV JSON fixture with 2 vulnerabilities."""
        kev_dict = {
            "vulnerabilities": [
                {"cveID": "CVE-2024-0001", "knownRansomwareCampaignUse": "Yes"},
                {"cveID": "CVE-2024-0002", "knownRansomwareCampaignUse": "No"},
            ]
        }
        result = parse_kev_json(kev_dict)
        assert result == {"CVE-2024-0001": True, "CVE-2024-0002": True}


class TestUpsertAdvisories:
    """Tests for advisory upsert logic."""

    @pytest.mark.asyncio
    async def test_upsert_advisories_inserts_and_updates(self, sm):
        """Insert 1 advisory, re-run with modified summary, assert updated."""
        item1 = FeedAdvisory(
            id="CVE-2024-1",
            aliases=["GHSA-a"],
            summary="Original summary",
            description_md="Desc",
            severity="high",
            cvss_v3="7.5",
            cvss_v4=None,
            published=datetime.fromisoformat("2024-01-01T00:00:00+00:00"),
            modified=datetime.fromisoformat("2024-01-02T00:00:00+00:00"),
            refs=["https://example.com"],
            affected=[
                FeedAffected(
                    ecosystem="npm",
                    package="test-pkg",
                    introduced="1.0.0",
                    fixed="2.0.0",
                )
            ],
        )

        async with sm() as session:
            inserted, updated = await upsert_advisories(
                sm, [item1], source="test"
            )
            await session.commit()
            assert inserted == 1
            assert updated == 0

            adv = await session.get(Advisory, "CVE-2024-1")
            assert adv.summary == "Original summary"
            pkg = await session.get(AffectedPackage, 1)
            assert pkg.package == "test-pkg"

        # Update the advisory
        item2 = FeedAdvisory(
            id="CVE-2024-1",
            aliases=["GHSA-a"],
            summary="Updated summary",
            description_md="New desc",
            severity="critical",
            cvss_v3="9.0",
            cvss_v4=None,
            published=datetime.fromisoformat("2024-01-01T00:00:00+00:00"),
            modified=datetime.fromisoformat("2024-01-03T00:00:00+00:00"),
            refs=["https://example.com"],
            affected=[
                FeedAffected(
                    ecosystem="pypi",
                    package="new-pkg",
                    introduced=None,
                    fixed="3.0.0",
                )
            ],
        )

        inserted, updated = await upsert_advisories(
            sm, [item2], source="test"
        )
        assert inserted == 0
        assert updated == 1

        # Check in a fresh session
        async with sm() as session:
            adv = await session.get(Advisory, "CVE-2024-1")
            assert adv.summary == "Updated summary"
            # Query for packages affected by this advisory
            from sqlalchemy import select
            stmt = select(AffectedPackage).where(
                AffectedPackage.advisory_id == "CVE-2024-1"
            )
            result = await session.execute(stmt)
            pkgs = result.scalars().all()
            # Should have exactly 1 new package
            assert len(pkgs) == 1
            assert pkgs[0].package == "new-pkg"
            assert pkgs[0].ecosystem == "pypi"


class TestApplyScores:
    """Tests for applying EPSS and KEV scores."""

    @pytest.mark.asyncio
    async def test_apply_scores_epss_and_kev(self, sm: async_sessionmaker):
        """Seed advisory, apply scores via id and alias."""
        async with sm() as session:
            adv = Advisory(
                id="CVE-2024-1",
                aliases=["GHSA-x"],
                summary="Test",
                severity="unknown",
                refs=[],
            )
            session.add(adv)
            await session.commit()

        # Apply EPSS by id
        async with sm() as session:
            count = await apply_scores(
                sm,
                {"CVE-2024-1": 0.85},
                kind="epss",
            )
            await session.commit()
            assert count == 1
            adv = await session.get(Advisory, "CVE-2024-1")
            assert adv.epss == 0.85

        # Apply KEV by alias
        async with sm() as session:
            count = await apply_scores(
                sm,
                {"GHSA-x": True},
                kind="kev",
            )
            await session.commit()
            assert count == 1
            adv = await session.get(Advisory, "CVE-2024-1")
            assert adv.kev is True


class TestAdvisoryWorkerFeeds:
    """Smoke-tests for AdvisoryWorker._run_feed wiring (replaces the old AdvisoryScheduler)."""

    @pytest.mark.asyncio
    async def test_worker_runs_all_three_feeds(self, sm):
        osv_result = [
            FeedAdvisory(
                id="GHSA-test",
                aliases=[],
                summary="Test advisory",
                description_md=None,
                severity="medium",
                cvss_v3=None,
                cvss_v4=None,
                published=None,
                modified=None,
                refs=[],
                affected=[
                    FeedAffected(
                        ecosystem="npm",
                        package="test-pkg",
                        introduced=None,
                        fixed="1.0.0",
                    )
                ],
            )
        ]
        epss_result = {"GHSA-test": 0.75}
        kev_result = {"GHSA-test": True}

        settings = FleetSettings(advisory_ecosystems=["npm"])
        worker = AdvisoryWorker(catalog_sm=sm, fleet_sm=sm, settings=settings)

        async def fake_osv_stream(_sm, *, ecosystem_allowlist=None, batch_size=500, url=""):
            from server.app.advisory.store import upsert_advisories
            ins, upd = await upsert_advisories(_sm, osv_result, "osv")
            return ins, upd, []

        with patch("server.app.advisory.feeds.osv_stream.osv_sync_stream", side_effect=fake_osv_stream), \
             patch.object(EPSSScoreFeed, "sync", new_callable=AsyncMock) as mock_epss, \
             patch.object(KEVScoreFeed, "sync", new_callable=AsyncMock) as mock_kev:
            mock_epss.return_value = epss_result
            mock_kev.return_value = kev_result

            await worker._run_feed("osv", trigger="test")
            await worker._run_feed("epss", trigger="test")
            await worker._run_feed("kev", trigger="test")

        # Every feed should record a status row
        statuses = await worker.get_status()
        names = {s["feed"] for s in statuses}
        assert names == {"osv", "epss", "kev"}
        assert all(s["last_sync_at"] is not None for s in statuses)
