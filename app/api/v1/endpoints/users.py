from typing import Any, List, Optional
from pathlib import Path
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from PIL import Image

from app.db.session import get_db
from app.core import security
from app.models.user import User
from app.models.record import Record
from app.models.user_profile_photo import UserProfilePhoto
from app.schemas.user import User as UserSchema, UserCreate, UserUpdate, UserSelfUpdate
from app.api import deps

router = APIRouter()
PROFILE_PHOTO_DIR = Path("uploads/profile_photos")
ALLOWED_PHOTO_TYPES = {"image/png": "png", "image/jpeg": "jpeg", "image/jpg": "jpeg"}
PROFILE_PHOTO_MAX_UPLOAD_BYTES = 5 * 1024 * 1024
PROFILE_PHOTO_WIDTH = 180
PROFILE_PHOTO_HEIGHT = 240


def _get_profile_photo_path(user_id: int) -> Optional[Path]:
    for extension in ("png", "jpeg"):
        candidate = PROFILE_PHOTO_DIR / f"profile_{user_id}.{extension}"
        if candidate.exists():
            return candidate
    return None


def _normalize_profile_photo(content: bytes) -> tuple[bytes, int, int]:
    try:
        image = Image.open(BytesIO(content))
    except Exception:
        raise HTTPException(status_code=400, detail="Não foi possível ler a imagem enviada.")

    image = image.convert("RGB")
    width, height = image.size
    if width <= 0 or height <= 0:
        raise HTTPException(status_code=400, detail="Imagem inválida.")

    target_ratio = PROFILE_PHOTO_WIDTH / PROFILE_PHOTO_HEIGHT  # 3:4
    current_ratio = width / height

    if current_ratio > target_ratio:
        crop_width = int(height * target_ratio)
        crop_height = height
        left = (width - crop_width) // 2
        top = 0
    else:
        crop_width = width
        crop_height = int(width / target_ratio)
        left = 0
        top = (height - crop_height) // 2

    right = left + crop_width
    bottom = top + crop_height
    cropped = image.crop((left, top, right, bottom))
    resized = cropped.resize((PROFILE_PHOTO_WIDTH, PROFILE_PHOTO_HEIGHT))

    buffer = BytesIO()
    resized.save(buffer, format="JPEG", quality=85, optimize=True)
    return buffer.getvalue(), PROFILE_PHOTO_WIDTH, PROFILE_PHOTO_HEIGHT

@router.get("/", response_model=List[UserSchema])
async def read_users(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Retrieve users. Only for Master/Admin.
    """
    result = await db.execute(select(User).offset(skip).limit(limit))
    users = result.scalars().all()
    return users

@router.post("/", response_model=UserSchema)
async def create_user(
    *,
    db: AsyncSession = Depends(get_db),
    user_in: UserCreate,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Create new user. Only for Master/Admin.
    """
    # Check if username exists
    result = await db.execute(select(User).where(User.username == user_in.username))
    existing_user = result.scalars().first()
    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="The user with this username already exists in the system.",
        )
    
    # Create User object
    user = User(
        username=user_in.username,
        full_name=user_in.full_name,
        is_active=user_in.is_active,
        is_superuser=user_in.is_superuser,
        password=security.get_password_hash(user_in.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

@router.post("/bootstrap", response_model=UserSchema, status_code=201)
async def bootstrap_first_superuser(
    *,
    db: AsyncSession = Depends(get_db),
    user_in: UserCreate,
) -> Any:
    """
    Bootstrap endpoint to create the first superuser when DB is empty.
    Must be used only once in clean environments.
    """
    users_count = await db.scalar(select(func.count(User.id)))
    if int(users_count or 0) > 0:
        raise HTTPException(status_code=409, detail="Bootstrap indisponível: já existe usuário cadastrado.")

    user = User(
        username=user_in.username,
        full_name=user_in.full_name,
        is_active=True if user_in.is_active is None else user_in.is_active,
        is_superuser=True,  # Force first user as master to guarantee admin access.
        password=security.get_password_hash(user_in.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

@router.get("/me", response_model=UserSchema)
async def read_user_me(
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Get current user.
    """
    return current_user

@router.patch("/me", response_model=UserSchema)
async def update_user_me(
    *,
    db: AsyncSession = Depends(get_db),
    user_in: UserSelfUpdate,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Update current user's profile (name/password).
    """
    update_data = user_in.model_dump(exclude_unset=True)
    if "password" in update_data:
        current_user.password = security.get_password_hash(update_data.pop("password"))
    if "full_name" in update_data:
        current_user.full_name = update_data["full_name"]

    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    return current_user

@router.post("/me/photo")
async def upload_user_photo(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
    file: UploadFile = File(...),
) -> Any:
    """
    Upload current user's profile photo.
    """
    if not file.content_type or file.content_type not in ALLOWED_PHOTO_TYPES:
        raise HTTPException(status_code=400, detail="Formato de imagem inválido.")

    payload = await file.read()
    await file.close()

    if not payload:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")
    if len(payload) > PROFILE_PHOTO_MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Imagem excede o tamanho máximo permitido (5 MB).")

    normalized_blob, width, height = _normalize_profile_photo(payload)

    existing = await db.execute(
        select(UserProfilePhoto).where(UserProfilePhoto.user_id == current_user.id)
    )
    profile_photo = existing.scalars().first()
    if profile_photo is None:
        profile_photo = UserProfilePhoto(
            user_id=current_user.id,
            content_type="image/jpeg",
            image_blob=normalized_blob,
            width=width,
            height=height,
        )
    else:
        profile_photo.content_type = "image/jpeg"
        profile_photo.image_blob = normalized_blob
        profile_photo.width = width
        profile_photo.height = height

    db.add(profile_photo)
    await db.commit()

    # Legacy cleanup (filesystem storage from previous versions).
    for ext in ("png", "jpeg"):
        previous = PROFILE_PHOTO_DIR / f"profile_{current_user.id}.{ext}"
        if previous.exists():
            previous.unlink()

    return {"filename": f"profile_{current_user.id}.jpeg"}

@router.get("/{user_id}/photo")
async def read_user_photo(
    *,
    db: AsyncSession = Depends(get_db),
    user_id: int,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Return the user's profile photo.
    """
    if not current_user.is_superuser and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    db_result = await db.execute(
        select(UserProfilePhoto).where(UserProfilePhoto.user_id == user_id)
    )
    profile_photo = db_result.scalars().first()
    if profile_photo:
        return Response(content=profile_photo.image_blob, media_type=profile_photo.content_type)

    photo_path = _get_profile_photo_path(user_id)
    if not photo_path:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    media_type = "image/png" if photo_path.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(photo_path, media_type=media_type)


@router.delete("/me/photo")
async def delete_user_photo(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    result = await db.execute(
        select(UserProfilePhoto).where(UserProfilePhoto.user_id == current_user.id)
    )
    profile_photo = result.scalars().first()
    removed = False
    if profile_photo is not None:
        await db.delete(profile_photo)
        removed = True
    await db.commit()

    # Legacy cleanup (filesystem storage from previous versions).
    for ext in ("png", "jpeg"):
        previous = PROFILE_PHOTO_DIR / f"profile_{current_user.id}.{ext}"
        if previous.exists():
            previous.unlink()
            removed = True

    return {"removed": removed}

@router.patch("/{user_id}", response_model=UserSchema)
async def update_user(
    *,
    db: AsyncSession = Depends(get_db),
    user_id: int,
    user_in: UserUpdate,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Update a user. Only for Master/Admin.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    update_data = user_in.model_dump(exclude_unset=True)
    if update_data.get("is_active") is False and user.is_active:
        record_ref = await db.execute(
            select(Record.id).where(Record.owner_id == user_id).limit(1)
        )
        if record_ref.scalar() is not None:
            raise HTTPException(status_code=400, detail="Usuário em uso, não pode desativar.")
    if "password" in update_data:
        user.password = security.get_password_hash(update_data.pop("password"))
        
    for field, value in update_data.items():
        setattr(user, field, value)
        
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

@router.delete("/{user_id}", response_model=UserSchema)
async def delete_user(
    *,
    db: AsyncSession = Depends(get_db),
    user_id: int,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Delete a user. Only for Master/Admin.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    record_ref = await db.execute(
        select(Record.id).where(Record.owner_id == user_id).limit(1)
    )
    if record_ref.scalar() is not None:
        raise HTTPException(status_code=400, detail="Usuário em uso, desative.")

    await db.delete(user)
    await db.commit()
    return user
