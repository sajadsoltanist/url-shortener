from fastapi import APIRouter, Request, Depends
from sqlmodel import Session

from db.session import get_session

router = APIRouter()


@router.post("/shorten")
def create_short_url(original_url: str, session: Session = Depends(get_session)):
    pass


@router.get("/{short_code}")
def redirect_to_url(short_code: str, request: Request, session: Session = Depends(get_session)):
    pass


@router.get("/stats/{short_code}")
def get_url_stats(short_code: str, session: Session = Depends(get_session)):
    pass
