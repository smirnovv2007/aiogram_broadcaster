from collections import defaultdict
from collections.abc import Generator
from typing import TYPE_CHECKING, Any, Optional, TypeVar
from aiogram.utils.text_decorations import HtmlDecoration
from sulguk import transform_html

from pydantic import BaseModel

from .items.jinja import JinjaPlaceholderEngine, JinjaPlaceholderItem
from .items.regexp import RegexpPlaceholderEngine, RegexpPlaceholderItem
from .items.string import StringPlaceholderEngine, StringPlaceholderItem
from .placeholder import Placeholder


if TYPE_CHECKING:
    from .items.base import BasePlaceholderEngine, BasePlaceholderItem


ModelType = TypeVar("ModelType", bound=BaseModel)

TEXT_FIELDS = {"text", "caption", "title", "description"}
ENTITIES_FIELD_MAP = {
    "text": "entities",
    "caption": "caption_entities",
}

class PlaceholderManager(Placeholder):
    __chain_root__ = True

    def __init__(self, name: Optional[str] = None) -> None:
        super().__init__(name=name)

        self.engines: dict[type[BasePlaceholderItem], BasePlaceholderEngine] = {
            JinjaPlaceholderItem: JinjaPlaceholderEngine(),
            RegexpPlaceholderItem: RegexpPlaceholderEngine(),
            StringPlaceholderItem: StringPlaceholderEngine(),
        }

        self.html_decoration = HtmlDecoration()

    async def render(self, model: ModelType, /, **context: Any) -> ModelType:
        if not tuple(self.chain_items):
            return model
        updates: dict[str, Any] = {}
        for field_name, field_value, entities in self._parse_text_fields(model):
            if entities is not None:
                html = self.html_decoration.unparse(field_value, entities)
                rendered_html = await self._render_source(html, **context)

                if rendered_html != html:
                    sulguk_result = transform_html(rendered_html.replace("\n", "<br />"))
                    updates[field_name] = sulguk_result.text
                    updates[ENTITIES_FIELD_MAP[field_name]] = sulguk_result.entities
            else:
                rendered = await self._render_source(field_value, **context)
                if rendered != field_value:
                    updates[field_name] = rendered

        if updates:
            model = model.model_copy(update=updates)
        return model

    def _parse_text_fields(self, model: BaseModel) -> Generator[tuple[str, str], None, None]:
        mapped_model = dict(model)
        for field_name in TEXT_FIELDS:
            text_value = mapped_model.get(field_name)
            if text_value:
                entities_field = ENTITIES_FIELD_MAP.get(field_name)
                entities = mapped_model.get(entities_field) if entities_field else None
                yield field_name, text_value, entities

    async def _render_source(self, source: str, /, **context: Any) -> str:
        grouped_items = defaultdict(set)
        for item in self.chain_items:
            grouped_items[type(item)].add(item)
        for item_type, items in grouped_items.items():
            source = await self.engines[item_type].render(
                source,
                *items,
                **context,
            )
        return source
