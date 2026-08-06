# Deploy em Produção — GEFIN Agent

> Runbook reproduzível para publicar o GEFIN Agent usando apenas serviços com tier gratuito permanente.

---

## 1. Visão geral

Este guia publica o GEFIN Agent em três serviços independentes: o backend FastAPI (Docker) no **Render.com**, o banco PostgreSQL no **Neon** e o frontend Streamlit no **Streamlit Community Cloud**. Cada peça já é stateless e configurada por variável de ambiente (`DATABASE_URL`, `CATALOG_PATH`, `BACKEND_URL`), então o deploy é apenas configuração de plataforma — nenhuma lógica de negócio muda. Os três serviços rodam permanentemente em tier gratuito, sem necessidade de cartão de crédito.

---

## 2. Pré-requisitos

- Conta no GitHub, com o repositório já publicado e a branch `master` atualizada.
- Conta no [Render.com](https://render.com) (gratuita, sem cartão).
- Conta no [Neon](https://neon.tech) (gratuita, sem cartão).
- Conta no [Streamlit Community Cloud](https://streamlit.io/cloud) (gratuita, sem cartão).
- `psql` instalado localmente (cliente PostgreSQL), para rodar a migração do banco.

---

## 3. Passo 1 — Criar o banco no Neon

1. Crie um projeto no Neon e, dentro dele, um database (o padrão `neondb` criado automaticamente serve).
2. Copie a connection string exibida no dashboard do projeto. O formato esperado é:

```text
postgresql://user:pass@host/db?sslmode=require&channel_binding=require
```

Guarde essa string — ela será usada tanto na migração (Passo 2) quanto na variável `DATABASE_URL` do backend no Render (Passo 3).

---

## 4. Passo 2 — Migrar o schema e os dados

A partir da raiz do repositório, rode o script de migração apontando para a connection string do Neon:

```bash
NEON_DATABASE_URL="postgresql://user:pass@host/db?sslmode=require&channel_binding=require" ./db/migrate_to_neon.sh
```

O script (`db/migrate_to_neon.sh`) aplica, em ordem, `01_schema.sql`, `02_sample_data.sql` e `03_views.sql` via `psql`, e ao final imprime a contagem de linhas das tabelas principais. A saída esperada é:

```text
customers | invoices | payments
-----------+----------+---------
        40 |      793 |     357
```

O próprio script avisa: ele **não é idempotente**. `01_schema.sql` usa `CREATE TABLE` sem `IF NOT EXISTS` e `02_sample_data.sql` usa `INSERT` puro sem proteção contra duplicação. Rode este script apenas uma vez por banco Neon — executá-lo de novo contra o mesmo banco falha em `01_schema.sql` (tabelas já existem) ou duplica os dados de exemplo, caso o schema seja alterado para permitir reexecução.

---

## 5. Passo 3 — Deploy do backend no Render

1. No dashboard do Render, crie um novo **Blueprint** apontando para o repositório GitHub, branch `master`. O Render vai ler o `render.yaml` na raiz do repo automaticamente.
2. Confira que o serviço criado (`gefin-backend`) usa `runtime: docker`, `dockerfilePath: backend/Dockerfile` e `dockerContext: .` — o contexto de build precisa ser a raiz do repositório, não `backend/`, porque o Dockerfile copia `catalog/` de fora da pasta `backend/`.
3. As variáveis `DATABASE_URL` e `ANTHROPIC_API_KEY` estão declaradas como `sync: false` no `render.yaml` — o Render não recebe esses valores do blueprint por segurança. Preencha-as manualmente no dashboard do serviço, em **Environment**:
   - `DATABASE_URL`: a connection string do Neon copiada no Passo 1 (com `sslmode=require&channel_binding=require`).
   - `ANTHROPIC_API_KEY`: sua chave da Anthropic.
4. As demais variáveis (`PORT`, `CATALOG_PATH`, `LLM_PROVIDER`, `LLM_MODEL`, `LOG_LEVEL`, `MAX_AGENT_STEPS`, `SQL_ROW_LIMIT`, `SQL_TIMEOUT_SECONDS`) já vêm preenchidas pelo blueprint.
5. O Render usa `healthCheckPath: /health` para saber quando o deploy está saudável — acompanhe o build no painel de logs até o serviço ficar `Live`.

**Comportamento do free tier:** o serviço entra em modo de espera ("spin down") após 15 minutos sem receber requisições. A próxima requisição após esse período sofre um cold start de cerca de 1 minuto até o container voltar a responder. O plano gratuito do Render oferece 750 horas/mês de execução, suficiente para manter um único serviço rodando o mês inteiro.

---

## 6. Passo 4 — Deploy do frontend no Streamlit Community Cloud

1. No Streamlit Community Cloud, crie um novo app conectado ao mesmo repositório GitHub, branch `master`.
2. Defina o **main file path** como:

```text
frontend/app.py
```

3. Em **Advanced settings → Secrets**, cole o conteúdo abaixo (formato TOML), substituindo pela URL pública do serviço criado no Passo 3:

```toml
BACKEND_URL = "https://<nome-do-servico>.onrender.com"
```

`frontend/app.py` lê essa chave via `_get_secret("BACKEND_URL", "http://localhost:8000")`, que tenta `st.secrets["BACKEND_URL"]` primeiro e só cai para o default local (`http://localhost:8000`) se o secret não existir.

4. Faça o deploy e aguarde o app ficar disponível na URL pública gerada pelo Streamlit Cloud.

---

## 7. Passo 5 — Smoke test

Com o backend e o frontend publicados, valide o fluxo completo:

1. Verifique o health check do backend:

```bash
curl https://<nome-do-servico>.onrender.com/health
```

2. Abra a URL pública do app no Streamlit Community Cloud.
3. Envie a pergunta de teste: `Qual o saldo total em aberto?`
4. Confira que a resposta chega em até aproximadamente 60 segundos — esse teto já contempla o cold start do Render (~1 min) caso o backend estivesse parado.

---

## 8. Variáveis de ambiente

| Variável | Onde é configurada | Descrição |
|----------|---------------------|-----------|
| `PORT` | Render (`render.yaml`, valor fixo) | Porta fixa do Uvicorn (`8000`), declarada explicitamente para evitar depender da autodetecção do Render. |
| `DATABASE_URL` | Render (`sync: false`, manual) | Connection string do Neon (`postgresql://...?sslmode=require&channel_binding=require`). |
| `CATALOG_PATH` | Render (`render.yaml`, valor fixo) | Caminho do `metrics.yaml` dentro da imagem Docker (`/app/catalog/metrics.yaml`), copiado em build-time. |
| `LLM_PROVIDER` | Render (`render.yaml`, valor fixo) | Provedor de LLM (`anthropic`). |
| `LLM_MODEL` | Render (`render.yaml`, valor fixo) | Modelo usado (`claude-sonnet-4-20250514`). |
| `ANTHROPIC_API_KEY` | Render (`sync: false`, manual) | Chave de API da Anthropic. |
| `LOG_LEVEL` | Render (`render.yaml`, valor fixo) | Nível de log (`INFO`). |
| `MAX_AGENT_STEPS` | Render (`render.yaml`, valor fixo) | Limite de passos do loop do agente (`6`). |
| `SQL_ROW_LIMIT` | Render (`render.yaml`, valor fixo) | Limite de linhas retornadas por query (`500`). |
| `SQL_TIMEOUT_SECONDS` | Render (`render.yaml`, valor fixo) | Timeout de execução de SQL em segundos (`30`). |
| `BACKEND_URL` | Streamlit Community Cloud (Secrets, TOML) | URL pública do backend no Render, lida via `st.secrets` pelo frontend. |

---

## 9. Limitações conhecidas

- **Cold start do Render:** após 15 minutos de inatividade o backend "dorme"; a primeira requisição seguinte leva até ~1 minuto para responder.
- **Sessões de chat em memória:** o histórico de conversa é mantido em memória do processo (`memory.py`); qualquer reinício do backend (deploy novo ou saída do cold start) zera as sessões ativas.
- **Sem autenticação:** o app é público — qualquer pessoa com o link do Streamlit Community Cloud tem acesso ao chat.
- **Sem CI/testes automatizados antes do deploy:** não há pipeline que rode testes antes de publicar mudanças na `master`; validação hoje é manual, via o smoke test da seção 7. Candidata a próxima feature.

---

## 10. Troubleshooting

**`/catalog` retorna vazio ou erro no backend**
Confira se o build do Render usou `dockerContext: .` (raiz do repositório) e não `backend/`. Sem isso, `COPY catalog ./catalog` no `backend/Dockerfile` não encontra a pasta `catalog/`, e `CATALOG_PATH=/app/catalog/metrics.yaml` fica vazio.

**Erro 401 ao chamar a LLM**
Confira o valor de `ANTHROPIC_API_KEY` no dashboard do Render (Environment). Como essa variável é `sync: false`, ela não vem do `render.yaml` e precisa ser preenchida manualmente após a criação do serviço.

**Frontend não consegue conectar ao backend**
Confira o valor de `BACKEND_URL` em Secrets, no Streamlit Community Cloud. Ele precisa ser a URL pública completa do serviço no Render (`https://<nome-do-servico>.onrender.com`), no formato TOML `BACKEND_URL = "..."`. Se o backend estava em cold start, aguarde até 1 minuto e tente novamente antes de assumir erro de configuração.
