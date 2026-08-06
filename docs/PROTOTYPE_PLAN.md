# GEFIN Agent — Plano de Protótipo (Docker) para Portfólio

**Status:** Alinhado com a implementação atual (2026-08-06)

---

## 1. Visão do Protótipo

Um analista financeiro abre `http://localhost:8501`, digita em português:

> “Qual o saldo total em aberto e o aging? Mostre um gráfico por faixa de atraso.”

O agente:
1. Consulta o catálogo
2. Gera e executa SQL seguro nas views
3. Valida o resultado
4. Gera o gráfico
5. Devolve resposta + tabela + gráfico + **bloco de linhagem**

---

## 2. Serviços no `docker-compose.yml`

| Serviço    | Imagem / Build     | Porta | Função                          | Obrigatório? |
|------------|--------------------|-------|---------------------------------|--------------|
| `db`       | `postgres:16`      | 5432  | Dados + views + audit_log       | Sim          |
| `backend`  | build `./backend`  | 8000  | FastAPI + agente ReAct          | Sim          |
| `frontend` | build `./frontend` | 8501  | Streamlit chat                  | Sim          |
| `adminer`  | `adminer`          | 8080  | Explorar o banco                | Opcional     |
| `ollama`   | `ollama/ollama`    | 11434 | LLM local                       | Só com `--profile ollama` |

---

## 3. Setup (caminho principal: Claude)

```bash
cd gefin-agent
cp .env.example .env
# Editar .env:
#   LLM_PROVIDER=anthropic
#   LLM_MODEL=claude-sonnet-4-20250514
#   ANTHROPIC_API_KEY=sk-ant-...

docker compose up --build
```

Acessar:
- Chat: http://localhost:8501
- API docs: http://localhost:8000/docs
- Adminer: http://localhost:8080

### Alternativa: Ollama 100% local

```bash
# No .env: LLM_PROVIDER=ollama e LLM_MODEL=qwen2.5:14b
docker compose --profile ollama up --build
docker compose exec ollama ollama pull qwen2.5:14b
```

---

## 4. LLM — opções suportadas

| Provider    | Qualidade tool calling | Quando usar                    |
|-------------|------------------------|--------------------------------|
| **Claude** (padrão) | Excelente         | Demo de portfólio, qualidade   |
| OpenAI      | Excelente              | Se já tiver chave OpenAI       |
| Ollama      | Boa (modelo ≥ 8B)      | Demo offline / sem custo de API|

Configuração via `.env` → `LLM_PROVIDER` + chave correspondente.

---

## 5. Dados de Exemplo

**Tabelas brutas (não expostas):**
- `customers`, `invoices`, `payments`

**Views semânticas (únicas que o agente consulta):**
- `vw_ar_open_items`, `vw_ar_aging`, `vw_ar_customer_summary`, `vw_ar_kpi_daily`, `vw_ar_dso`

**Catálogo:** `catalog/metrics.yaml`

---

## 6. Status de implementação

| Fase | Conteúdo | Status |
|------|----------|--------|
| A — Fundação | docker-compose, schema, sample data, views, catálogo | ✅ |
| B — Tools + Agente | execute_sql (guardrails), catalog tools, loop ReAct, /chat | ✅ |
| C — Frontend + Linhagem | Streamlit, Plotly, bloco de linhagem, histórico | ✅ |
| D — Polimento | README, .env.example, docs alinhados, Claude como padrão | ✅ |
| E — Validação | Lista real de perguntas + ajustes de prompt | ⏳ Próximo |

---

## 7. Diferenciais de portfólio

- Linhagem visível em toda resposta
- Arquitetura agentic real (tools + planning + reflection)
- Guardrails de SQL (sqlglot + whitelist)
- Claude / OpenAI / Ollama configuráveis
- Tudo reproduzível com Docker
- Documentação clara e caminho de evolução (Fase 2)

---

## 8. Próximos passos sugeridos

1. Colocar a `ANTHROPIC_API_KEY` no `.env` e validar o fluxo ponta a ponta
2. Testar as perguntas de exemplo da sidebar
3. Ajustar prompts / few-shots se alguma métrica falhar
4. (Opcional) Adicionar testes unitários das tools de SQL
5. (Opcional) Trocar Streamlit por Next.js para visual de produto

---

*Documento alinhado com o código em `gefin-agent/` (2026-08-06).*
