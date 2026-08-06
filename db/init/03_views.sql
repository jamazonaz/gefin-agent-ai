-- GEFIN Agent - Semantic views (ONLY layer the agent is allowed to query)

-- Open items with days overdue
CREATE OR REPLACE VIEW vw_ar_open_items AS
SELECT
    i.invoice_id,
    i.customer_id,
    c.customer_name,
    c.segment,
    c.region,
    i.issue_date,
    i.due_date,
    i.amount AS amount_original,
    ROUND(i.amount - COALESCE(p.paid, 0), 2) AS amount_open,
    GREATEST(0, (CURRENT_DATE - i.due_date)) AS days_overdue,
    i.status
FROM invoices i
JOIN customers c ON c.customer_id = i.customer_id
LEFT JOIN (
    SELECT invoice_id, SUM(amount) AS paid
    FROM payments
    GROUP BY invoice_id
) p ON p.invoice_id = i.invoice_id
WHERE i.status IN ('open', 'partial')
  AND (i.amount - COALESCE(p.paid, 0)) > 0.01;

COMMENT ON VIEW vw_ar_open_items IS 'Faturas em aberto com valor residual e dias de atraso. Camada semântica principal.';

-- Aging buckets
CREATE OR REPLACE VIEW vw_ar_aging AS
SELECT
    CASE
        WHEN days_overdue = 0 THEN 'A vencer / Em dia'
        WHEN days_overdue BETWEEN 1 AND 30 THEN '1-30 dias'
        WHEN days_overdue BETWEEN 31 AND 60 THEN '31-60 dias'
        WHEN days_overdue BETWEEN 61 AND 90 THEN '61-90 dias'
        ELSE '90+ dias'
    END AS aging_bucket,
    CASE
        WHEN days_overdue = 0 THEN 1
        WHEN days_overdue BETWEEN 1 AND 30 THEN 2
        WHEN days_overdue BETWEEN 31 AND 60 THEN 3
        WHEN days_overdue BETWEEN 61 AND 90 THEN 4
        ELSE 5
    END AS bucket_order,
    ROUND(SUM(amount_open), 2) AS amount_open,
    COUNT(*) AS invoice_count
FROM vw_ar_open_items
GROUP BY 1, 2
ORDER BY bucket_order;

COMMENT ON VIEW vw_ar_aging IS 'Distribuição do saldo em aberto por faixa de aging.';

-- Customer summary
CREATE OR REPLACE VIEW vw_ar_customer_summary AS
SELECT
    customer_id,
    customer_name,
    region,
    segment,
    ROUND(SUM(amount_open), 2) AS amount_open,
    COUNT(*) AS invoice_count,
    ROUND(AVG(days_overdue), 1) AS avg_days_overdue
FROM vw_ar_open_items
GROUP BY customer_id, customer_name, region, segment
ORDER BY amount_open DESC;

COMMENT ON VIEW vw_ar_customer_summary IS 'Saldo e quantidade de faturas em aberto por cliente.';

-- Daily KPI snapshot (simplified: current open balance projected back using issue dates)
-- For MVP we create a simple daily series of open balance based on invoices still open
CREATE OR REPLACE VIEW vw_ar_kpi_daily AS
WITH days AS (
    SELECT generate_series(
        CURRENT_DATE - INTERVAL '90 days',
        CURRENT_DATE,
        INTERVAL '1 day'
    )::DATE AS snapshot_date
),
open_by_day AS (
    SELECT
        d.snapshot_date,
        ROUND(SUM(
            CASE
                WHEN i.issue_date <= d.snapshot_date
                 AND (i.status IN ('open', 'partial')
                      OR EXISTS (
                          SELECT 1 FROM payments p
                          WHERE p.invoice_id = i.invoice_id
                            AND p.payment_date > d.snapshot_date
                      ))
                THEN i.amount - COALESCE((
                    SELECT SUM(p2.amount)
                    FROM payments p2
                    WHERE p2.invoice_id = i.invoice_id
                      AND p2.payment_date <= d.snapshot_date
                ), 0)
                ELSE 0
            END
        ), 2) AS amount_open,
        COUNT(*) FILTER (
            WHERE i.issue_date <= d.snapshot_date
              AND i.status IN ('open', 'partial')
        ) AS invoice_count
    FROM days d
    CROSS JOIN invoices i
    GROUP BY d.snapshot_date
)
SELECT snapshot_date, amount_open, invoice_count
FROM open_by_day
ORDER BY snapshot_date;

COMMENT ON VIEW vw_ar_kpi_daily IS 'Série temporal aproximada de saldo em aberto (últimos 90 dias).';

-- DSO (simplified calculation for MVP)
CREATE OR REPLACE VIEW vw_ar_dso AS
WITH open_total AS (
    SELECT COALESCE(SUM(amount_open), 0) AS total_open
    FROM vw_ar_open_items
),
sales_90d AS (
    SELECT COALESCE(SUM(amount), 0) / 90.0 AS avg_daily_sales
    FROM invoices
    WHERE issue_date >= CURRENT_DATE - INTERVAL '90 days'
)
SELECT
    CURRENT_DATE AS as_of_date,
    ROUND(
        CASE WHEN s.avg_daily_sales > 0
             THEN o.total_open / s.avg_daily_sales
             ELSE 0
        END
    , 1) AS dso_days,
    o.total_open,
    ROUND(s.avg_daily_sales, 2) AS avg_daily_sales
FROM open_total o, sales_90d s;

COMMENT ON VIEW vw_ar_dso IS 'DSO simplificado = Saldo em Aberto / Média de vendas diárias dos últimos 90 dias.';

-- Grant read access (the app user is the same in this prototype)
-- In a real setup you would use a restricted role that can only SELECT these views.
