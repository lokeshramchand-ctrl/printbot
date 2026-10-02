from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from datetime import datetime
from app.database import get_db
from app.models.admin import Admin
from app.schemas.admin import LoginRequest, TokenResponse, AdminOut
from app.utils.security import verify_password, get_password_hash, create_access_token, decode_access_token
from app.config import settings

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def get_current_admin(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> Admin:
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    username = payload["sub"]
    admin = db.query(Admin).filter(Admin.username == username, Admin.is_active == True).first()
    if not admin:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return admin

@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    # Initialize default admin if no admins exist in database
    if db.query(Admin).count() == 0:
        default_admin = Admin(
            username=settings.ADMIN_DEFAULT_USERNAME,
            email="admin@printbot.local",
            password_hash=get_password_hash(settings.ADMIN_DEFAULT_PASSWORD),
            role="admin"
        )
        db.add(default_admin)
        db.commit()

    admin = db.query(Admin).filter(Admin.username == req.username).first()
    if not admin or not verify_password(req.password, admin.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")
    
    if not admin.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin account is disabled")

    admin.last_login = datetime.utcnow()
    db.commit()

    access_token = create_access_token(data={"sub": admin.username, "role": admin.role})
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        username=admin.username,
        role=admin.role
    )

@router.get("/me", response_model=AdminOut)
def get_me(current_admin: Admin = Depends(get_current_admin)):
    return current_admin
