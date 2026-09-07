import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from routes_templates import _validate_logos


@pytest.mark.parametrize("logos", [
    {}, "invalid", [None], ["invalid"], [{"data_url": None}],
    [{"data_url": 1}], [{"data_url": "data:image/png;base64,%%%"}],
])
def test_invalid_logo_payload_is_rejected(logos):
    with pytest.raises(HTTPException) as error:
        _validate_logos(logos)
    assert error.value.status_code == 400
