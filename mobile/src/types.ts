export interface AdminUser {
  id: number;
  username: string;
  email: string;
  role: string;
}

export interface CustomerBrief {
  id: number;
  channel: 'WHATSAPP' | 'TELEGRAM';
  whatsapp_number?: string;
  telegram_chat_id?: string;
  display_name?: string;
}

export interface Order {
  id: string;
  customer_id: number;
  channel: 'WHATSAPP' | 'TELEGRAM';
  customer?: CustomerBrief;
  original_file_name?: string;
  file_type?: string;
  file_size_bytes: number;
  total_pages: number;
  copies: number;
  paper_size: string;
  color_mode: string;
  sides: string;
  pages_to_print: string;
  total_amount: number;
  payment_status: 'PENDING' | 'PAID' | 'FAILED' | 'REFUNDED';
  current_state: string;
  print_status: 'NOT_QUEUED' | 'QUEUED' | 'PRINTING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';
  print_serial?: string;
  pickup_code?: string;
  failure_reason?: string;
  created_at: string;
  updated_at: string;
}

export interface OrderHistory {
  id: number;
  from_status?: string;
  to_status: string;
  trigger_source: string;
  notes?: string;
  created_at: string;
}

export interface PaymentInfo {
  id: number;
  razorpay_order_id?: string;
  razorpay_payment_id?: string;
  razorpay_payment_link_url?: string;
  amount: number;
  currency: string;
  status: string;
  method?: string;
  created_at: string;
}

export interface OrderDetail extends Order {
  rate_per_page: number;
  subtotal_amount: number;
  additional_charges: number;
  stored_file_path?: string;
  printable_pdf_path?: string;
  history: OrderHistory[];
  payments: PaymentInfo[];
}

export interface Printer {
  id: number;
  name: string;
  cups_name: string;
  model: string;
  location: string;
  status: 'ONLINE' | 'BUSY' | 'OFFLINE' | 'ERROR';
  is_online: boolean;
  is_default: boolean;
  is_color_supported: boolean;
  supported_paper_sizes: string;
  connection_type?: 'CUPS' | 'WIFI' | 'BLUETOOTH' | 'USB';
  connection_uri?: string | null;
  current_job_id?: string;
  total_printed_jobs: number;
  updated_at: string;
}

export interface PricingRule {
  id: number;
  paper_size: string;
  is_color: boolean;
  is_double_sided: boolean;
  price_per_page: number;
  min_order_price: number;
  additional_charge: number;
  is_active: boolean;
  updated_at: string;
}

export interface Customer {
  id: number;
  channel: 'WHATSAPP' | 'TELEGRAM';
  whatsapp_number?: string;
  telegram_chat_id?: string;
  display_name: string;
  bot_state: string;
  order_count: number;
  total_spent: number;
  last_order_id?: string;
  last_order_date?: string;
  created_at: string;
}

export interface DashboardStats {
  kpis: {
    todays_orders: number;
    todays_revenue: number;
    pending_payments: number;
    queue_length: number;
    currently_printing: number;
    completed_orders: number;
    failed_orders: number;
    total_pages: number;
    bw_pages: number;
    color_pages: number;
    online_printers: number;
    total_printers: number;
  };
  revenue_chart: Array<{
    date: string;
    revenue: number;
    orders: number;
  }>;
}
