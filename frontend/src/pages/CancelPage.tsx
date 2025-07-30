import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { XCircle } from 'lucide-react';

export function CancelPage() {
  return (
    <div className="container mx-auto p-6 flex items-center justify-center min-h-screen">
      <Card className="w-full max-w-md text-center">
        <CardHeader>
          <div className="mx-auto mb-4">
            <XCircle className="h-16 w-16 text-red-500" />
          </div>
          <CardTitle className="text-2xl">Subscription Cancelled</CardTitle>
          <CardDescription>
            Your subscription process was cancelled. No payment has been made.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            You can try again anytime. If you have any questions, please contact our support team.
          </p>
          <div className="space-y-2">
            <Button 
              onClick={() => window.location.href = '/subscribe'} 
              className="w-full"
            >
              Try Again
            </Button>
            <Button 
              variant="outline" 
              onClick={() => window.location.href = '/'} 
              className="w-full"
            >
              Back to Home
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
