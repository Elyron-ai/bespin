import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { SubscriptionStatus } from '@/components/subscription/SubscriptionStatus';
import { useAuth } from '@/contexts/AuthContext';
import { User, LogOut } from 'lucide-react';

export function UserDashboard() {
  const { user, logout } = useAuth();

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Dashboard</h1>
        <Button variant="outline" onClick={logout}>
          <LogOut className="h-4 w-4 mr-2" />
          Sign Out
        </Button>
      </div>
      
      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <User className="h-5 w-5" />
              Account Information
            </CardTitle>
            <CardDescription>Your account details</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">Email:</span>
                <span className="text-sm">{user?.email}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">User ID:</span>
                <span className="text-sm text-muted-foreground">#{user?.id}</span>
              </div>
            </div>
          </CardContent>
        </Card>
        
        <SubscriptionStatus />
      </div>
    </div>
  );
}
