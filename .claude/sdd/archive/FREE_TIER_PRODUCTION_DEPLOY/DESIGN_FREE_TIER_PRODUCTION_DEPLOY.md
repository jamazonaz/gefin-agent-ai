# DESIGN: Deploy em Produção com Serviços Gratuitos

> Especificação técnica para publicar o GEFIN Agent (backend, banco, frontend) em Render, Neon e Streamlit Community Cloud.

## Metadata

| Attribute | Value |
|-----------|-------|
| **Feature** | FREE_TIER_PRODUCTION_DEPLOY |
| **Date** | 2026-08-06 |
| **Author** | design-agent |
| **DEFINE** | [DEFINE_FREE_TIER_PRODUCTION_DEPLOY.md](./DEFINE_FREE_TIER_PRODUCTION_DEPLOY.md) |
| **Status** | ✅ Shipped |

**Confiança do Design:** 0.80 — nenhum domínio do KB cobre Render/Neon/Streamlit Community Cloud e nenhum agente especialista é específico dessas plataformas (confirmado no Define). Todos os fatos de plataforma abaixo (sintaxe do `render.yaml`, comportamento do free tier, formato da connection string do Neon, deploy de subdiretório no Streamlit Cloud) foram verificados na documentação oficial nesta fase, em vez de assumidos.

---

## Architecture Overview

```text
┌────────────────────────────────────────────────────────────────────────────┐
│                       PRODUCTION ARCHITECTURE                              │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  [Navegador] ──HTTPS──▶ [Streamlit Community Cloud]                        │
│                            frontend/app.py (main file path)                │
│                            secrets.toml: BACKEND_URL                       │
│                                   │                                        │
│                                   │ POST /chat, GET /health                │
│                                   ▼                                        │
│                          [Render Web Service — free]                       │
│                     backend/Dockerfile (FastAPI + LangGraph)               │
│                     catalog/ copiado na imagem em build-time               │
│                                   │              │                         │
│                                   │              └──▶ [Anthropic / OpenAI API]│
│                                   ▼                                        │
│                          [Neon Postgres — free, sslmode=require]           │
│                     customers, invoices, payments, audit_log               │
│                     + 5 views semânticas (vw_ar_*)                         │
│                                                                              │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## Components

| Component | Purpose | Technology |
|-----------|---------|------------|
| Frontend | UI de chat, renderiza resposta/dados/gráfico/linhagem | Streamlit 1.41.1, Streamlit Community Cloud |
| Backend API | Orquestra o agente (LangGraph), expõe `/chat`, `/health`, `/catalog` | FastAPI + Uvicorn, Docker, Render Web Service (free) |
| Banco de dados | Armazena tabelas brutas e serve as 5 views semânticas whitelisted | PostgreSQL 16, Neon (serverless, free) |
| Catálogo semântico | `metrics.yaml` — fonte de métricas/views que o agente consulta | Arquivo YAML, empacotado na imagem Docker do backend |

---

## Key Decisions

### Decision 1: Desacoplar o `docker-compose` em 3 deploys independentes

| Attribute | Value |
|-----------|-------|
| **Status** | Accepted |
| **Date** | 2026-08-06 |

**Context:** Não existe plataforma gratuita permanente que rode um `docker-compose` multi-container como uma unidade só. O stack precisa ser dividido.

**Choice:** Backend no Render (Docker Web Service), banco no Neon (Postgres gerenciado), frontend no Streamlit Community Cloud — cada um com seu próprio ciclo de deploy, todos apontando para a branch `master`.

**Rationale:** Cada peça já é stateless/env-driven (confirmado no Define: `DATABASE_URL`, `CATALOG_PATH`, `BACKEND_URL` já vêm de variável de ambiente), então o desacoplamento não exige reescrever lógica de negócio — só a forma como cada serviço é configurado e inicializado.

**Alternatives Rejected:**
1. Um único VPS gratuito (ex.: Oracle Cloud Free Tier) rodando o `docker-compose` inteiro — rejeitado por exigir cartão de crédito no cadastro e manutenção manual de SO/patches, fora do que o usuário pediu ("serviço gratuito", sem operação de infra).
2. Render Postgres free — rejeitado porque expira em 90 dias (Neon não expira).

**Consequences:**
- Aceita-se 3 painéis de administração/log separados em vez de um só `docker compose logs`.
- Ganha-se deploy independente por serviço (atualizar só o frontend não redeploya o backend).

---

### Decision 2: Empacotar `catalog/` dentro da imagem Docker do backend (build-time), abandonando o bind mount

| Attribute | Value |
|-----------|-------|
| **Status** | Accepted |
| **Date** | 2026-08-06 |

**Context:** Hoje `docker-compose.yml` monta `./catalog:/app/catalog:ro` em runtime. O Render não suporta bind mount de arquivos do repositório — só constrói a imagem a partir do Dockerfile. Sem esse volume, `CATALOG_PATH=/app/catalog/metrics.yaml` ficaria vazio e `list_metrics`/`get_metric_definition` quebrariam em produção.

**Choice:** Mudar o `dockerContext` do Render para a raiz do repositório (não mais `backend/`) e adicionar `COPY catalog ./catalog` no `backend/Dockerfile`, com os demais `COPY` ajustados para caminhos relativos à raiz (`backend/requirements.txt`, `backend/app`).

**Rationale:** Mantém `catalog/metrics.yaml` como fonte única (sem duplicar o arquivo dentro de `backend/`), evitando divergência entre o catálogo usado localmente e em produção.

**Alternatives Rejected:**
1. Duplicar `catalog/metrics.yaml` para dentro de `backend/catalog/` — rejeitado: cria duas cópias que podem divergir silenciosamente.
2. Buscar o catálogo de uma URL remota (ex.: GitHub raw) em runtime — rejeitado: complexidade e dependência de rede desnecessárias para um arquivo estático pequeno.

**Consequences:**
- `docker-compose.yml` local também precisa apontar o `build.context` do backend para a raiz do repo (mudança de infra local, não de comportamento).
- Qualquer atualização em `catalog/metrics.yaml` exige rebuild + redeploy do backend no Render (aceitável: catálogo muda com pouca frequência).

---

### Decision 3: Alternar `uvicorn --reload` via variável `APP_ENV`, mantendo um único Dockerfile

| Attribute | Value |
|-----------|-------|
| **Status** | Accepted |
| **Date** | 2026-08-06 |

**Context:** O `CMD` atual do `backend/Dockerfile` sempre roda `uvicorn --reload`, útil para o volume mount local (`./backend/app:/app/app`) mas incorreto em produção (overhead de watcher de arquivos, sem hot-reload possível numa imagem imutável).

**Choice:** Trocar o `CMD` por um wrapper `sh -c` que só adiciona `--reload` quando `APP_ENV=development`; `docker-compose.yml` passa a definir `APP_ENV: development` no serviço backend. O Render não define essa variável, então roda sem `--reload` por padrão.

**Rationale:** Um único Dockerfile para os dois ambientes evita manter dois arquivos de build em paralelo (risco de divergência), e o comportamento padrão (sem a variável) já é o seguro para produção.

**Alternatives Rejected:**
1. Dois Dockerfiles (`Dockerfile` e `Dockerfile.prod`) — rejeitado por duplicação de manutenção.
2. Usar o campo `dockerCommand` do Render para sobrescrever o `CMD` — rejeitado: adiciona uma configuração só da plataforma Render, enquanto a variável de ambiente funciona em qualquer lugar (mais portável).

**Consequences:**
- Comportamento de dev/prod passa a depender de uma variável de ambiente — precisa estar documentada em `docs/DEPLOYMENT.md` e no `.env.example`.

---

### Decision 4: Fixar `PORT=8000` explicitamente no Render em vez de reescrever a app para ler `$PORT`

| Attribute | Value |
|-----------|-------|
| **Status** | Accepted |
| **Date** | 2026-08-06 |

**Context:** A documentação do Render recomenda que o serviço escute na porta definida por `$PORT` (padrão 10000), mas confirma que também é possível fixar outra porta — nesse caso, "Render usualmente detecta e usa" a porta exposta, e se a detecção falhar o deploy é rejeitado com erro explícito nos logs (não falha silenciosamente).

**Choice:** Manter o Uvicorn fixo em `--port 8000` (igual ao `EXPOSE 8000` já existente) e declarar `PORT=8000` como env var explícita no `render.yaml`, eliminando a ambiguidade da autodetecção.

**Rationale:** Evita reescrever `main.py`/Dockerfile para ler `$PORT` dinamicamente — mantém o comportamento idêntico entre local (`docker-compose`, porta 8000) e produção.

**Alternatives Rejected:**
1. Ler `$PORT` dinamicamente no `CMD` do Uvicorn — rejeitado por ser mudança desnecessária dado que fixar a env var resolve o mesmo problema com menos código.

**Consequences:**
- Se o Render mudar sua porta padrão/detecção no futuro, será preciso revisitar essa env var — risco baixo e documentado.

---

### Decision 5: Frontend lê `BACKEND_URL` de `st.secrets` com fallback para `os.getenv`

| Attribute | Value |
|-----------|-------|
| **Status** | Accepted |
| **Date** | 2026-08-06 |

**Context:** `frontend/app.py` hoje só lê `BACKEND_URL` via `os.getenv`. O Streamlit Community Cloud não expõe variáveis de ambiente do jeito do Docker — segredos/config são injetados via `st.secrets` (arquivo `secrets.toml` colado na UI da plataforma). Sem essa mudança, o frontend em produção sempre cairia no default `http://localhost:8000`, que não existe no Streamlit Cloud.

**Choice:** Adicionar uma função `_get_secret(key, default)` que tenta `st.secrets[key]` primeiro e cai para `os.getenv(key, default)` se o secrets store não existir ou não tiver a chave (try/except, já que `st.secrets` pode não ter nenhum arquivo configurado localmente).

**Rationale:** Uma única implementação funciona nos dois ambientes (Docker local via env var, Streamlit Cloud via secrets), sem branch de código por ambiente.

**Alternatives Rejected:**
1. Exigir sempre `st.secrets` — rejeitado: quebraria o `docker-compose` local, que não tem `.streamlit/secrets.toml`.

**Consequences:**
- Para testar localmente com `st.secrets`, o dev pode opcionalmente criar `.streamlit/secrets.toml` (já está no `.gitignore`); não é obrigatório.

---

## File Manifest

| # | File | Action | Purpose | Agent | Dependencies |
|---|------|--------|---------|-------|--------------|
| 1 | `render.yaml` | Create | Blueprint do Render: Web Service Docker, plan free, healthCheckPath, envVars | (general) | None |
| 2 | `backend/Dockerfile` | Modify | Build-context raiz, `COPY catalog`, `CMD` condicional por `APP_ENV` (Decisions 2 e 3) | (general) | 1 |
| 3 | `docker-compose.yml` | Modify | `build.context: .` para o backend, `APP_ENV: development`, `dockerfile: backend/Dockerfile` | (general) | 2 |
| 4 | `frontend/app.py` | Modify | `_get_secret()` para `BACKEND_URL` (Decision 5) | @python-developer | None |
| 5 | `db/migrate_to_neon.sh` | Create | Script idempotente que roda `01_schema.sql`, `02_sample_data.sql`, `03_views.sql` contra o Neon via `psql` | @shell-script-specialist | None |
| 6 | `docs/DEPLOYMENT.md` | Create | Passo a passo reproduzível (Neon → migração → Render → Streamlit Cloud → smoke test) | @code-documenter | 1, 2, 3, 4, 5 |
| 7 | `.env.example` | Modify | Documentar `APP_ENV` e nota sobre `sslmode=require` do Neon | (general) | 3 |

**Total Files:** 7

---

## Agent Assignment Rationale

> Agentes descobertos a partir do catálogo disponível nesta sessão (`agentspec:*`). Nenhum agente é específico de Render/Neon/Streamlit Community Cloud — confirmado no Define (Technical Context → KB Domains).

| Agent | Files Assigned | Why This Agent |
|-------|----------------|-----------------|
| @shell-script-specialist | 5 | "Elite shell scripting specialist... building deployment scripts" — encaixe direto para o script de migração idempotente com tratamento de erro |
| @python-developer | 4 | Mudança de código Python pequena mas com padrão claro (fallback de config) — "Python code architect... clean patterns" |
| @code-documenter | 6 | "Documentation specialist for creating comprehensive, production-ready documentation" — guia de deploy é exatamente esse tipo de artefato |
| (general) | 1, 2, 3, 7 | Configuração de infraestrutura (YAML do Render, Dockerfile, docker-compose, env vars) sem especialista dedicado a essas plataformas no catálogo de agentes disponível |

**Agent Discovery:** agentes listados na sessão atual (catálogo `agentspec`), sem correspondência direta para Render/Neon/Streamlit Community Cloud.

---

## Code Patterns

### Pattern 1: `backend/Dockerfile` — build-context raiz + reload condicional

```dockerfile
# Build context: raiz do repositório (não mais backend/)
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY catalog ./catalog

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV CATALOG_PATH=/app/catalog/metrics.yaml

EXPOSE 8000

# APP_ENV=development (setado no docker-compose local) liga --reload;
# ausente (Render) => roda sem --reload.
CMD ["sh", "-c", "if [ \"$APP_ENV\" = development ]; then uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload; else uvicorn app.main:app --host 0.0.0.0 --port 8000; fi"]
```

### Pattern 2: `render.yaml` — Blueprint do Web Service

```yaml
services:
  - name: gefin-backend
    type: web
    runtime: docker
    plan: free
    dockerfilePath: backend/Dockerfile
    dockerContext: .
    healthCheckPath: /health
    autoDeployTrigger: commit
    envVars:
      - key: PORT
        value: 8000
      - key: DATABASE_URL
        sync: false          # setado manualmente no dashboard com a connection string do Neon
      - key: CATALOG_PATH
        value: /app/catalog/metrics.yaml
      - key: LLM_PROVIDER
        value: anthropic
      - key: LLM_MODEL
        value: claude-sonnet-4-20250514
      - key: ANTHROPIC_API_KEY
        sync: false          # setado manualmente no dashboard
      - key: LOG_LEVEL
        value: INFO
      - key: MAX_AGENT_STEPS
        value: "6"
      - key: SQL_ROW_LIMIT
        value: "500"
      - key: SQL_TIMEOUT_SECONDS
        value: "30"
```

### Pattern 3: `frontend/app.py` — resolução de `BACKEND_URL`

```python
def _get_secret(key: str, default: str) -> str:
    """Lê de st.secrets (Streamlit Cloud) com fallback para os.getenv (Docker local)."""
    try:
        return st.secrets[key]
    except Exception:
        return os.getenv(key, default)


st.set_page_config(...)  # st.secrets só pode ser acessado DEPOIS do set_page_config
                          # (StreamlitSetPageConfigMustBeFirstCommandError) — bug pego
                          # e corrigido durante a verificação do Build (ver BUILD_REPORT)

BACKEND_URL = _get_secret("BACKEND_URL", "http://localhost:8000")
```

### Pattern 4: `db/migrate_to_neon.sh` — migração idempotente

```bash
#!/usr/bin/env bash
# Uso: NEON_DATABASE_URL="postgresql://user:pass@host/db?sslmode=require" ./db/migrate_to_neon.sh
set -euo pipefail

: "${NEON_DATABASE_URL:?Defina NEON_DATABASE_URL antes de rodar este script}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for f in 01_schema.sql 02_sample_data.sql 03_views.sql; do
  echo "==> Aplicando $f no Neon..."
  psql "$NEON_DATABASE_URL" -v ON_ERROR_STOP=1 -f "$SCRIPT_DIR/init/$f"
done

echo "==> Verificando contagens..."
psql "$NEON_DATABASE_URL" -c \
  "SELECT (SELECT COUNT(*) FROM customers) customers, (SELECT COUNT(*) FROM invoices) invoices, (SELECT COUNT(*) FROM payments) payments;"
```

---

## Data Flow

```text
1. Criar projeto + database no Neon
   │
   ▼
2. Rodar db/migrate_to_neon.sh contra a connection string do Neon
   (aplica 01_schema.sql, 02_sample_data.sql, 03_views.sql)
   │
   ▼
3. Verificar contagens no Neon (40 clientes / 793 invoices / 357 payments) — AT-004
   │
   ▼
4. Criar Web Service no Render a partir de render.yaml, branch master
   Configurar envVars sync:false (DATABASE_URL do Neon, ANTHROPIC_API_KEY)
   │
   ▼
5. Aguardar build + deploy; verificar GET /health — parte de AT-001
   │
   ▼
6. Criar app no Streamlit Community Cloud, branch master,
   main file path = frontend/app.py, requirements em frontend/requirements.txt
   Configurar secrets.toml com BACKEND_URL = https://<serviço>.onrender.com
   │
   ▼
7. Abrir a URL pública do Streamlit Cloud e rodar a pergunta de teste — AT-001, AT-002
```

---

## Integration Points

| External System | Integration Type | Authentication |
|-----------------|-------------------|-----------------|
| Anthropic / OpenAI API | REST (via `langchain-anthropic`/`langchain-openai`, já existente) | API key em env var `sync: false` no Render |
| Neon Postgres | SQLAlchemy + psycopg2, `postgresql://...?sslmode=require&channel_binding=require` | Usuário/senha na connection string, TLS obrigatório |
| Render (deploy) | GitHub App / OAuth do Render, auto-deploy na branch `master` | Autorização de repositório via GitHub |
| Streamlit Community Cloud (deploy) | GitHub OAuth, auto-deploy na branch `master` | Autorização de repositório via GitHub |

---

## Testing Strategy

| Test Type | Scope | Files / Comandos | Tools | Cobre |
|-----------|-------|-------------------|-------|-------|
| Smoke (banco) | Contagens pós-migração | `psql "$NEON_DATABASE_URL" -c "SELECT COUNT(*) ..."` | psql | AT-004 |
| Smoke (backend) | Health check público | `curl https://<serviço>.onrender.com/health` | curl | Parte de AT-001 |
| E2E (fluxo completo) | Pergunta real na UI pública | Abrir Streamlit Cloud URL, perguntar "Qual o saldo total em aberto?" | Manual (navegador) | AT-001 |
| E2E (cold start) | Comportamento após 15+ min ocioso | Repetir a pergunta após esperar o serviço "dormir" | Manual | AT-002 |
| Segurança | Ausência de segredos no repo público | `grep` por padrões de chave em `git log` + arquivos rastreados (já usado ao criar o repo) | git, grep | AT-003 |

---

## Error Handling

| Error Type | Handling Strategy | Retry? |
|------------|---------------------|--------|
| Render cold start (>15 min ocioso) | Frontend mostra o spinner já existente (`st.spinner`); primeira resposta pode levar até ~1 min | Não — usuário só espera; comportamento documentado em `docs/DEPLOYMENT.md` |
| Neon connection drop (serverless scale-to-zero) | `pool_pre_ping=True` já configurado em `backend/app/db/connection.py` — SQLAlchemy detecta conexão morta e reconecta | Sim, automático via SQLAlchemy |
| `DATABASE_URL`/`ANTHROPIC_API_KEY` ausente no Render | Falha rápida e visível no boot (erro de conexão/401 nos logs do Render) — não é mascarado | Não — corrigir env var e redeploy |
| Sessão perdida após cold start | `memory.py` é um store em memória; reiniciar o processo zera sessões ativas | Não — limitação aceita (fora de escopo HA, conforme Define) |

---

## Configuration

| Config Key | Type | Default | Description |
|------------|------|---------|--------------|
| `APP_ENV` | string | *(vazio)* | `development` liga `uvicorn --reload` (só local); ausente = produção |
| `PORT` | int | `8000` | Porta fixa do Uvicorn, declarada explicitamente no Render |
| `DATABASE_URL` | string | `postgresql://gefin:gefin@localhost:5432/gefin` | Em produção: connection string do Neon com `sslmode=require` |
| `CATALOG_PATH` | string | `/app/catalog/metrics.yaml` | Caminho do catálogo dentro da imagem (agora copiado, não montado) |
| `BACKEND_URL` (frontend) | string | `http://localhost:8000` | Em produção: lido de `st.secrets`, URL pública do Render |

---

## Security Considerations

- Nenhum segredo em código ou `render.yaml`/`secrets.toml` versionado — `ANTHROPIC_API_KEY`/`DATABASE_URL` são `sync: false` no Render (setados manualmente no dashboard) e `secrets.toml` do Streamlit Cloud é colado na UI, nunca commitado.
- `sslmode=require&channel_binding=require` obrigatório na conexão com o Neon (TLS sempre ativo).
- CORS permanece `allow_origins=["*"]` (já existente) — risco aceito conscientemente para este protótipo público, documentado no Define como fora de escopo qualquer autenticação/autorização.
- Aplicação pública fica sem autenticação — qualquer pessoa com o link do Streamlit Cloud usa o chat; aceito explicitamente no Define (Out of Scope).

---

## Observability

| Aspect | Implementation |
|--------|-----------------|
| Logging | Logs `INFO` já existentes (`logging.basicConfig`) ficam visíveis nos painéis nativos de logs do Render e do Streamlit Community Cloud — nenhuma ferramenta nova |
| Metrics | Não incluído (fora de escopo no Define — sem APM/observabilidade avançada) |
| Tracing | Não incluído (fora de escopo) |

---

## Pipeline Architecture (if applicable)

Não aplicável — a migração Neon é uma execução única via script (`db/migrate_to_neon.sh`, Pattern 4), não um pipeline recorrente de dados. Ver "Data Flow" e "Code Patterns" acima para o processo completo.

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-08-06 | design-agent | Initial version |
| 1.1 | 2026-08-07 | ship-agent | Shipped and archived |

---

## Next Step

**Ready for:** Shipped — see `SHIPPED_2026-08-07.md` neste mesmo diretório.
