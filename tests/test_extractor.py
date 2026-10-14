import pytest

from agent.extractor import extract_metric, extract_metrics
from agent.schema import Fact


class FakeClient:
    """Duck-typed stand-in for EdgarClient with canned companyfacts JSON."""

    def __init__(self, cik: str, company_facts: dict):
        self._cik = cik
        self._facts = company_facts

    def ticker_to_cik(self, ticker):
        return self._cik

    def get_company_facts(self, cik):
        return self._facts


def _fact(start, end, val, frame, filed, accn, form="10-Q", fy=None, fp=None):
    return {
        "start": start,
        "end": end,
        "val": val,
        "frame": frame,
        "filed": filed,
        "accn": accn,
        "form": form,
        "fy": fy,
        "fp": fp,
    }


# Four consecutive ~90-day quarters, with CY2023Q2 filed twice (restatement).
REVENUE_FACTS = {
    "entityName": "NVIDIA CORP",
    "facts": {
        "us-gaap": {
            "RevenueFromContractWithCustomerExcludingAssessedTax": {
                "label": "RevenueFromContractWithCustomerExcludingAssessedTax",
                "units": {
                    "USD": [
                        _fact("2023-01-01", "2023-03-31", 7192000000, "CY2023Q1", "2023-05-26", "a1", fy=2023, fp="Q1"),
                        _fact("2023-04-01", "2023-06-30", 13507000000, "CY2023Q2", "2023-08-28", "a2", fy=2023, fp="Q2"),
                        # restated in a later 10-K: same (start,end), later filed -> wins
                        _fact("2023-04-01", "2023-06-30", 13510000000, "CY2023Q2", "2024-02-21", "a3", form="10-K", fy=2023, fp="Q2"),
                        _fact("2023-07-01", "2023-09-30", 18120000000, "CY2023Q3", "2023-11-21", "a4", fy=2023, fp="Q3"),
                        _fact("2023-10-01", "2023-12-31", 22103000000, "CY2023Q4", "2024-02-21", "a5", fy=2023, fp="Q4"),
                    ]
                },
            }
        }
    },
}


def test_extract_metric_picks_restated_value_and_orders():
    client = FakeClient("0001045810", REVENUE_FACTS)
    facts = extract_metric(client, "NVDA", "revenue", frequency="quarterly", n=4)

    assert [f.period for f in facts] == ["2023-03-31", "2023-06-30", "2023-09-30", "2023-12-31"]
    assert [f.period_label for f in facts] == ["Q1 FY2023", "Q2 FY2023", "Q3 FY2023", "Q4 FY2023"]
    # The CY2023Q2 fact kept is the later-filed restatement.
    q2 = next(f for f in facts if f.period == "2023-06-30")
    assert q2.provenance.value == 13510000000
    assert q2.provenance.form == "10-K"
    assert q2.provenance.accession_number == "a3"


def test_provenance_fields_populated():
    client = FakeClient("0001045810", REVENUE_FACTS)
    facts = extract_metric(client, "NVDA", "revenue", frequency="quarterly", n=1)
    assert len(facts) == 1
    p = facts[0].provenance
    assert p.ticker == "NVDA"
    assert p.cik == "0001045810"
    assert p.entity_name == "NVIDIA CORP"
    assert p.xbrl_tag == "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert p.unit == "USD"
    assert p.fiscal_period == "Q4"
    assert p.fiscal_year == 2023
    assert p.start_date == "2023-10-01"
    assert p.end_date == "2023-12-31"
    assert p.source_url.startswith("https://www.sec.gov/Archives/edgar/data/")


def test_synonym_fallback_when_primary_tag_absent():
    data = {
        "entityName": "OLD CO",
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "label": "Revenues",
                    "units": {
                        "USD": [_fact("2023-01-01", "2023-03-31", 100, "CY2023Q1", "2023-05-01", "b1", fy=2023, fp="Q1")]
                    },
                }
            }
        },
    }
    client = FakeClient("0000000001", data)
    facts = extract_metric(client, "OLD", "revenue", frequency="quarterly", n=4)
    assert len(facts) == 1
    assert facts[0].provenance.xbrl_tag == "Revenues"


def test_prefers_most_recent_tag_over_stale_primary():
    # Primary synonym is stale; the fallback tag has recent data.
    data = {
        "entityName": "NVIDIA CORP",
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "label": "RevExcl",
                    "units": {
                        "USD": [
                            _fact("2018-01-01", "2018-03-31", 1, "CY2018Q1", "2018-05-01", "s1", fy=2018, fp="Q1"),
                            _fact("2018-04-01", "2018-06-30", 2, "CY2018Q2", "2018-08-01", "s2", fy=2018, fp="Q2"),
                            _fact("2018-07-01", "2018-09-30", 3, "CY2018Q3", "2018-11-01", "s3", fy=2018, fp="Q3"),
                            _fact("2018-10-01", "2018-12-31", 4, "CY2018Q4", "2019-02-01", "s4", fy=2018, fp="Q4"),
                        ]
                    },
                },
                "Revenues": {
                    "label": "Revenues",
                    "units": {
                        "USD": [
                            _fact("2025-01-01", "2025-03-31", 100, "CY2025Q1", "2025-05-01", "r1", fy=2025, fp="Q1"),
                            _fact("2025-04-01", "2025-06-30", 200, "CY2025Q2", "2025-08-01", "r2", fy=2025, fp="Q2"),
                            _fact("2025-07-01", "2025-09-30", 300, "CY2025Q3", "2025-11-01", "r3", fy=2025, fp="Q3"),
                            _fact("2025-10-01", "2025-12-31", 400, "CY2025Q4", "2026-02-01", "r4", fy=2025, fp="Q4"),
                        ]
                    },
                },
            }
        },
    }
    client = FakeClient("0001045810", data)
    facts = extract_metric(client, "NVDA", "revenue", frequency="quarterly", n=4)
    assert facts[0].provenance.xbrl_tag == "Revenues"
    assert [f.period for f in facts] == ["2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31"]


def test_annual_frequency():
    data = {
        "entityName": "NVIDIA CORP",
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "label": "Revenue",
                    "units": {
                        "USD": [
                            _fact("2021-01-30", "2022-01-28", 26974000000, "CY2021", "2022-03-18", "c1", form="10-K", fy=2021, fp="FY"),
                            _fact("2022-01-29", "2023-01-27", 26974000000, "CY2022", "2023-02-24", "c2", form="10-K", fy=2022, fp="FY"),
                            _fact("2023-01-28", "2024-01-26", 60922000000, "CY2023", "2024-02-21", "c3", form="10-K", fy=2023, fp="FY"),
                        ]
                    },
                }
            }
        },
    }
    client = FakeClient("0001045810", data)
    facts = extract_metric(client, "NVDA", "revenue", frequency="annual", n=2)
    assert [f.period for f in facts] == ["2023-01-27", "2024-01-26"]
    assert [f.period_label for f in facts] == ["FY2023", "FY2024"]


def test_yearly_cumulative_facts_excluded():
    # A 6-month cumulative fact must not leak into quarterly output.
    data = {
        "entityName": "CO",
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "label": "Revenues",
                    "units": {
                        "USD": [
                            _fact("2023-01-01", "2023-06-30", 999, None, "2023-08-01", "y1", fy=2023, fp="H1"),  # 6-month YTD
                            _fact("2023-01-01", "2023-03-31", 100, "CY2023Q1", "2023-05-01", "q1", fy=2023, fp="Q1"),
                        ]
                    },
                }
            }
        },
    }
    client = FakeClient("0000000001", data)
    facts = extract_metric(client, "CO", "revenue", frequency="quarterly", n=4)
    assert [f.provenance.value for f in facts] == [100]


def test_unknown_metric_raises():
    client = FakeClient("0001045810", REVENUE_FACTS)
    with pytest.raises(ValueError):
        extract_metric(client, "NVDA", "does_not_exist")


def test_extract_metrics_multiple():
    client = FakeClient("0001045810", REVENUE_FACTS)
    out = extract_metrics(client, "NVDA", ["revenue", "net_income"], n=2)
    assert "revenue" in out and "net_income" in out
    assert len(out["revenue"]) == 2
    assert out["net_income"] == []  # no net-income facts in canned data
