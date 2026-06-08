"""
Unit tests for the BigQuery service query execution.
"""

from unittest.mock import MagicMock, patch

import pytest

from api.services.bigquery_service import BigQueryService


@pytest.fixture
def mock_bq_client():
    with patch("api.services.bigquery_service.bigquery.Client") as mock_class:
        mock_instance = MagicMock()
        mock_class.return_value = mock_instance
        yield mock_instance


def test_bq_service_ping(mock_bq_client):
    service = BigQueryService(project_id="test-proj", dataset="test-ds", location="US")
    mock_bq_client.list_datasets.return_value = []
    service.ping()
    mock_bq_client.list_datasets.assert_called_once_with(max_results=1)


def test_bq_service_get_policy_by_id_found(mock_bq_client):
    service = BigQueryService(project_id="test-proj", dataset="test-ds", location="US")

    # Mock BQ query result rows
    mock_query_job = MagicMock()
    mock_row = {
        "policy_id": "POL-12345",
        "holder_name": "Alice Smith",
        "holder_email": "alice@example.com",
        "plan_id": "PLAN-001",
        "plan_type": "HMO",
        "effective_date": "2026-01-01",
        "expiry_date": "2026-12-31",
        "premium_amount": 300.00,
        "status": "ACTIVE",
        "state": "CA",
    }
    mock_query_job.result.return_value = [mock_row]
    mock_bq_client.query.return_value = mock_query_job

    policy = service.get_policy_by_id("POL-12345")
    assert policy is not None
    assert policy.policy_id == "POL-12345"
    assert policy.holder_name == "Alice Smith"
    assert policy.premium_amount == 300.00


def test_bq_service_get_policy_by_id_not_found(mock_bq_client):
    service = BigQueryService(project_id="test-proj", dataset="test-ds", location="US")
    mock_query_job = MagicMock()
    mock_query_job.result.return_value = []
    mock_bq_client.query.return_value = mock_query_job

    policy = service.get_policy_by_id("POL-99999")
    assert policy is None
