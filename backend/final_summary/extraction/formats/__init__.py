"""
--------------------------------
FORMAT_REGISTRY maps BuyerFactoryPair.report_type values to extractor classes.

Usage
-----
    from extraction.formats import get_extractor

    extractor = get_extractor(pair)
    record    = extractor.extract(path, sheet_name, inspection_date, pair)

Adding a new format
-------------------
1. Create extraction/formats/<format_name>.py inheriting BaseExtractor.
2. Set REPORT_TYPE = "<FORMAT_KEY>" on the class.
3. Add it to FORMAT_REGISTRY below.
4. Add the new key to ReportType choices in models/buyer_factory_pair.py.
That is all — no other files need changing.
"""

from .base        import BaseExtractor, AuditRecord
from .knit_35     import Knit35Extractor
from .woven_37    import Woven37Extractor
from .woven_78    import Woven78Extractor
from .sweater_37  import Sweater37Extractor

# ---------------------------------------------------------------------------
# Registry — maps report_type string → extractor class
# ---------------------------------------------------------------------------

FORMAT_REGISTRY: dict[str, type[BaseExtractor]] = {
    "KNIT_35":    Knit35Extractor,
    "WOVEN_37":   Woven37Extractor,
    "WOVEN_78":   Woven78Extractor,
    "SWEATER_37": Sweater37Extractor,
}


def get_extractor(pair) -> BaseExtractor:
    """
    Return the correct extractor instance for the given BuyerFactoryPair.

    Parameters
    ----------
    pair : BuyerFactoryPair instance

    Returns
    -------
    Instantiated extractor for pair.report_type.
    Falls back to Woven78Extractor if the type is unrecognised.
    """
    extractor_cls = FORMAT_REGISTRY.get(pair.report_type)

    if extractor_cls is None:
        import logging
        logging.warning(
            f"get_extractor: unknown report_type '{pair.report_type}' "
            f"for pair {pair}. Falling back to Woven78Extractor."
        )
        extractor_cls = Woven78Extractor

    return extractor_cls()


__all__ = [
    "BaseExtractor",
    "AuditRecord",
    "Knit35Extractor",
    "Woven37Extractor",
    "Woven78Extractor",
    "Sweater37Extractor",
    "FORMAT_REGISTRY",
    "get_extractor",
]