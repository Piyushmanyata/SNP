import asyncio

import pytest
from fastapi import HTTPException

from security import require_clinical


@pytest.mark.parametrize("role", ["admin", "clinical_desk_operator"])
def test_admin_and_the_clinical_desk_operator_use_the_clinical_desk(role):
    user = {"role": role}
    assert asyncio.run(require_clinical(user=user)) is user


@pytest.mark.parametrize("role", ["team_lead", "volunteer"])
def test_door_staff_are_refused_the_clinical_desk(role):
    with pytest.raises(HTTPException) as refused:
        asyncio.run(require_clinical(user={"role": role}))
    assert refused.value.status_code == 403
