from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models import Market, Product, Template
from app.schemas.template import TemplateUpdate
from app.services import templates as template_service


@pytest.mark.asyncio
async def test_market_may_preview_global_template(monkeypatch):
    market = Market(id=uuid4(), name="Preview Market", slug=f"preview-{uuid4().hex[:8]}")
    template = Template(id=uuid4(), name="Global", slug="global", is_global=True, market_id=None)
    product = Product(id=uuid4(), market_id=market.id, name="Milk", is_active=True)

    class Session:
        async def get(self, model, item_id):
            return market

        async def scalars(self, statement):
            return SimpleNamespace(all=lambda: [product])

    async def get_template(*args, **kwargs):
        return template

    monkeypatch.setattr(template_service, "get_template", get_template)
    monkeypatch.setattr(template_service, "render_campaign_preview_html", lambda *args, **kwargs: "<html />")

    result = await template_service.render_template_preview(Session(), template.id, market.id)

    assert result["template_name"] == "Global"
    assert result["html"] == "<html />"


@pytest.mark.asyncio
async def test_market_cannot_update_global_template(monkeypatch):
    template = Template(id=uuid4(), name="Global", slug="global", is_global=True, market_id=None)
    monkeypatch.setattr(template_service, "get_template", lambda *args, **kwargs: _return(template))

    with pytest.raises(HTTPException) as error:
        await template_service.update_template(object(), template.id, TemplateUpdate(name="Changed"), uuid4())

    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_market_owned_template_update_remains_allowed(monkeypatch):
    template = Template(id=uuid4(), name="Market", slug="market", is_global=False, market_id=uuid4())
    persisted = []

    async def get_template(*args, **kwargs):
        return template

    async def persist(session, value):
        persisted.append(value)
        return value

    monkeypatch.setattr(template_service, "get_template", get_template)
    monkeypatch.setattr(template_service, "_persist", persist)

    result = await template_service.update_template(object(), template.id, TemplateUpdate(name="Updated"), template.market_id)

    assert result.name == "Updated"
    assert persisted == [template]


async def _return(value):
    return value
