import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_scope
from app.database import get_db
from app.models import CatalystIntakeStatus, CatalystIntakeSubmission, User
from app.schemas import CatalystIntakeAccepted, CatalystIntakeCreate

router = APIRouter(prefix="/api/catalyst-intake", tags=["catalyst-intake"])


@router.post("", response_model=CatalystIntakeAccepted, status_code=status.HTTP_202_ACCEPTED)
async def accept_catalyst_intake(
    data: CatalystIntakeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_scope("catalyst_intake:write")),
) -> CatalystIntakeAccepted:
    submission = CatalystIntakeSubmission(
        id=uuid.uuid4(),
        path=data.path,
        name=data.name,
        email=str(data.email),
        company=data.company,
        expected_nodes_sites=data.expected_nodes_sites,
        timeline=data.timeline,
        notes=data.notes,
        status=CatalystIntakeStatus.PENDING,
        created_by=current_user.id,
    )
    db.add(submission)
    await db.commit()
    await db.refresh(submission)
    return CatalystIntakeAccepted(id=submission.id)
