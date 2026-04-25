from __future__ import annotations

import importlib


def test_lingxi_tool_definitions_use_supported_categories() -> None:
    import backend.core.s02_tools.builtin.lingxi as lingxi

    importlib.reload(lingxi)

    definitions = [
        lingxi.create_lingxi_financial_search_tool()[0],
        lingxi.create_lingxi_realtime_marketdata_tool()[0],
        lingxi.create_lingxi_ranklist_tool()[0],
        lingxi.create_lingxi_smart_stock_selection_tool()[0],
    ]

    assert {definition.category for definition in definitions} == {"search"}
