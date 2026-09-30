from sms import sms_venue


def test_the_short_name_wins_and_the_full_venue_is_the_fallback():
    assert sms_venue({"venue": "Full Hall", "venue_sms": "Hall"}) == "Hall"
    assert sms_venue({"venue": "Full Hall"}) == "Full Hall"
    assert sms_venue({"venue": "Full Hall", "venue_sms": None}) == "Full Hall"


def test_a_token_reads_its_collection_fields():
    assert sms_venue({"collection_venue": "Full Hospital", "collection_venue_sms": "Hospital"}) == "Hospital"
    assert sms_venue({"collection_venue": "Full Hospital"}) == "Full Hospital"
    assert sms_venue({"collection_venue": "Full Hospital", "collection_venue_sms": None}) == "Full Hospital"


def test_spacing_is_tidied_and_a_blank_short_name_falls_back():
    assert sms_venue({"venue": "Full Hall", "venue_sms": "  SNP   Office "}) == "SNP Office"
    assert sms_venue({"venue": "  Full   Hall ", "venue_sms": "   "}) == "Full Hall"


def test_nothing_to_name_gives_an_empty_string_and_never_raises():
    assert sms_venue(None) == ""
    assert sms_venue({}) == ""
    assert sms_venue({"venue": None}) == ""
    assert sms_venue({"venue_sms": ""}) == ""
    assert sms_venue({"collection_venue": None, "collection_venue_sms": None}) == ""


def test_the_function_does_not_judge_the_venue():
    assert sms_venue({"venue": "NA"}) == "NA"
    assert sms_venue({"venue": "A" * 40}) == "A" * 40
    assert sms_venue({"venue": "Hall", "venue_sms": "call 9876543210"}) == "call 9876543210"
