from sqlalchemy.orm import Session
from database import SessionLocal
from models.user import User
from models.account import AWSAccount
from services.security import create_access_token
import uuid

def main():
    db = SessionLocal()
    account = db.query(AWSAccount).first()
    user = db.query(User).filter(User.id == account.user_id).first()
    
    t1 = create_access_token({"sub": str(user.id)})
    fake_id = str(uuid.uuid4())
    print(f"{t1}|{fake_id}")

if __name__ == '__main__':
    main()
