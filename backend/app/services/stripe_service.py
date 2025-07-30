import stripe
import os
from datetime import datetime
from typing import Dict, Any
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from app.models.user import User, SubscriptionStatus

load_dotenv()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

class StripeService:
    @staticmethod
    def create_or_get_customer(user: User) -> str:
        if user.stripe_customer_id:
            return user.stripe_customer_id
        
        customer = stripe.Customer.create(
            email=user.email,
            metadata={"user_id": str(user.id)}
        )
        return customer.id
    
    @staticmethod
    def create_checkout_session(customer_id: str, price_id: str, success_url: str, cancel_url: str) -> str:
        session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=['card'],
            line_items=[{
                'price': price_id,
                'quantity': 1,
            }],
            mode='subscription',
            success_url=success_url,
            cancel_url=cancel_url,
        )
        return session.url
    
    @staticmethod
    def process_webhook_event(event: Dict[str, Any], db: Session) -> bool:
        try:
            if event['type'] == 'checkout.session.completed':
                return StripeService._handle_checkout_completed(event['data']['object'], db)
            elif event['type'] == 'invoice.paid':
                return StripeService._handle_invoice_paid(event['data']['object'], db)
            elif event['type'] == 'customer.subscription.created':
                return StripeService._handle_subscription_created(event['data']['object'], db)
            elif event['type'] == 'customer.subscription.updated':
                return StripeService._handle_subscription_updated(event['data']['object'], db)
            elif event['type'] == 'customer.subscription.deleted':
                return StripeService._handle_subscription_deleted(event['data']['object'], db)
            return True
        except Exception as e:
            print(f"Error processing webhook event: {e}")
            return False
    
    @staticmethod
    def _handle_checkout_completed(session: Dict[str, Any], db: Session) -> bool:
        customer_id = session.get('customer')
        subscription_id = session.get('subscription')
        
        user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
        if user:
            user.subscription_id = subscription_id
            user.subscription_status = SubscriptionStatus.active
            db.commit()
        return True
    
    @staticmethod
    def _handle_invoice_paid(invoice: Dict[str, Any], db: Session) -> bool:
        customer_id = invoice.get('customer')
        subscription_id = invoice.get('subscription')
        
        user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
        if user:
            user.subscription_status = SubscriptionStatus.active
            if subscription_id:
                user.subscription_id = subscription_id
            db.commit()
        return True
    
    @staticmethod
    def _handle_subscription_created(subscription: Dict[str, Any], db: Session) -> bool:
        customer_id = subscription.get('customer')
        subscription_id = subscription.get('id')
        current_period_end = subscription.get('current_period_end')
        
        user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
        if user:
            user.subscription_id = subscription_id
            user.subscription_status = SubscriptionStatus.active
            if current_period_end:
                user.current_period_end = datetime.fromtimestamp(current_period_end)
            db.commit()
        return True
    
    @staticmethod
    def _handle_subscription_updated(subscription: Dict[str, Any], db: Session) -> bool:
        customer_id = subscription.get('customer')
        subscription_id = subscription.get('id')
        status = subscription.get('status')
        current_period_end = subscription.get('current_period_end')
        
        user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
        if user:
            user.subscription_id = subscription_id
            if status == 'active':
                user.subscription_status = SubscriptionStatus.active
            elif status in ['canceled', 'incomplete_expired']:
                user.subscription_status = SubscriptionStatus.canceled
            
            if current_period_end:
                user.current_period_end = datetime.fromtimestamp(current_period_end)
            db.commit()
        return True
    
    @staticmethod
    def _handle_subscription_deleted(subscription: Dict[str, Any], db: Session) -> bool:
        customer_id = subscription.get('customer')
        
        user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
        if user:
            user.subscription_status = SubscriptionStatus.canceled
            db.commit()
        return True
