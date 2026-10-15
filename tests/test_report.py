from eval.report import value_coverage, value_precision


def test_value_coverage_recall():
    oracle = [100.0, 200.0, 300.0]
    assert value_coverage([100.0, 200.0, 300.0], oracle) == 1.0
    assert value_coverage([100.0], oracle) == 1 / 3


def test_value_precision_catches_extra_wrong_values():
    oracle = [100.0, 200.0]
    # All claimed values present -> precision 1.0
    assert value_precision([100.0, 200.0], oracle) == 1.0
    # Extra wrong value (a leaked ticker/metric) -> precision drops, recall stays 1.0
    claimed = [100.0, 200.0, 999.0]
    assert value_precision(claimed, oracle) == 2 / 3
    assert value_coverage(claimed, oracle) == 1.0  # recall ignores the extra value
