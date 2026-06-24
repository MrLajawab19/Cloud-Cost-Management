"""
routes/accounts.py - CRUD for AWS Accounts
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import boto3
import botocore.exceptions

from database import get_db
from models.account import AWSAccount
from models.user import User
from services.security import get_current_user, encrypt_secret

router = APIRouter(prefix="/accounts", tags=["accounts"])

class AccountCreate(BaseModel):
    name: str
    access_key_id: str
    secret_access_key: str
    region: str = "us-east-1"

class AccountResponse(BaseModel):
    id: str
    name: str
    region: str
    # Do NOT return secret_key or full access_key_id in response for security
    access_key_last_4: str

@router.post("/", response_model=AccountResponse)
def create_account(account_in: AccountCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # 1. Verify credentials with AWS STS
    try:
        sts = boto3.client(
            'sts',
            aws_access_key_id=account_in.access_key_id,
            aws_secret_access_key=account_in.secret_access_key,
            region_name=account_in.region
        )
        # If this succeeds, credentials are valid
        identity = sts.get_caller_identity()
    except botocore.exceptions.ClientError as e:
        raise HTTPException(status_code=400, detail=f"Invalid AWS Credentials: {e}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"AWS connection error: {e}")

    # 2. Encrypt secret and save to DB
    encrypted_secret = encrypt_secret(account_in.secret_access_key)
    
    new_account = AWSAccount(
        user_id=current_user.id,
        name=account_in.name,
        access_key_id=account_in.access_key_id,
        encrypted_secret_key=encrypted_secret,
        region=account_in.region
    )
    db.add(new_account)
    db.commit()
    db.refresh(new_account)
    
    # Trigger collection pipeline immediately so data is ready for the frontend
    from scheduler import run_collection_pipeline
    run_collection_pipeline(user_id=current_user.id, account_id=new_account.id)
    
    return {
        "id": new_account.id,
        "name": new_account.name,
        "region": new_account.region,
        "access_key_last_4": new_account.access_key_id[-4:] if len(new_account.access_key_id) >= 4 else "****"
    }

@router.get("/", response_model=List[AccountResponse])
def list_accounts(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    accounts = db.query(AWSAccount).filter(AWSAccount.user_id == current_user.id).all()
    results = []
    for acc in accounts:
        results.append({
            "id": acc.id,
            "name": acc.name,
            "region": acc.region,
            "access_key_last_4": acc.access_key_id[-4:] if len(acc.access_key_id) >= 4 else "****"
        })
    return results

@router.delete("/{account_id}")
def delete_account(account_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    acc = db.query(AWSAccount).filter(AWSAccount.id == account_id, AWSAccount.user_id == current_user.id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    
    db.delete(acc)
    db.commit()
    return {"message": "Account deleted successfully"}

@router.post("/sync")
def sync_accounts(account_id: Optional[str] = None, current_user: User = Depends(get_current_user)):
    from scheduler import run_collection_pipeline
    run_collection_pipeline(user_id=current_user.id, account_id=account_id)
    return {"message": "Sync completed"}
