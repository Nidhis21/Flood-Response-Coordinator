from backend.database import SessionLocal
from backend.models import AuditLog

db = SessionLocal()
logs = db.query(AuditLog).filter(AuditLog.event_type == "conflict_resolved").order_by(AuditLog.id.desc()).limit(5).all()
for l in logs:
    print(f"ID: {l.id}, Event: {l.event_type}, Agent: {l.agent_name}")
    print(f" ReqA: {l.request_a}")
    print(f" ReqB: {l.request_b}")
    print(f" Scores: {l.score_a} / {l.score_b}")
    print(f" Expl: {l.explanation}")
    print("-" * 40)
