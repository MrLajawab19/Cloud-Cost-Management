"""
routes/accounts.py - CRUD for AWS and Azure Accounts
"""

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import boto3
import botocore.exceptions

from database import get_db
from models.account import CloudAccount
from models.user import User
from services.security import get_current_user, encrypt_secret
from config import get_settings

router = APIRouter(prefix="/accounts", tags=["accounts"])

class AccountCreate(BaseModel):
    name: str
    provider: str = "aws"
    region: str = "us-east-1"
    # AWS fields
    access_key_id: Optional[str] = None
    secret_access_key: Optional[str] = None
    # Azure fields
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    subscription_id: Optional[str] = None

class AccountResponse(BaseModel):
    id: str
    name: str
    region: str
    access_key_last_4: str

@router.post("/", response_model=AccountResponse)
def create_account(account_in: AccountCreate, background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    settings = get_settings()
    
    if account_in.provider == "aws":
        if not account_in.access_key_id or not account_in.secret_access_key:
            raise HTTPException(status_code=400, detail="Missing AWS credentials")
        if not settings.demo_mode:
            try:
                sts = boto3.client(
                    'sts',
                    aws_access_key_id=account_in.access_key_id,
                    aws_secret_access_key=account_in.secret_access_key,
                    region_name=account_in.region
                )
                identity = sts.get_caller_identity()
            except botocore.exceptions.ClientError as e:
                raise HTTPException(status_code=400, detail=f"Invalid AWS Credentials: {e}")
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"AWS connection error: {e}")

        encrypted_secret = "" if settings.demo_mode else encrypt_secret(account_in.secret_access_key)
        new_account = CloudAccount(
            user_id=current_user.id,
            name=account_in.name,
            provider="aws",
            access_key_id=account_in.access_key_id,
            encrypted_secret_key=encrypted_secret,
            region=account_in.region
        )
    elif account_in.provider == "azure":
        if not account_in.tenant_id or not account_in.client_id or not account_in.client_secret or not account_in.subscription_id:
            raise HTTPException(status_code=400, detail="Missing Azure credentials")
        
        if not settings.demo_mode:
            try:
                from azure.identity import ClientSecretCredential
                from azure.mgmt.resource import SubscriptionClient
                credential = ClientSecretCredential(account_in.tenant_id, account_in.client_id, account_in.client_secret)
                sub_client = SubscriptionClient(credential, subscription_id=account_in.subscription_id)
                # Verify subscription exists
                sub = sub_client.subscriptions.get(account_in.subscription_id)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid Azure Credentials: {e}")
                
        encrypted_secret = "" if settings.demo_mode else encrypt_secret(account_in.client_secret)
        new_account = CloudAccount(
            user_id=current_user.id,
            name=account_in.name,
            provider="azure",
            tenant_id=account_in.tenant_id,
            client_id=account_in.client_id,
            encrypted_client_secret=encrypted_secret,
            subscription_id=account_in.subscription_id,
            region=account_in.region,
            access_key_id="N/A",
            encrypted_secret_key=""
        )
    else:
        raise HTTPException(status_code=400, detail="Unsupported provider")

    db.add(new_account)
    db.commit()
    db.refresh(new_account)
    
    from scheduler import run_collection_pipeline
    background_tasks.add_task(run_collection_pipeline, user_id=current_user.id, account_id=new_account.id)
    
    if new_account.provider == "aws" and new_account.access_key_id:
        last_4 = new_account.access_key_id[-4:] if len(new_account.access_key_id) >= 4 else "****"
    elif new_account.provider == "azure" and new_account.client_id:
        last_4 = new_account.client_id[-4:] if len(new_account.client_id) >= 4 else "****"
    else:
        last_4 = "****"
        
    return {
        "id": new_account.id,
        "name": new_account.name,
        "region": new_account.region,
        "access_key_last_4": last_4
    }

@router.get("/", response_model=List[AccountResponse])
def list_accounts(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    accounts = db.query(CloudAccount).filter(CloudAccount.user_id == current_user.id).all()
    results = []
    for acc in accounts:
        if acc.provider == "aws" and acc.access_key_id:
            last_4 = acc.access_key_id[-4:] if len(acc.access_key_id) >= 4 else "****"
        elif acc.provider == "azure" and acc.client_id:
            last_4 = acc.client_id[-4:] if len(acc.client_id) >= 4 else "****"
        else:
            last_4 = "****"
        results.append({
            "id": acc.id,
            "name": acc.name,
            "region": acc.region,
            "access_key_last_4": last_4
        })
    return results

@router.delete("/{account_id}")
def delete_account(account_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    acc = db.query(CloudAccount).filter(CloudAccount.id == account_id, CloudAccount.user_id == current_user.id).first()
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
