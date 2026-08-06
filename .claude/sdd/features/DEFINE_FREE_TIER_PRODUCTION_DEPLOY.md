# DEFINE: Deploy em Produção com Serviços Gratuitos

> Publicar o GEFIN Agent (backend FastAPI, banco Postgres, frontend Streamlit) fora do ambiente local, usando apenas serviços com tier gratuito permanente.

## Metadata

| Attribute | Value |
|-----------|-------|
| **Feature** | FREE_TIER_PRODUCTION_DEPLOY |
| **Date** | 2026-08-06 |
| **Author** | jamazonaz (via define-agent) |
| **Status** | ✅ Complete (Built) |
| **Clarity Score** | 14/15 |

---

## Problem Statement

O GEFIN Agent hoje só roda localmente via `docker-compose` na máquina do desenvolvedor; não há nenhuma URL pública, então ninguém além de quem tem o repositório clonado e o Docker rodando consegue acessar ou demonstrar o agente.

---

## Target Users

| User | Role | Pain Point |
|------|------|------------|
| jamazonaz | Dono/desenvolvedor do projeto | Não consegue compartilhar uma demo funcional sem pedir para a outra pessoa clonar o repo, subir Docker e configurar `.env` localmente |
| Revisor/stakeholder convidado | Visualiza a demo via link | Não tem (e não deveria precisar de) Docker, Python ou acesso ao código para testar o agente |

---

## Goals

| Priority | Goal |
|----------|------|
| **MUST** | Backend (FastAPI) publicamente acessível via HTTPS, hospedado no Render.com (Web Service gratuito, build via Docker) |
| **MUST** | Banco de dados Postgres gerenciado no Neon (tier gratuito, sem expiração), com schema e dados de exemplo migrados de `db/init/*.sql` |
| **MUST** | Frontend (Streamlit) publicamente acessível, hospedado no Streamlit Community Cloud, apontando para o backend público |
| **MUST** | Nenhum segredo (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DATABASE_URL`) commitado no repositório; todos configurados via secret manager de cada plataforma |
| **SHOULD** | Deploy automático a partir de push/merge na branch `master` (integração nativa GitHub de Render e Streamlit Cloud) |
| **SHOULD** | Documentação (`docs/DEPLOYMENT.md`) com passo a passo reproduzível do deploy |
| **COULD** | Mensagem de "carregando" no frontend cobrindo o cold-start do Render (~30-50s após 15 min de inatividade) |

**Priority Guide:**
- **MUST** = MVP fails without this
- **SHOULD** = Important, but workaround exists
- **COULD** = Nice-to-have, cut first if needed

---

## Success Criteria

- [ ] URL pública do backend responde `GET /health` com `200 OK`
- [ ] URL pública do frontend carrega a UI Streamlit sem erro no console
- [ ] Pergunta de teste "Qual o saldo total em aberto?" feita na UI pública retorna resposta correta com linhagem, dentro de até 60s (considerando cold start do Render)
- [ ] As 5 views semânticas (`vw_ar_open_items`, `vw_ar_aging`, `vw_ar_customer_summary`, `vw_ar_kpi_daily`, `vw_ar_dso`) retornam os mesmos dados/contagens verificados localmente (40 clientes, 793 invoices, 357 payments)
- [ ] Varredura do repositório (git history + working tree) não encontra nenhuma chave de API ou credencial de banco
- [ ] Deploy é reproduzível a partir de um `git clone` limpo da branch `master`, seguindo `docs/DEPLOYMENT.md`

---

## Acceptance Tests

| ID | Scenario | Given | When | Then |
|----|----------|-------|------|------|
| AT-001 | Happy path | Stack publicada (Render + Neon + Streamlit Cloud) | Usuário abre a URL do Streamlit Cloud e pergunta "Qual o saldo total em aberto?" | Resposta correta com linhagem é exibida em até 60s, sem erro no console do navegador |
| AT-002 | Cold start do backend | Backend Render ficou inativo por mais de 15 minutos | Frontend faz a primeira requisição do dia | Requisição eventualmente sucede (após o cold start) ou o frontend mostra estado de carregamento amigável, sem crash |
| AT-003 | Sem segredos expostos | Repositório é público no GitHub | Alguém inspeciona o histórico de commits e os arquivos atuais | Nenhuma chave de API (`sk-...`, `gho_...`) ou string de conexão com credencial real é encontrada |
| AT-004 | Paridade de dados | Banco Neon populado a partir de `db/init/*.sql` | Query `SELECT COUNT(*) FROM invoices` (e equivalentes) é executada no Neon | Contagens batem com o ambiente local (40 clientes, 793 invoices, 357 payments) |

---

## Out of Scope

- CI/CD com testes automatizados antes do deploy (pipeline de qualidade fica para uma feature futura)
- Domínio customizado (usaremos os domínios padrão: `*.onrender.com`, `*.streamlit.app`, `*.neon.tech`)
- Autenticação de usuários / controle de acesso na aplicação pública — qualquer pessoa com o link acessa o chat
- Alta disponibilidade, múltiplas réplicas ou autoscaling (limitação inerente ao tier gratuito)
- Monitoramento/observabilidade avançada (APM, Sentry, alertas) — logs ficam restritos ao painel de cada plataforma
- Suporte ao provider `ollama` em produção (permanece só para uso local; produção usa Anthropic ou OpenAI)

---

## Constraints

| Type | Constraint | Impact |
|------|------------|--------|
| Technical | Apenas serviços com tier gratuito permanente e sem cartão de crédito (Render, Neon, Streamlit Community Cloud) | Descarta Railway/Fly.io (exigem cartão) e Render Postgres free (expira em 90 dias) |
| Technical | Stack atual é um único `docker-compose` com 3 containers acoplados | Precisa ser desacoplada em 3 deploys independentes, cada um com seu próprio ciclo de vida |
| Resource | Sem orçamento para infraestrutura paga | Aceitar as limitações do tier gratuito (cold start, sem SLA) como trade-off consciente |
| Technical | Render free Web Service "dorme" após ~15 min sem tráfego | Primeira requisição após esse período leva ~30-50s; UX precisa considerar isso |

---

## Technical Context

| Aspect | Value | Notes |
|--------|-------|-------|
| **Deployment Location** | Raiz do repo (`render.yaml` opcional) + `docs/DEPLOYMENT.md` (novo) + ajustes pontuais em `backend/app/db/connection.py` (sslmode) e `frontend/app.py` (BACKEND_URL) | Nenhuma nova pasta `src/`; é config/infra, não novo módulo de aplicação |
| **KB Domains** | Nenhum domínio do KB cobre Render/Neon/Streamlit Community Cloud especificamente (os domínios de infraestrutura disponíveis são voltados a AWS/Azure/Databricks) | Design phase seguirá a documentação oficial de cada plataforma em vez de padrões do KB |
| **IaC Impact** | Novos recursos externos (1 Web Service no Render, 1 projeto no Neon, 1 app no Streamlit Community Cloud) | Provisionamento manual via dashboard/CLI de cada plataforma; sem Terraform/IaC neste escopo |

**Já resolvido durante o Define (não é gap para o Design):**
- CORS: `backend/app/main.py` já tem `CORSMiddleware` com `allow_origins=["*"]` configurado — não requer mudança de código, só validação em produção.
- `DATABASE_URL` e `CATALOG_PATH` já são lidos via variável de ambiente (`backend/app/db/connection.py`, `backend/app/catalog/loader.py`) — plataformas de deploy só precisam injetar os valores corretos.

---

## Data Contract (if applicable)

### Source Inventory
| Source | Type | Volume | Freshness | Owner |
|--------|------|--------|-----------|-------|
| `gefin-db` (Postgres local, container Docker) | Postgres | 40 customers, 793 invoices, 357 payments | Migração única (snapshot), não é sync contínuo | jamazonaz |

### Schema Contract
Sem alteração de schema — reaproveita integralmente `db/init/01_schema.sql` (tabelas `customers`, `invoices`, `payments`, `audit_log`), `db/init/02_sample_data.sql` (seed) e `db/init/03_views.sql` (5 views semânticas), executados na ordem contra o Neon.

| Column | Type | Constraints | PII? |
|--------|------|-------------|------|
| `customers.customer_name` | VARCHAR | NOT NULL | Não (dados fictícios de exemplo) |
| `invoices.amount` | NUMERIC | NOT NULL | Não |
| `payments.amount` | NUMERIC | NOT NULL | Não |

### Freshness SLAs
| Layer | Target | Measurement |
|-------|--------|-------------|
| Neon (destino) | Migração única, executada uma vez no deploy inicial | Contagem de linhas comparada ao ambiente local logo após a migração |

### Completeness Metrics
- 100% das linhas de `customers`, `invoices` e `payments` migradas (contagens devem bater exatamente: 40 / 793 / 357)
- As 5 views semânticas devem existir e retornar dados no Neon antes do backend ser considerado pronto para produção

### Lineage Requirements
- Nenhum requisito adicional além do já existente (`get_lineage` tool do agente já documenta a origem via views semânticas)

---

## Assumptions

| ID | Assumption | If Wrong, Impact | Validated? |
|----|------------|------------------|------------|
| A-001 | O Render free Web Service consegue buildar a imagem a partir do `backend/Dockerfile` atual sem mudanças estruturais | Precisaria adaptar o Dockerfile ou trocar de runtime (buildpack Python nativo) | [ ] |
| A-002 | O Neon free tier comporta o volume atual de dados (40 clientes, 793 invoices, 357 payments) sem se aproximar dos limites do tier gratuito | Precisaria reduzir o dataset de exemplo | [ ] |
| A-003 | O Streamlit Community Cloud consegue rodar a partir do subdiretório `frontend/` deste mesmo repositório monorepo, sem precisar de um repo separado | Precisaria extrair o frontend para um repositório próprio só para o Streamlit Cloud | [ ] |
| A-004 | O `sslmode=require` do Neon é compatível com a `create_engine` do SQLAlchemy/psycopg2 já usada em `backend/app/db/connection.py` sem mudança de código, só a connection string | Precisaria adicionar parâmetros extras de conexão SSL no código | [ ] |

**Note:** Validar as suposições críticas antes da fase DESIGN. Suposições não validadas viram riscos.

---

## Clarity Score Breakdown

| Element | Score (0-3) | Notes |
|---------|-------------|-------|
| Problem | 3 | Problema específico e acionável: sem URL pública, só acesso local via Docker |
| Users | 3 | Duas personas nomeadas com dor clara (dono do projeto e revisor/stakeholder) |
| Goals | 3 | Metas com prioridade MoSCoW explícita, uma por plataforma/responsabilidade |
| Success | 3 | Critérios mensuráveis e testáveis (contagens exatas, códigos HTTP, tempo em segundos) |
| Scope | 2 | Escopo de fora bem definido, mas alguns detalhes de plataforma (ex.: parâmetros exatos do Render Blueprint) ficam para o Design |
| **Total** | **14/15** | |

**Scoring Guide:**
- 0 = Missing entirely
- 1 = Vague or incomplete
- 2 = Clear but missing details
- 3 = Crystal clear, actionable

**Minimum to proceed: 12/15**

---

## Open Questions

None - ready for Design.

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-06 | define-agent | Initial version |

---

## Next Step

**Ready for:** `/ship .claude/sdd/features/DEFINE_FREE_TIER_PRODUCTION_DEPLOY.md`
