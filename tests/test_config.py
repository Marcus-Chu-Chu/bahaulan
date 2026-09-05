from pipeline import config


def test_bbox_is_ordered():
    assert config.LAT_MIN < config.LAT_MAX
    assert config.LON_MIN < config.LON_MAX


def test_warning_bands_descend():
    thresholds = [t for t, _ in config.WARNING_BANDS]
    assert thresholds == sorted(thresholds, reverse=True)
