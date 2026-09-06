from pipeline import config


def test_bbox_is_ordered():
    assert config.LAT_MIN < config.LAT_MAX
    assert config.LON_MIN < config.LON_MAX


def test_warning_bands_descend():
    thresholds = [t for t, _ in config.WARNING_BANDS]
    assert thresholds == sorted(thresholds, reverse=True)


def test_past_days_exceeds_archive_lag():
    # The forecast snapshot's past_days window has to bridge the ERA5 publication lag on its
    # own, and the archive re-fetch window has to be at least as long as that lag so a day
    # first published as null is asked for again once ERA5 fills it in.
    assert config.PAST_DAYS > config.ARCHIVE_LAG_DAYS
    assert config.ARCHIVE_REFETCH_DAYS >= config.ARCHIVE_LAG_DAYS
