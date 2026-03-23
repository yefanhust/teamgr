import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.team import Team, TeamMember
from app.models.talent import Talent
from app.models.project import Project, ProjectMember
from app.middleware.auth_middleware import require_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/teams", tags=["teams"])


class TeamCreate(BaseModel):
    name: str


class TeamUpdate(BaseModel):
    name: Optional[str] = None
    position_x: Optional[float] = None
    position_y: Optional[float] = None


class AddMemberBody(BaseModel):
    talent_id: int


class SetLeaderBody(BaseModel):
    talent_id: int


class UpdateTitleBody(BaseModel):
    position_title: str


def _team_to_response(team: Team) -> dict:
    return {
        "id": team.id,
        "name": team.name,
        "position_x": team.position_x,
        "position_y": team.position_y,
        "created_at": team.created_at.isoformat() if team.created_at else "",
        "updated_at": team.updated_at.isoformat() if team.updated_at else "",
        "members": [
            {
                "id": m.id,
                "talent_id": m.talent_id,
                "name": m.talent.name if m.talent else "",
                "avatar_url": (m.talent.card_data or {}).get("avatar_url", "") if m.talent else "",
                "is_leader": m.is_leader,
                "position_title": m.position_title or "",
                "joined_at": m.joined_at.isoformat() if m.joined_at else "",
            }
            for m in team.members
        ],
    }


@router.get("/project-view")
async def get_project_view(
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    """Get team-project-member relationship data for the project tab."""
    teams = db.query(Team).order_by(Team.created_at).all()
    result = []
    for team in teams:
        team_data = {
            "id": team.id,
            "name": team.name,
            "members": [],
            "projects": [],
        }
        talent_ids = [m.talent_id for m in team.members]
        project_ids_set = set()
        talent_project_map = {}
        if talent_ids:
            pm_rows = db.query(ProjectMember).filter(
                ProjectMember.talent_id.in_(talent_ids)
            ).all()
            for pm in pm_rows:
                project_ids_set.add(pm.project_id)
                talent_project_map.setdefault(pm.talent_id, []).append(pm.project_id)

        if project_ids_set:
            projects = db.query(Project).filter(Project.id.in_(project_ids_set)).all()
            for p in projects:
                team_data["projects"].append({
                    "id": p.id,
                    "name": p.name,
                    "status": p.status,
                })

        for m in team.members:
            member_projects = talent_project_map.get(m.talent_id, [])
            team_data["members"].append({
                "talent_id": m.talent_id,
                "name": m.talent.name if m.talent else "",
                "avatar_url": (m.talent.card_data or {}).get("avatar_url", "") if m.talent else "",
                "is_leader": m.is_leader,
                "project_ids": member_projects,
                "project_count": len(member_projects),
            })

        result.append(team_data)
    return result


@router.get("")
async def list_teams(
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    teams = db.query(Team).order_by(Team.created_at).all()
    return [_team_to_response(t) for t in teams]


@router.post("")
async def create_team(
    body: TeamCreate,
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    team = Team(name=body.name)
    db.add(team)
    db.commit()
    db.refresh(team)
    return _team_to_response(team)


@router.put("/{team_id}")
async def update_team(
    team_id: int,
    body: TeamUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="团队不存在")
    if body.name is not None:
        team.name = body.name
    if body.position_x is not None:
        team.position_x = body.position_x
    if body.position_y is not None:
        team.position_y = body.position_y
    db.commit()
    db.refresh(team)
    return _team_to_response(team)


@router.delete("/{team_id}")
async def delete_team(
    team_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="团队不存在")
    db.delete(team)
    db.commit()
    return {"ok": True}


@router.post("/{team_id}/members")
async def add_member(
    team_id: int,
    body: AddMemberBody,
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="团队不存在")
    talent = db.query(Talent).filter(Talent.id == body.talent_id).first()
    if not talent:
        raise HTTPException(status_code=404, detail="人才不存在")
    # Check if already a member
    existing = db.query(TeamMember).filter(
        TeamMember.team_id == team_id,
        TeamMember.talent_id == body.talent_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="该成员已在团队中")
    member = TeamMember(team_id=team_id, talent_id=body.talent_id)
    db.add(member)
    db.commit()
    db.refresh(team)
    return _team_to_response(team)


@router.delete("/{team_id}/members/{talent_id}")
async def remove_member(
    team_id: int,
    talent_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    member = db.query(TeamMember).filter(
        TeamMember.team_id == team_id,
        TeamMember.talent_id == talent_id,
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="成员不在该团队中")
    db.delete(member)
    db.commit()
    team = db.query(Team).filter(Team.id == team_id).first()
    return _team_to_response(team)


@router.put("/{team_id}/leader")
async def set_leader(
    team_id: int,
    body: SetLeaderBody,
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="团队不存在")
    # Clear existing leaders
    for m in team.members:
        m.is_leader = False
    # Set new leader
    member = db.query(TeamMember).filter(
        TeamMember.team_id == team_id,
        TeamMember.talent_id == body.talent_id,
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="该成员不在团队中")
    member.is_leader = True
    db.commit()
    db.refresh(team)
    return _team_to_response(team)


@router.put("/{team_id}/members/{talent_id}/title")
async def update_member_title(
    team_id: int,
    talent_id: int,
    body: UpdateTitleBody,
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    member = db.query(TeamMember).filter(
        TeamMember.team_id == team_id,
        TeamMember.talent_id == talent_id,
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="成员不在该团队中")
    member.position_title = body.position_title
    db.commit()
    db.refresh(member)
    team = db.query(Team).filter(Team.id == team_id).first()
    return _team_to_response(team)
