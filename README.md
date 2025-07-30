# Bespin - Stripe Subscription System

A complete subscription management system built with FastAPI and React, featuring Stripe integration for payment processing.

## Features

- User authentication with JWT tokens
- Stripe subscription management
- Webhook handling for subscription events
- React frontend with shadcn/ui components
- Real-time subscription status updates

## Backend Setup

1. Navigate to the backend directory:
   ```bash
   cd backend
   ```

2. Install dependencies:
   ```bash
   poetry install
   ```

3. Set up environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your Stripe keys
   ```

4. Run the development server:
   ```bash
   poetry run fastapi dev app/main.py
   ```

## Frontend Setup

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Set up environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your API URL and Stripe publishable key
   ```

4. Run the development server:
   ```bash
   npm run dev
   ```

## API Endpoints

- `POST /api/auth/register` - User registration
- `POST /api/auth/login` - User login
- `GET /api/auth/me` - Get current user info
- `POST /api/subscribe` - Create subscription checkout session
- `GET /api/subscription/status` - Get subscription status
- `POST /api/stripe/webhook` - Stripe webhook handler

## Environment Variables

### Backend (.env)
```
SECRET_KEY=your-jwt-secret-key
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
```

### Frontend (.env)
```
VITE_API_URL=http://localhost:8000
VITE_STRIPE_PUBLISHABLE_KEY=pk_test_...
```

## Testing

1. Start both backend and frontend servers
2. Register a new user account
3. Navigate to subscription page
4. Test the complete checkout flow
5. Verify webhook processing with Stripe CLI

## Stripe Webhook Events

The system handles these Stripe webhook events:
- `checkout.session.completed`
- `invoice.paid`
- `customer.subscription.created`
- `customer.subscription.updated`
- `customer.subscription.deleted`

## Database Schema

The User model includes these subscription-related fields:
- `stripe_customer_id` - Stripe customer ID
- `subscription_status` - Current subscription status (active/canceled/expired)
- `subscription_id` - Stripe subscription ID
- `current_period_end` - End date of current billing period

## Development
This project uses pre-commit hooks for code quality. To set up:
```bash
pip install pre-commit
pre-commit install
```
