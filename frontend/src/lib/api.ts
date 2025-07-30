const API_BASE_URL = (import.meta.env as ImportMetaEnv).VITE_API_URL || 'http://localhost:8000';

class ApiClient {
  private baseURL: string;
  private token: string | null = null;

  constructor(baseURL: string) {
    this.baseURL = baseURL;
    this.token = localStorage.getItem('access_token');
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.baseURL}${endpoint}`;
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

    if (this.token) {
      (headers as Record<string, string>).Authorization = `Bearer ${this.token}`;
    }

    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  setToken(token: string) {
    this.token = token;
    localStorage.setItem('access_token', token);
  }

  clearToken() {
    this.token = null;
    localStorage.removeItem('access_token');
  }

  async register(email: string, password: string) {
    const response = await this.request<{ access_token: string; token_type: string }>('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    this.setToken(response.access_token);
    return response;
  }

  async login(email: string, password: string) {
    const response = await this.request<{ access_token: string; token_type: string }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    this.setToken(response.access_token);
    return response;
  }

  async getCurrentUser() {
    return this.request<{
      id: number;
      email: string;
      subscription_status: string | null;
      current_period_end: string | null;
    }>('/api/auth/me');
  }

  async createSubscription(priceId: string, successUrl: string, cancelUrl: string) {
    return this.request<{ checkout_url: string }>('/api/subscribe', {
      method: 'POST',
      body: JSON.stringify({
        price_id: priceId,
        success_url: successUrl,
        cancel_url: cancelUrl,
      }),
    });
  }

  async getSubscriptionStatus() {
    return this.request<{
      subscription_status: string | null;
      subscription_id: string | null;
      current_period_end: string | null;
    }>('/api/subscription/status');
  }
}

export const apiClient = new ApiClient(API_BASE_URL);
