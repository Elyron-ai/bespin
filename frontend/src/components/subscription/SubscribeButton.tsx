import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { apiClient } from '@/lib/api';

interface SubscribeButtonProps {
  priceId: string;
  planName: string;
}

export function SubscribeButton({ priceId, planName }: SubscribeButtonProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubscribe = async () => {
    setIsLoading(true);
    setError(null);
    
    try {
      const successUrl = `${window.location.origin}/success`;
      const cancelUrl = `${window.location.origin}/cancel`;
      
      const response = await apiClient.createSubscription(priceId, successUrl, cancelUrl);
      
      window.location.href = response.checkout_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create subscription');
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-2">
      <Button 
        onClick={handleSubscribe} 
        disabled={isLoading}
        className="w-full"
        size="lg"
      >
        {isLoading ? 'Creating checkout...' : `Subscribe to ${planName}`}
      </Button>
      {error && <div className="text-red-500 text-sm">{error}</div>}
    </div>
  );
}
