import { useEffect, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { apiClient } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';
import { Calendar, CreditCard } from 'lucide-react';

interface SubscriptionData {
  subscription_status: string | null;
  subscription_id: string | null;
  current_period_end: string | null;
}

export function SubscriptionStatus() {
  const [subscription, setSubscription] = useState<SubscriptionData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { refreshUser } = useAuth();

  const fetchSubscriptionStatus = async () => {
    try {
      const data = await apiClient.getSubscriptionStatus();
      setSubscription(data);
      await refreshUser();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch subscription status');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSubscriptionStatus();
  }, []);

  if (loading) {
    return (
      <Card>
        <CardContent className="p-6">
          <div className="text-center">Loading subscription status...</div>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardContent className="p-6">
          <div className="text-center text-red-500">{error}</div>
          <Button onClick={fetchSubscriptionStatus} className="mt-4 w-full">
            Retry
          </Button>
        </CardContent>
      </Card>
    );
  }

  const getStatusColor = (status: string | null) => {
    switch (status) {
      case 'active':
        return 'bg-green-500 text-white';
      case 'canceled':
        return 'bg-red-500 text-white';
      case 'expired':
        return 'bg-gray-500 text-white';
      default:
        return 'bg-gray-400 text-white';
    }
  };

  const formatDate = (dateString: string | null) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleDateString();
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <CreditCard className="h-5 w-5" />
          Subscription Status
        </CardTitle>
        <CardDescription>Manage your subscription and billing</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium">Status:</span>
          <Badge className={getStatusColor(subscription?.subscription_status || null)}>
            {subscription?.subscription_status || 'No subscription'}
          </Badge>
        </div>
        
        {subscription?.subscription_id && (
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">Subscription ID:</span>
            <span className="text-sm text-muted-foreground font-mono">
              {subscription.subscription_id.slice(0, 20)}...
            </span>
          </div>
        )}
        
        {subscription?.current_period_end && (
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium flex items-center gap-1">
              <Calendar className="h-4 w-4" />
              Next billing date:
            </span>
            <span className="text-sm">{formatDate(subscription.current_period_end)}</span>
          </div>
        )}
        
        {!subscription?.subscription_status && (
          <div className="text-center py-4">
            <p className="text-muted-foreground mb-4">You don't have an active subscription</p>
            <Button onClick={() => window.location.href = '/subscribe'}>
              Choose a Plan
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
