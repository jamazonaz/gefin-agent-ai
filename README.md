# GEFIN Agent

**Agentic Analytics for Contas a Receber** — protótipo local com governança de dados, linhagem visível e chat em linguagem natural.

> Portfólio project · 100% Docker · Single-agent (Plan → Tools → Reflect) · Semantic layer + catalog

---

## O que é

O GEFIN Agent permite que o time financeiro pergunte em português sobre **contas a receber** e receba:

- Respostas em linguagem natural
- Tabelas e gráficos dinâmicos
- **Linhagem completa** (views usadas + SQL executado)
- Tudo com guardrails: o agente só consulta views semânticas whitelisted

Não é um simples text-to-SQL. É um **agente** com tools, planejamento e reflexão.

---

## Arquitetura (resumo)

```
Usuário → Chainlit UI (login + chat, montado no FastAPI) → Agent (ReAct loop)
                              ├── Tools (catalog, execute_sql, chart, lineage…)
                              ├── PostgreSQL (views semânticas)
                              └── Claude / OpenAI / Ollama (LLM)
```

Documentação completa:
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md)

---

## Pré-requisitos

- Docker + Docker Compose
- Uma chave de API da **Anthropic (Claude)** — recomendado  
  *ou* OpenAI *ou* Ollama local (se preferir 100% offline)

---

## Subir o protótipo (com Claude)

```bash
git clone <seu-repo>
cd gefin-agent
cp .env.example .env
```

Edite o `.env` e coloque sua chave:

```bash
LLM_PROVIDER=anthropic
LLM_MODEL=claude-sonnet-4-20250514
ANTHROPIC_API_KEY=sk-ant-api03-sua-chave-aqui
```

Gere o segredo de sessão do chat e defina o login único (usado pelo Chainlit):

```bash
pip install chainlit  # só para gerar o segredo, uma vez
chainlit create-secret
```

```bash
# No .env:
CHAINLIT_AUTH_SECRET=<valor gerado acima>
APP_USERNAME=gefin
APP_PASSWORD=escolha-uma-senha
```

Suba os serviços (Ollama **não** sobe por padrão):

```bash
docker compose up --build
```

### Alternativa: Ollama local

```bash
# No .env:
# LLM_PROVIDER=ollama
# LLM_MODEL=qwen2.5:14b

docker compose --profile ollama up --build
docker compose exec ollama ollama pull qwen2.5:14b
```

### URLs

| Serviço   | URL                          |
|-----------|-------------------------------|
| Chat UI   | http://localhost:8000/chainlit |
| API docs  | http://localhost:8000/docs   |
| Adminer   | http://localhost:8080        |

Adminer: sistema `PostgreSQL`, servidor `db`, usuário/senha/db `gefin`.

---

## Exemplos de perguntas

- Qual o saldo total em aberto?
- Mostre o aging por faixa de atraso
- Quais os 5 clientes com maior saldo a receber?
- Qual o DSO atual?
- Evolução do saldo em aberto nos últimos 90 dias

---

## Stack

| Camada        | Tecnologia                          |
|---------------|-------------------------------------|
| Chat UI       | Chainlit + Plotly (montado no FastAPI) |
| Backend       | FastAPI + LangChain tools (ReAct)   |
| LLM           | Claude (Anthropic) / OpenAI / Ollama |
| Banco         | PostgreSQL 16 + views semânticas    |
| Catálogo      | YAML versionado                     |
| Guardrails    | sqlglot + whitelist de views        |

---

## Estrutura do repositório

```
gefin-agent/
├── docker-compose.yml
├── .env.example
├── catalog/metrics.yaml          # catálogo semântico
├── db/init/                      # schema + sample data + views
├── backend/                      # FastAPI + agent + Chainlit (chat UI)
└── docs/                         # arquitetura e requisitos
```

---

## Decisões de design (portfólio)

1. **Single-agent com tools** em vez de text-to-SQL puro → demonstra arquitetura agentic real.
2. **Views + catálogo** → padrão moderno de Agentic Data Stack (LLM não vê tabelas brutas).
3. **Linhagem sempre visível** → diferencial forte de governança.
4. **Tudo local em Docker** → qualquer pessoa consegue rodar e avaliar.
5. **Caminho de evolução claro** → Fase 2: contas a pagar + Iceberg + OpenMetadata.

---

## Desenvolvimento local (sem rebuild)

Os volumes montam o código. Basta editar e o `--reload` do uvicorn recarrega (inclui a UI do Chainlit, montada no mesmo processo).

Para testar só o backend:

```bash
cd backend
pip install -r requirements.txt
export DATABASE_URL=postgresql://gefin:gefin@localhost:5432/gefin
export LLM_PROVIDER=anthropic
export ANTHROPIC_API_KEY=sk-ant-...
export LLM_MODEL=claude-sonnet-4-20250514
uvicorn app.main:app --reload
```

---

## Roadmap (pós-MVP)

- [ ] Contas a pagar
- [ ] Fluxo de caixa
- [ ] Memória de longo prazo
- [ ] Multi-agent (supervisor + especialistas)
- [ ] Migração para lakehouse (Iceberg) + OpenMetadata
- [ ] Testes automatizados das tools e do loop do agente

---

## Licença

MIT — use livremente no seu portfólio.
