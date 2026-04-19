from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from api.routes.webhook import get_review_service
from services.review_service import ReviewService

router = APIRouter(tags=["reviews"])


@router.get("/reviews/{pr_number}")
async def get_review(
	pr_number: int,
	repo_full_name: str = Query(..., min_length=3),
	review_service: ReviewService = Depends(get_review_service),
) -> dict[str, Any]:
	result = await review_service.get_latest_review(repo_full_name, pr_number)
	if not result:
		raise HTTPException(status_code=404, detail="Review not found")
	return result
