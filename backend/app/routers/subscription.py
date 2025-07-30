from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import stripe
import os
from dotenv import load_dotenv
from app.database import get_db
from app.models.user import User
from app.core.auth import get_current_user
from app.services.stripe_service import StripeService

load_dotenv()

router = APIRouter(prefix="/api", tags=["subscription"])

class SubscribeRequest(BaseModel):
    price_id: str = "price_1234567890"
    success_url: str = "http://localhost:5173/success"
    cancel_url: str = "http://localhost:5173/cancel"

class SubscriptionStatusResponse(BaseModel):
    subscription_status: Optional[str] = None
    subscription_id: Optional[str] = None
    current_period_end: Optional[str] = None

@router.post("/subscribe")
def create_subscription(
    request: SubscribeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        customer_id = StripeService.create_or_get_customer(current_user)
        
        if not current_user.stripe_customer_id:
            current_user.stripe_customer_id = customer_id
            db.commit()
        
        checkout_url = StripeService.create_checkout_session(
            customer_id=customer_id,
            price_id=request.price_id,
            success_url=request.success_url,
            cancel_url=request.cancel_url
        )
        
        return {"checkout_url": checkout_url}
    
    except stripe.error.StripeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Stripe error: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )

@router.get("/subscription/status", response_model=SubscriptionStatusResponse)
def get_subscription_status(current_user: User = Depends(get_current_user)):
    return {
        "subscription_status": current_user.subscription_status.value if current_user.subscription_status else None,
        "subscription_id": current_user.subscription_id,
        "current_period_end": current_user.current_period_end.isoformat() if current_user.current_period_end else None
    }

@router.post("/stripe/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')
    webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET')
    
    if not webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook secret not configured"
        )
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payload"
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid signature"
        )
    
    success = StripeService.process_webhook_event(event, db)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process webhook event"
        )
    
    return {"status": "success"}
