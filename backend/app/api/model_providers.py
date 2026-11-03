"""Administrator-only model provider configuration and connection checks."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_permission
from app.schemas.model_provider import ModelProviderCreate, ModelProviderOut, ModelProviderProbe, ModelProviderUpdate
from app.services import model_provider_service as service


class SafeValidationRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request):
            try:
                return await original(request)
            except RequestValidationError as error:
                # Input values can contain API keys or secret headers.
                raise HTTPException(422, detail=[{key: item[key] for key in ("loc", "msg", "type")} for item in error.errors()]) from None
            except ValidationError as error:
                raise HTTPException(422, detail=[{key: item[key] for key in ("loc", "msg", "type")} for item in error.errors()]) from None
            except service.ProviderError as error:
                raise HTTPException(error.status_code, detail=str(error)) from None

        return handler


router = APIRouter(prefix="/model-providers", tags=["Model Providers"], route_class=SafeValidationRoute,
                   dependencies=[Depends(require_permission("system.model_manage"))])


@router.get("/catalog")
async def catalog():
    return service.CATALOG


@router.get("", response_model=list[ModelProviderOut])
async def list_providers(db: AsyncSession = Depends(get_db)):
    return await service.list_providers(db)


@router.post("", response_model=ModelProviderOut, status_code=201)
async def create_provider(data: ModelProviderCreate, db: AsyncSession = Depends(get_db)):
    return await service.create_provider(db, data)


@router.post("/models")
async def discover_models(data: ModelProviderProbe, db: AsyncSession = Depends(get_db)):
    return await service.discover_models(db, data)


@router.post("/test")
async def test_connection(data: ModelProviderProbe, db: AsyncSession = Depends(get_db)):
    return await service.test_connection(db, data)


@router.patch("/{provider_id}", response_model=ModelProviderOut)
async def update_provider(provider_id: uuid.UUID, data: ModelProviderUpdate, db: AsyncSession = Depends(get_db)):
    return await service.update_provider(db, provider_id, data)


@router.delete("/{provider_id}", status_code=204)
async def delete_provider(provider_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await service.delete_provider(db, provider_id)
