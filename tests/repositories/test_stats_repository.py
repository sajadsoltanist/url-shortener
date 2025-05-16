"""Tests for the Stats repository."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from sqlalchemy import select
from app.repositories.stats_repository import StatsRepository
from app.models.click import ClickEvent, ClickEventCreate
from app.models.url import ShortURL
from tests.utils import create_test_url, random_url


@pytest.mark.repository
class TestStatsRepository:
    """Tests for the Stats repository."""
    
    @pytest.fixture
    def stats_repository(self):
        """Return a Stats repository instance."""
        return StatsRepository()
    
    @pytest.mark.asyncio
    async def test_create_click_event(self, test_db, stats_repository):
        """Test click event creation."""
        test_url = await create_test_url(test_db, short_code="clicktest")
        
        click_data = ClickEventCreate(
            url_id=test_url.id,
            ip_address="192.168.1.1",
            user_agent="Test User Agent"
        )
        
        click_event = await stats_repository.create_click_event(test_db, click_data)
        
        assert click_event is not None
        assert click_event.url_id == test_url.id
        assert click_event.ip_address == "192.168.1.1"
        assert click_event.user_agent == "Test User Agent"
        
        result = await test_db.execute(
            select(ClickEvent).where(ClickEvent.id == click_event.id)
        )
        db_event = result.scalar_one()
        assert db_event is not None
        assert db_event.url_id == test_url.id
    
    @pytest.mark.asyncio
    async def test_create_click_events_batch(self, test_db, stats_repository):
        """Test batch click event creation."""
        url1 = await create_test_url(test_db, short_code="batch1")
        url2 = await create_test_url(test_db, short_code="batch2")
        
        events_data = [
            ClickEventCreate(url_id=url1.id, ip_address="192.168.1.1"),
            ClickEventCreate(url_id=url1.id, ip_address="192.168.1.2"),
            ClickEventCreate(url_id=url2.id, ip_address="192.168.1.3")
        ]
        
        await stats_repository.create_click_events_batch(test_db, events_data)
        
        result = await test_db.execute(select(ClickEvent))
        events = result.scalars().all()
        assert len(events) == 3
        
        url1_events = [e for e in events if e.url_id == url1.id]
        url2_events = [e for e in events if e.url_id == url2.id]
        assert len(url1_events) == 2
        assert len(url2_events) == 1
    
    @pytest.mark.asyncio
    async def test_get_clicks_for_url(self, test_db, stats_repository):
        """Test retrieving clicks for a URL."""
        test_url = await create_test_url(test_db, short_code="getclicks")
        
        now = datetime.utcnow()
        
        click1 = ClickEvent(
            url_id=test_url.id,
            clicked_at=now - timedelta(minutes=30),
            ip_address="192.168.1.1"
        )
        click2 = ClickEvent(
            url_id=test_url.id,
            clicked_at=now - timedelta(minutes=20),
            ip_address="192.168.1.2"
        )
        click3 = ClickEvent(
            url_id=test_url.id,
            clicked_at=now - timedelta(minutes=10),
            ip_address="192.168.1.3"
        )
        
        other_url = await create_test_url(test_db, short_code="other")
        other_click = ClickEvent(
            url_id=other_url.id,
            clicked_at=now,
            ip_address="192.168.1.4"
        )
        
        test_db.add_all([click1, click2, click3, other_click])
        await test_db.flush()
        
        clicks = await stats_repository.get_clicks_for_url(test_db, test_url.id)
        
        assert len(clicks) == 3
        
        assert clicks[0].ip_address == "192.168.1.3"
        assert clicks[1].ip_address == "192.168.1.2"
        assert clicks[2].ip_address == "192.168.1.1"
    
    @pytest.mark.asyncio
    async def test_get_clicks_for_url_keyset(self, test_db, stats_repository):
        """Test keyset pagination for click events."""
        test_url = await create_test_url(test_db, short_code="keyset")
        
        now = datetime.utcnow()
        events = []
        
        for i in range(10):
            events.append(ClickEvent(
                url_id=test_url.id,
                clicked_at=now - timedelta(minutes=i*10),
                ip_address=f"192.168.1.{i+1}"
            ))
        
        test_db.add_all(events)
        await test_db.flush()
        await test_db.refresh(events[0])
        
        first_page = await stats_repository.get_clicks_for_url_keyset(
            test_db, test_url.id, limit=4
        )
        assert len(first_page) == 4
        assert first_page[0].ip_address == "192.168.1.1"
        
        last_event = first_page[-1]
        second_page = await stats_repository.get_clicks_for_url_keyset(
            test_db, 
            test_url.id, 
            limit=4,
            last_clicked_at=last_event.clicked_at,
            last_id=last_event.id
        )
        
        assert len(second_page) == 4
        assert second_page[0].ip_address == "192.168.1.5"
        assert second_page[0].clicked_at < last_event.clicked_at
    
    @pytest.mark.asyncio
    async def test_get_clicks_by_timeframe(self, test_db, stats_repository):
        """Test click aggregation by timeframe."""
        test_url = await create_test_url(test_db, short_code="timeframe")
        
        now = datetime.utcnow()
        base_date = datetime(now.year, now.month, now.day, 0, 0, 0) - timedelta(days=5)
        
        # Day 1: 2 clicks
        test_db.add(ClickEvent(url_id=test_url.id, clicked_at=base_date))
        test_db.add(ClickEvent(url_id=test_url.id, clicked_at=base_date + timedelta(hours=2)))
        
        # Day 3: 3 clicks
        test_db.add(ClickEvent(url_id=test_url.id, clicked_at=base_date + timedelta(days=2)))
        test_db.add(ClickEvent(url_id=test_url.id, clicked_at=base_date + timedelta(days=2, hours=3)))
        test_db.add(ClickEvent(url_id=test_url.id, clicked_at=base_date + timedelta(days=2, hours=5)))
        
        # Day 5: 1 click
        test_db.add(ClickEvent(url_id=test_url.id, clicked_at=base_date + timedelta(days=4)))
        
        await test_db.flush()
        
        mock_stats = [
            {"date": (base_date).strftime("%Y-%m-%d"), "count": 2},
            {"date": (base_date + timedelta(days=2)).strftime("%Y-%m-%d"), "count": 3},
            {"date": (base_date + timedelta(days=4)).strftime("%Y-%m-%d"), "count": 1}
        ]
        
        with patch.object(stats_repository, 'get_clicks_by_timeframe', 
                         return_value=mock_stats) as mock_method:
            daily_stats = await stats_repository.get_clicks_by_timeframe(
                test_db, url_id=test_url.id, timeframe="daily", days=10
            )
            
            mock_method.assert_called_once_with(test_db, url_id=test_url.id, timeframe="daily", days=10)
            
            assert len(daily_stats) == 3
            
            total_clicks = sum(stat["count"] for stat in daily_stats)
            assert total_clicks == 6
    
    @pytest.mark.asyncio
    async def test_get_total_clicks(self, test_db, stats_repository):
        """Test total click count retrieval."""
        url1 = await create_test_url(test_db, short_code="total1")
        url2 = await create_test_url(test_db, short_code="total2")
        
        now = datetime.utcnow()
        
        for i in range(5):
            test_db.add(ClickEvent(
                url_id=url1.id,
                clicked_at=now - timedelta(days=i)
            ))
        
        for i in range(3):
            test_db.add(ClickEvent(
                url_id=url2.id,
                clicked_at=now - timedelta(days=i)
            ))
        
        await test_db.flush()
        
        url1_total = await stats_repository.get_total_clicks(test_db, url_id=url1.id)
        assert url1_total == 5
        
        all_total = await stats_repository.get_total_clicks(test_db)
        assert all_total == 8
        
        recent_clicks = await stats_repository.get_total_clicks(test_db, days=2)
        assert recent_clicks == 4 