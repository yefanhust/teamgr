from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.talent import LLMUsageLog
from app.middleware.auth_middleware import require_auth

router = APIRouter(prefix="/api/stats", tags=["stats"], dependencies=[Depends(require_auth)])


@router.get("/llm-logs")
def get_llm_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Return paginated LLM usage logs, newest first."""
    total = db.query(func.count(LLMUsageLog.id)).scalar()
    logs = (
        db.query(LLMUsageLog)
        .order_by(LLMUsageLog.timestamp.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": log.id,
                "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                "model_name": log.model_name,
                "call_type": log.call_type,
                "duration_ms": log.duration_ms,
                "input_tokens": log.input_tokens,
                "output_tokens": log.output_tokens,
            }
            for log in logs
        ],
    }


@router.get("/llm-summary")
def get_llm_summary(db: Session = Depends(get_db)):
    """Return aggregated stats grouped by model_name."""
    rows = (
        db.query(
            LLMUsageLog.model_name,
            func.count(LLMUsageLog.id).label("call_count"),
            func.avg(LLMUsageLog.duration_ms).label("avg_duration_ms"),
            func.avg(LLMUsageLog.input_tokens).label("avg_input_tokens"),
            func.avg(LLMUsageLog.output_tokens).label("avg_output_tokens"),
            func.sum(LLMUsageLog.input_tokens).label("total_input_tokens"),
            func.sum(LLMUsageLog.output_tokens).label("total_output_tokens"),
        )
        .group_by(LLMUsageLog.model_name)
        .all()
    )
    return [
        {
            "model_name": row.model_name,
            "call_count": row.call_count,
            "avg_duration_ms": round(row.avg_duration_ms or 0),
            "avg_input_tokens": round(row.avg_input_tokens or 0),
            "avg_output_tokens": round(row.avg_output_tokens or 0),
            "total_input_tokens": row.total_input_tokens or 0,
            "total_output_tokens": row.total_output_tokens or 0,
        }
        for row in rows
    ]
