import React, { useState } from 'react';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { LoginForm } from './components/auth/LoginForm';
import { RegisterForm } from './components/auth/RegisterForm';
import { UserDashboard } from './components/dashboard/UserDashboard';
import { SubscribePage } from './pages/SubscribePage';
import { SuccessPage } from './pages/SuccessPage';
import { CancelPage } from './pages/CancelPage';
import { Button } from './components/ui/button';
import './App.css';

type Page = 'login' | 'register' | 'dashboard' | 'subscribe' | 'success' | 'cancel';

function AppContent() {
  const { user, loading } = useAuth();
  const [currentPage, setCurrentPage] = useState<Page>('login');

  React.useEffect(() => {
    const path = window.location.pathname;
    if (path === '/success') {
      setCurrentPage('success');
    } else if (path === '/cancel') {
      setCurrentPage('cancel');
    } else if (path === '/subscribe') {
      setCurrentPage('subscribe');
    } else if (user) {
      setCurrentPage('dashboard');
    } else {
      setCurrentPage('login');
    }
  }, [user]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900 mx-auto mb-4"></div>
          <p>Loading...</p>
        </div>
      </div>
    );
  }

  if (currentPage === 'success') {
    return <SuccessPage />;
  }

  if (currentPage === 'cancel') {
    return <CancelPage />;
  }

  if (!user) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="w-full max-w-md">
          {currentPage === 'register' ? (
            <RegisterForm onSwitchToLogin={() => setCurrentPage('login')} />
          ) : (
            <LoginForm onSwitchToRegister={() => setCurrentPage('register')} />
          )}
        </div>
      </div>
    );
  }

  if (currentPage === 'subscribe') {
    return (
      <div className="min-h-screen bg-gray-50">
        <nav className="bg-white shadow-sm border-b">
          <div className="container mx-auto px-6 py-4 flex justify-between items-center">
            <h1 className="text-xl font-semibold">Bespin</h1>
            <Button variant="outline" onClick={() => setCurrentPage('dashboard')}>
              Back to Dashboard
            </Button>
          </div>
        </nav>
        <SubscribePage />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white shadow-sm border-b">
        <div className="container mx-auto px-6 py-4 flex justify-between items-center">
          <h1 className="text-xl font-semibold">Bespin</h1>
          <Button variant="outline" onClick={() => setCurrentPage('subscribe')}>
            Subscribe
          </Button>
        </div>
      </nav>
      <UserDashboard />
    </div>
  );
}

function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}

export default App;
