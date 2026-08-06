-- GEFIN Agent - Realistic sample data for Contas a Receber
-- ~40 customers, hundreds of invoices, payments, mix of open/paid/overdue

-- Customers
INSERT INTO customers (customer_name, segment, region) VALUES
('TechNova Soluções Ltda', 'Enterprise', 'Sudeste'),
('AgroBrasil Comércio S.A.', 'Enterprise', 'Centro-Oeste'),
('Varejo Rápido ME', 'SMB', 'Sudeste'),
('Indústrias Metalúrgicas Sul', 'Mid-Market', 'Sul'),
('Saúde Total Clínicas', 'Mid-Market', 'Sudeste'),
('Logística Norte Express', 'Enterprise', 'Norte'),
('EducaMais Cursos Online', 'SMB', 'Nordeste'),
('ConstruFácil Engenharia', 'Mid-Market', 'Sudeste'),
('FarmaVida Distribuidora', 'Enterprise', 'Sudeste'),
('Alimentos Verdes Orgânicos', 'SMB', 'Sul'),
('Energia Limpa Brasil', 'Enterprise', 'Nordeste'),
('Moda Urbana Confecções', 'Mid-Market', 'Sudeste'),
('Transporte Seguro Ltda', 'Mid-Market', 'Centro-Oeste'),
('Software House Alpha', 'SMB', 'Sudeste'),
('Café do Cerrado Export', 'Enterprise', 'Centro-Oeste'),
('PetCare Serviços', 'SMB', 'Sul'),
('Imobiliária Horizonte', 'Mid-Market', 'Sudeste'),
('Química Industrial Beta', 'Enterprise', 'Sudeste'),
('Turismo Aventura Nordeste', 'SMB', 'Nordeste'),
('Auto Peças Centro', 'Mid-Market', 'Centro-Oeste'),
('CloudSync Tecnologia', 'Enterprise', 'Sudeste'),
('Padaria Artesanal Bom Pão', 'SMB', 'Sul'),
('Seguros Protege Mais', 'Enterprise', 'Sudeste'),
('Agritech Inovação', 'Mid-Market', 'Centro-Oeste'),
('Design Criativo Studio', 'SMB', 'Sudeste'),
('Mineração Serra Norte', 'Enterprise', 'Norte'),
('Franquia Fitness Pro', 'Mid-Market', 'Sudeste'),
('Importados Oriente Ltda', 'Mid-Market', 'Sudeste'),
('Serviços Contábeis Precision', 'SMB', 'Sul'),
('Hospital Regional Vida', 'Enterprise', 'Nordeste'),
('E-commerce Flash Sales', 'Mid-Market', 'Sudeste'),
('Pecuária Boi Forte', 'Enterprise', 'Centro-Oeste'),
('Escola Técnica Futuro', 'SMB', 'Nordeste'),
('Químicos Especializados Gamma', 'Mid-Market', 'Sudeste'),
('Logística Portuária Sul', 'Enterprise', 'Sul'),
('App Mobile StartUp', 'SMB', 'Sudeste'),
('Indústria Têxtil Nordeste', 'Mid-Market', 'Nordeste'),
('Consultoria Estratégica Apex', 'Enterprise', 'Sudeste'),
('Distribuidora de Bebidas Rio', 'Mid-Market', 'Sudeste'),
('Fazenda Orgânica Vale Verde', 'SMB', 'Sul');

-- Generate invoices with realistic dates and statuses
DO $$
DECLARE
    c RECORD;
    n INT;
    inv_id INT;
    issue DATE;
    due DATE;
    amt NUMERIC;
    st TEXT;
    pay_amt NUMERIC;
    pay_date DATE;
BEGIN
    FOR c IN SELECT customer_id FROM customers LOOP
        -- 15 to 25 invoices per customer
        FOR n IN 1 .. (15 + (c.customer_id % 11)) LOOP
            issue := CURRENT_DATE - ((random() * 180)::INT);
            due   := issue + (20 + (random() * 40)::INT);
            amt   := ROUND((500 + random() * 45000)::NUMERIC, 2);

            -- Status distribution: ~55% open, ~35% paid, ~10% partial
            IF random() < 0.55 THEN
                st := 'open';
            ELSIF random() < 0.85 THEN
                st := 'paid';
            ELSE
                st := 'partial';
            END IF;

            INSERT INTO invoices (customer_id, issue_date, due_date, amount, status)
            VALUES (c.customer_id, issue, due, amt, st)
            RETURNING invoice_id INTO inv_id;

            -- Payments
            IF st = 'paid' THEN
                pay_date := due - ((random() * 10)::INT) + ((random() * 15)::INT);
                IF pay_date > CURRENT_DATE THEN
                    pay_date := CURRENT_DATE - (random() * 5)::INT;
                END IF;
                INSERT INTO payments (invoice_id, payment_date, amount)
                VALUES (inv_id, pay_date, amt);
            ELSIF st = 'partial' THEN
                pay_amt := ROUND((amt * (0.3 + random() * 0.5))::NUMERIC, 2);
                pay_date := due - ((random() * 5)::INT);
                INSERT INTO payments (invoice_id, payment_date, amount)
                VALUES (inv_id, pay_date, pay_amt);
            END IF;
        END LOOP;
    END LOOP;
END $$;

-- Force some clearly overdue open invoices for interesting aging demos
UPDATE invoices
SET due_date = CURRENT_DATE - (30 + (random() * 90)::INT),
    status = 'open'
WHERE invoice_id IN (
    SELECT invoice_id FROM invoices
    WHERE status = 'open'
    ORDER BY random()
    LIMIT 120
);

ANALYZE customers;
ANALYZE invoices;
ANALYZE payments;
