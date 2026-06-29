from datetime import datetime, timezone

from src.domain.models.job import CrawlJob, JobStatus
from src.domain.models.property import CrawledProperty, Location


def test_crawled_property_defaults():
    p = CrawledProperty(
        source_url="https://example.com/listing/1",
        source_site="example.com",
        title="Test Listing",
    )
    assert p.property_id is not None
    assert p.description is None
    assert p.price_monthly is None
    assert p.amenities == []
    assert p.confidence == 0.5
    assert p.crawled_at.tzinfo is not None


def test_crawled_property_with_location():
    p = CrawledProperty(
        source_url="https://example.com/listing/1",
        source_site="example.com",
        title="Test Listing",
        location=Location(lat=34.0522, lng=-118.2437, address="Los Angeles"),
        price_monthly=1500.0,
        bedrooms=2,
    )
    assert p.location is not None
    assert p.location.lat == 34.0522
    assert p.price_monthly == 1500.0
    assert p.bedrooms == 2


def test_crawl_job_defaults():
    job = CrawlJob(search_id="test-123", query="studio near UCLA")
    assert job.status == JobStatus.QUEUED
    assert job.progress == 0
    assert job.error is None
    assert job.completed_at is None


def test_crawl_job_status_transition():
    job = CrawlJob(search_id="test-123", query="test")
    job.status = JobStatus.SCRAPING
    job.progress = 5
    assert job.status == JobStatus.SCRAPING
    assert job.progress == 5


def test_crawled_property_serialization():
    p = CrawledProperty(
        source_url="https://example.com/listing/1",
        source_site="example.com",
        title="Test",
        crawled_at=datetime(2026, 6, 29, tzinfo=timezone.utc),
    )
    data = p.model_dump(mode="json")
    assert data["source_url"] == "https://example.com/listing/1"
    assert "2026-06-29T00:00:00" in data["crawled_at"]
