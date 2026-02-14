"""
Generate a new API resource: model, schema, repository, service, router, and wire into app.
Usage: poetry run new-resource <name> [--fields "field:type,..."]
Example: poetry run new-resource product --fields "name:str,description:str|None"
"""
import re
import sys
from pathlib import Path

# Project root (app/core/generators/ -> project root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
APP = PROJECT_ROOT / "app"


def to_pascal(s: str) -> str:
    """product_item -> ProductItem."""
    return "".join(w.capitalize() for w in s.replace("-", "_").split("_"))


def to_snake(s: str) -> str:
    """ProductItem -> product_item."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", s).lower()


def to_plural_snake(s: str) -> str:
    """product -> products; category -> categories."""
    base = to_snake(s).replace("-", "_")
    if base.endswith("s"):
        return f"{base}es"
    if base.endswith("y") and len(base) > 1 and base[-2] not in "aeiou":
        return f"{base[:-1]}ies"
    return f"{base}s"


def parse_fields(fields_str: str) -> list[tuple[str, str, bool]]:
    """Parse 'name:str,email:str|None' -> [(name, str, False), (email, str, True)]."""
    out = []
    for part in fields_str.strip().split(","):
        part = part.strip()
        if ":" not in part:
            continue
        name, type_hint = part.split(":", 1)
        name = name.strip()
        type_hint = type_hint.strip()
        optional = "|None" in type_hint or "Optional[" in type_hint
        base_type = type_hint.replace("|None", "").replace("Optional[", "").rstrip("]")
        out.append((name, base_type, optional))
    return out


# SQLAlchemy type and Pydantic type mapping
SA_TYPES = {
    "str": "String",
    "int": "Integer",
    "float": "Float",
    "bool": "Boolean",
    "datetime": "DateTime",
}
PYDANTIC_TYPES = {
    "str": "str",
    "int": "int",
    "float": "float",
    "bool": "bool",
    "datetime": "datetime",
}


def generate_model(name: str, class_name: str, table_name: str, fields: list) -> str:
    lines = [
        "import uuid",
        "from datetime import datetime",
        "from sqlalchemy import String, DateTime, Boolean",
        "from sqlalchemy.orm import Mapped, mapped_column",
        "from app.core.database import Base",
        "",
        "",
        f"class {class_name}(Base):",
        f'    __tablename__ = "{table_name}"',
        "",
        "    id: Mapped[str] = mapped_column(",
        '        String,',
        "        primary_key=True,",
        "        default=lambda: str(uuid.uuid4()),",
        "    )",
    ]
    for fname, ftype, optional in fields:
        sa_type = SA_TYPES.get(ftype, "String")
        nullable = "True" if optional else "False"
        type_annot = f"{ftype} | None" if optional else ftype
        lines.append(f"    {fname}: Mapped[{type_annot}] = mapped_column(")
        lines.append(f"        {sa_type},")
        lines.append(f"        nullable={nullable},")
        if ftype == "bool" and not optional:
            lines.append("        default=True,")
        lines.append("    )")
    lines.extend([
        "    is_active: Mapped[bool] = mapped_column(",
        "        Boolean,",
        "        default=True,",
        "        nullable=False,",
        "    )",
        "    created_at: Mapped[datetime] = mapped_column(",
        "        DateTime,",
        "        default=datetime.utcnow,",
        "        nullable=False,",
        "    )",
        "    updated_at: Mapped[datetime] = mapped_column(",
        "        DateTime,",
        "        default=datetime.utcnow,",
        "        onupdate=datetime.utcnow,",
        "        nullable=False,",
        "    )",
        "",
        "    def __repr__(self) -> str:",
        f'        return f"<{class_name} {{self.id}}>"',
    ])
    return "\n".join(lines)


def generate_schema(name: str, class_name: str, fields: list) -> str:
    create_fields = []
    response_fields = ["id: str"]
    for fname, ftype, optional in fields:
        py_type = PYDANTIC_TYPES.get(ftype, "str")
        opt = " | None" if optional else ""
        if optional:
            create_fields.append(f"    {fname}: {py_type}{opt} = None")
        else:
            create_fields.append(f"    {fname}: {py_type} = Field(..., min_length=1)" if ftype == "str" else f"    {fname}: {py_type} = ...")
        response_fields.append(f"{fname}: {py_type}{opt}")
    response_fields.extend([
        "is_active: bool",
        "created_at: datetime",
        "updated_at: datetime",
    ])
    create_body = "\n".join(create_fields)
    response_body = "\n".join("    " + f for f in response_fields)
    return f'''from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional


class {class_name}Create(BaseModel):
{create_body}


class {class_name}Response(BaseModel):
    model_config = ConfigDict(from_attributes=True)

{response_body}


class {class_name}ListResponse(BaseModel):
    total: int
    items: list[{class_name}Response]
'''


def generate_repository_interface(name: str, class_name: str) -> str:
    return f'''from abc import abstractmethod
from typing import Optional
from app.repositories.base_repository import BaseRepository
from app.models.{name} import {class_name}


class I{class_name}Repository(BaseRepository[{class_name}]):

    @abstractmethod
    async def get_all_active(self) -> list[{class_name}]:
        raise NotImplementedError

    @abstractmethod
    async def deactivate(self, entity_id: str) -> Optional[{class_name}]:
        raise NotImplementedError
'''


def generate_repository(name: str, class_name: str, table_name: str) -> str:
    return f'''from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from app.repositories.{name}_repository_interface import I{class_name}Repository
from app.models.{name} import {class_name}
import logging

logger = logging.getLogger(__name__)


class {class_name}Repository(I{class_name}Repository):

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, entity: {class_name}) -> {class_name}:
        self.db.add(entity)
        await self.db.commit()
        await self.db.refresh(entity)
        logger.info(f"Created {{entity.__class__.__name__}}: {{entity.id}}")
        return entity

    async def get_by_id(
        self,
        entity_id: str,
    ) -> Optional[{class_name}]:
        result = await self.db.execute(
            select({class_name}).where({class_name}.id == entity_id)
        )
        return result.scalar_one_or_none()

    async def get_all(self) -> list[{class_name}]:
        result = await self.db.execute(select({class_name}))
        return list(result.scalars().all())

    async def get_all_active(self) -> list[{class_name}]:
        result = await self.db.execute(
            select({class_name}).where({class_name}.is_active == True)  # noqa: E712
        )
        return list(result.scalars().all())

    async def update(
        self,
        entity: {class_name},
    ) -> {class_name}:
        await self.db.commit()
        await self.db.refresh(entity)
        return entity

    async def deactivate(
        self,
        entity_id: str,
    ) -> Optional[{class_name}]:
        entity = await self.get_by_id(entity_id)
        if not entity:
            return None
        entity.is_active = False
        await self.db.commit()
        await self.db.refresh(entity)
        logger.info(f"Deactivated {{entity.__class__.__name__}}: {{entity.id}}")
        return entity

    async def delete(self, entity_id: str) -> bool:
        entity = await self.get_by_id(entity_id)
        if not entity:
            return False
        await self.db.delete(entity)
        await self.db.commit()
        return True
'''


def generate_service(name: str, class_name: str, fields: list) -> str:
    first_field = fields[0][0] if fields else "name"
    create_params = ", ".join(f"data.{f[0]}" for f in fields)
    return f'''from app.repositories.{name}_repository_interface import I{class_name}Repository
from app.models.{name} import {class_name}
from app.schemas.{name} import (
    {class_name}Create,
    {class_name}Response,
    {class_name}ListResponse,
)
from fastapi import HTTPException
import logging

logger = logging.getLogger(__name__)


class {class_name}Service:

    def __init__(self, repository: I{class_name}Repository) -> None:
        self.repository = repository

    async def create(
        self,
        data: {class_name}Create,
    ) -> {class_name}Response:
        entity = {class_name}(
            {create_params},
        )
        saved = await self.repository.create(entity)
        return {class_name}Response.model_validate(saved)

    async def get_by_id(
        self,
        entity_id: str,
    ) -> {class_name}Response:
        entity = await self.repository.get_by_id(entity_id)
        if not entity:
            raise HTTPException(
                status_code=404,
                detail=f"{class_name} not found",
            )
        return {class_name}Response.model_validate(entity)

    async def get_all(self) -> {class_name}ListResponse:
        items = await self.repository.get_all_active()
        return {class_name}ListResponse(
            total=len(items),
            items=[{class_name}Response.model_validate(i) for i in items],
        )

    async def deactivate(
        self,
        entity_id: str,
    ) -> {class_name}Response:
        entity = await self.repository.deactivate(entity_id)
        if not entity:
            raise HTTPException(
                status_code=404,
                detail=f"{class_name} not found",
            )
        return {class_name}Response.model_validate(entity)
'''


def generate_router(name: str, class_name: str) -> str:
    return f'''from fastapi import APIRouter, Depends
from app.core.dependencies import get_{name}_service
from app.services.{name}_service import {class_name}Service
from app.schemas.{name} import (
    {class_name}Create,
    {class_name}Response,
    {class_name}ListResponse,
)

router = APIRouter()


@router.post(
    "/",
    response_model={class_name}Response,
    summary=f"Create {name.replace("_", " ")}",
    status_code=201,
)
async def create(
    data: {class_name}Create,
    service: {class_name}Service = Depends(get_{name}_service),
) -> {class_name}Response:
    return await service.create(data)


@router.get(
    "/",
    response_model={class_name}ListResponse,
    summary=f"List all {name.replace("_", " ")}s",
)
async def list_all(
    service: {class_name}Service = Depends(get_{name}_service),
) -> {class_name}ListResponse:
    return await service.get_all()


@router.get(
    "/{{entity_id}}",
    response_model={class_name}Response,
    summary=f"Get {name.replace("_", " ")} by ID",
)
async def get_one(
    entity_id: str,
    service: {class_name}Service = Depends(get_{name}_service),
) -> {class_name}Response:
    return await service.get_by_id(entity_id)


@router.delete(
    "/{{entity_id}}",
    response_model={class_name}Response,
    summary=f"Deactivate {name.replace("_", " ")}",
)
async def deactivate(
    entity_id: str,
    service: {class_name}Service = Depends(get_{name}_service),
) -> {class_name}Response:
    return await service.deactivate(entity_id)
'''


def _readme_resource_rows(name: str, class_name: str) -> list[str]:
    """Markdown table rows for the new resource's API endpoints."""
    human = name.replace("_", " ")
    human_plural = f"{human}s" if not human.endswith("s") else f"{human}es"
    return [
        f"| `POST` | `/api/v1/{name}/` | Create {human} |",
        f"| `GET`  | `/api/v1/{name}/` | List all {human_plural} |",
        f"| `GET`  | `/api/v1/{name}/{{id}}` | Get one {human} |",
        f"| `DELETE` | `/api/v1/{name}/{{id}}` | Deactivate {human} |",
    ]


def _update_readme(readme_path: Path, name: str, class_name: str) -> None:
    """Append new resource endpoints to the API overview table in README.md."""
    content = readme_path.read_text(encoding="utf-8")
    marker = "## API overview"
    if marker not in content:
        return
    new_rows = _readme_resource_rows(name, class_name)
    # Avoid duplicate entries
    if f"/api/v1/{name}/" in content:
        return
    lines = content.split("\n")
    # Find last table row under API overview (line like | `GET` | `/api/...` |)
    last_table_row = -1
    in_api_section = False
    for i, line in enumerate(lines):
        if marker in line:
            in_api_section = True
            continue
        if in_api_section and line.strip().startswith("|") and "|" in line[1:]:
            # Skip separator line (|---|---|)
            if re.match(r"^\|\s*[-:]+\s*\|", line.strip()):
                continue
            last_table_row = i
        elif in_api_section and line.strip() and not line.strip().startswith("|"):
            # Left the table
            break
    if last_table_row < 0:
        return
    for j, row in enumerate(new_rows):
        lines.insert(last_table_row + 1 + j, row)
    readme_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Updated: {readme_path.relative_to(PROJECT_ROOT)}")


def run(name: str, fields_str: str | None = None) -> None:
    name = name.strip().lower().replace(" ", "_")
    if not name or not re.match(r"^[a-z][a-z0-9_]*$", name):
        print("Usage: new-resource <name> [--fields 'field:type,...']")
        print("Example: new-resource product --fields 'name:str,description:str|None'")
        sys.exit(1)

    fields = parse_fields(fields_str or "name:str")
    class_name = to_pascal(name)
    table_name = to_plural_snake(name)

    # Paths
    app = PROJECT_ROOT / "app"
    (app / "models").mkdir(exist_ok=True)
    (app / "schemas").mkdir(exist_ok=True)
    (app / "repositories").mkdir(exist_ok=True)
    (app / "services").mkdir(exist_ok=True)
    (app / "api" / "v1" / "endpoints").mkdir(parents=True, exist_ok=True)

    files = [
        (app / "models" / f"{name}.py", generate_model(name, class_name, table_name, fields)),
        (app / "schemas" / f"{name}.py", generate_schema(name, class_name, fields)),
        (app / "repositories" / f"{name}_repository_interface.py", generate_repository_interface(name, class_name)),
        (app / "repositories" / f"{name}_repository.py", generate_repository(name, class_name, table_name)),
        (app / "services" / f"{name}_service.py", generate_service(name, class_name, fields)),
        (app / "api" / "v1" / "endpoints" / f"{name}.py", generate_router(name, class_name)),
    ]

    for path, content in files:
        if path.exists():
            print(f"Skip (exists): {path.relative_to(PROJECT_ROOT)}")
            continue
        path.write_text(content, encoding="utf-8")
        print(f"Created: {path.relative_to(PROJECT_ROOT)}")

    # Patch dependencies.py
    deps_path = app / "core" / "dependencies.py"
    deps = deps_path.read_text(encoding="utf-8")
    if f"get_{name}_repository" not in deps:
        new_deps = f'''

def get_{name}_repository(
    db: AsyncSession = Depends(get_db),
):
    from app.repositories.{name}_repository import {class_name}Repository
    return {class_name}Repository(db)


def get_{name}_service(
    repository: I{class_name}Repository = Depends(get_{name}_repository),
):
    from app.services.{name}_service import {class_name}Service
    return {class_name}Service(repository)
'''
        deps = deps.rstrip() + new_deps + "\n"
        # Add interface import after last repository *interface* import (top of file only)
        new_import = f"from app.repositories.{name}_repository_interface import I{class_name}Repository"
        if new_import not in deps:
            lines = deps.split("\n")
            last_idx = -1
            for i, line in enumerate(lines):
                if "repository_interface" in line and "import I" in line:
                    last_idx = i
            if last_idx >= 0:
                lines.insert(last_idx + 1, new_import)
                deps = "\n".join(lines)
        deps_path.write_text(deps, encoding="utf-8")
        print(f"Updated: {deps_path.relative_to(PROJECT_ROOT)}")

    # Patch main.py
    main_path = app / "main.py"
    main = main_path.read_text(encoding="utf-8")
    if f"from app.models import {name}" not in main:
        lines = main.split("\n")
        for i in range(len(lines) - 1, -1, -1):
            if "from app.models import" in lines[i] and "noqa" in lines[i]:
                lines.insert(i + 1, f"from app.models import {name}  # noqa: F401 - registers models")
                break
        main = "\n".join(lines)
    if f"{name}_endpoints" not in main:
        lines = main.split("\n")
        for i in range(len(lines) - 1, -1, -1):
            if "from app.api.v1.endpoints import" in lines[i]:
                lines.insert(i + 1, f"from app.api.v1.endpoints import {name} as {name}_endpoints")
                break
        main = "\n".join(lines)
    if f'prefix="/api/v1/{name}"' not in main:
        router_block = f'''
app.include_router(
    {name}_endpoints.router,
    prefix="/api/v1/{name}",
    tags=["{name}"],
)'''
        main = main.replace("\n\n@app.get", router_block + "\n\n@app.get")
    main_path.write_text(main, encoding="utf-8")
    print(f"Updated: {main_path.relative_to(PROJECT_ROOT)}")

    # Update README.md with new resource API docs
    readme_path = PROJECT_ROOT / "README.md"
    if readme_path.exists():
        _update_readme(readme_path, name, class_name)

    print("\nNext steps:")
    print(f"  1. Run: poetry run migration 'add {table_name} table'")
    print("  2. Run: poetry run migrate")
    print("  3. Adjust model/schema/repository in the new files if needed.")
