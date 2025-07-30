import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { SubscribeButton } from './SubscribeButton';
import { Check } from 'lucide-react';

const plans = [
  {
    id: 'basic',
    name: 'Basic Plan',
    price: '$20',
    period: 'month',
    priceId: 'price_1234567890',
    features: [
      'Access to all features',
      'Priority support',
      'Monthly updates',
      'Cancel anytime',
    ],
  },
];

export function SubscriptionPlans() {
  return (
    <div className="grid gap-6 md:grid-cols-1 lg:grid-cols-1 max-w-md mx-auto">
      {plans.map((plan) => (
        <Card key={plan.id} className="relative">
          <CardHeader>
            <CardTitle className="text-2xl">{plan.name}</CardTitle>
            <CardDescription>
              <span className="text-3xl font-bold">{plan.price}</span>
              <span className="text-muted-foreground">/{plan.period}</span>
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <ul className="space-y-2">
              {plan.features.map((feature, index) => (
                <li key={index} className="flex items-center gap-2">
                  <Check className="h-4 w-4 text-green-500" />
                  <span className="text-sm">{feature}</span>
                </li>
              ))}
            </ul>
            <SubscribeButton priceId={plan.priceId} planName={plan.name} />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
