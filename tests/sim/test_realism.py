from bts.sim.realism import TARGETS, simulate_many


def test_report_table_lists_all_targets():
    r = simulate_many(3)
    assert set(r.metrics) == {t.name for t in TARGETS}
    assert r.table().count("|") >= 7 * 4


def test_generator_is_realistic_over_40_matches():
    r = simulate_many(40)
    assert r.passes(), r.table()
