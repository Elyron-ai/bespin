import { SubscriptionPlans } from '@/components/subscription/SubscriptionPlans';

export function SubscribePage() {
  return (
    <div className="container mx-auto p-6">
      <div className="text-center mb-8">
        <h1 className="text-3xl font-bold mb-4">Choose Your Plan</h1>
        <p className="text-muted-foreground">
          Select a subscription plan to get started with premium features
        </p>
      </div>
      <SubscriptionPlans />
    </div>
  );
}
