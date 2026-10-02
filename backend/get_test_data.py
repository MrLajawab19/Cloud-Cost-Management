from sqlalchemy.orm import Session
from database import SessionLocal
from models.user import User
from models.account import AWSAccount
from models.cost_record import Recommendation
from services.security import create_access_token
import uuid

def main():
    db = SessionLocal()
    account = db.query(AWSAccount).first()
    user = db.query(User).filter(User.id == account.user_id).first()
    
    rec = db.query(Recommendation).filter(Recommendation.account_id == account.id).first()
    if not rec:
        rec = Recommendation(
            account_id=account.id,
            resource_id="i-dummy2",
            resource_name="Dummy Instance 2",
            service_type="EC2",
            region="us-east-1",
            issue="Underutilized",
            description="dummy desc",
            action="dummy action",
            potential_savings_usd=25.0,
            severity="low"
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)

    user2 = db.query(User).filter(User.id != account.user_id).first()
    
    t1 = create_access_token({"sub": str(user.id)})
    t2 = create_access_token({"sub": str(user2.id)})
    
    print(f"{t1}|{t2}|{rec.id}")

if __name__ == '__main__':
    main()
