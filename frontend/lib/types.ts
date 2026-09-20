export type CustomerBooking = {
  flight: string;
  route: string;
  scheduled_departure: string;
  status: string;
  delay_hours: number | null;
  new_departure: string | null;
};

export type Customer = {
  id: number;
  name: string;
  loyalty_tier: string;
  email: string;
  phone: string;
  flights_last_12m: number;
  prior_complaints: string;
  pnr: string;
  bookings: CustomerBooking[];
  opener: string;
};

export type ChatMessage = {
  id: number;
  role: "customer" | "agent";
  content: string;
  created_at: string;
};

export type ToolTrace = {
  tool: string;
  args: Record<string, unknown>;
  result: Record<string, unknown>;
  policy_reference: string;
  escalated: boolean;
};

export type Conversation = {
  id: number;
  pnr: string;
  customer_name: string;
  loyalty_tier: string;
  escalated: boolean;
  escalation_reason: string | null;
  started_at: string;
  messages: ChatMessage[];
};

export type AuditEntry = {
  id: number;
  timestamp: string;
  pnr: string | null;
  customer_message: string | null;
  agent_reasoning: string | null;
  tool_called: string | null;
  tool_args: string | null;
  policy_reference: string | null;
  action_taken: string | null;
  escalated: boolean;
};

export type SendMessageResponse = {
  user_message: ChatMessage;
  agent_message: ChatMessage;
  tool_trace: ToolTrace[];
  escalated: boolean;
  provider: string;
};
