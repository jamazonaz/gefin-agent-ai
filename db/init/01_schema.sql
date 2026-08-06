-- GEFIN Agent - Base schema (raw tables)
-- These tables are NOT exposed to the agent. Only views in 03_views.sql are.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Customers
CREATE TABLE customers (
    customer_id     SERIAL PRIMARY KEY,
    customer_name   VARCHAR(200) NOT NULL,
    segment         VARCHAR(50)  NOT NULL,  -- Enterprise, Mid-Market, SMB
    region          VARCHAR(50)  NOT NULL,  -- Sudeste, Sul, Nordeste, Centro-Oeste, Norte
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Invoices
CREATE TABLE invoices (
    invoice_id      SERIAL PRIMARY KEY,
    customer_id     INTEGER NOT NULL REFERENCES customers(customer_id),
    issue_date      DATE NOT NULL,
    due_date        DATE NOT NULL,
    amount          NUMERIC(15,2) NOT NULL CHECK (amount > 0),
    status          VARCHAR(20) NOT NULL DEFAULT 'open',  -- open, paid, partial, cancelled
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Payments
CREATE TABLE payments (
    payment_id      SERIAL PRIMARY KEY,
    invoice_id      INTEGER NOT NULL REFERENCES invoices(invoice_id),
    payment_date    DATE NOT NULL,
    amount          NUMERIC(15,2) NOT NULL CHECK (amount > 0),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Audit log (written by the agent)
CREATE TABLE audit_log (
    id              BIGSERIAL PRIMARY KEY,
    session_id      VARCHAR(100),
    user_message    TEXT,
    agent_plan      TEXT,
    tools_called    JSONB,
    final_sql       TEXT,
    response_summary TEXT,
    lineage         JSONB,
    latency_ms      INTEGER,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Helpful indexes
CREATE INDEX idx_invoices_customer ON invoices(customer_id);
CREATE INDEX idx_invoices_status ON invoices(status);
CREATE INDEX idx_invoices_due_date ON invoices(due_date);
CREATE INDEX idx_payments_invoice ON payments(invoice_id);
CREATE INDEX idx_audit_session ON audit_log(session_id);
CREATE INDEX idx_audit_created ON audit_log(created_at);
