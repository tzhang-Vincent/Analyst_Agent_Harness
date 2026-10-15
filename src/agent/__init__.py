"""Financial research agent with full provenance tracking over SEC EDGAR."""

from .analyst import Analyst
from .edgar import EdgarClient, filing_index_url
from .metrics import METRICS, canonical_metric
from .schema import Answer, Fact, Provenance, QueryIntent

__version__ = "0.1.0"

__all__ = [
    "Analyst",
    "EdgarClient",
    "filing_index_url",
    "METRICS",
    "canonical_metric",
    "Answer",
    "Fact",
    "Provenance",
    "QueryIntent",
    "__version__",
]
