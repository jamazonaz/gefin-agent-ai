"""GEFIN Agent - Chainlit chat UI, mounted inside the FastAPI backend."""

from __future__ import annotations

import os
from typing import Any

import chainlit as cl
import pandas as pd
import plotly.express as px

from app.agent.graph import run_agent
from app.audit.logger import write_audit

APP_USERNAME = os.getenv("APP_USERNAME")
APP_PASSWORD = os.getenv("APP_PASSWORD")

AR_STARTERS = [
    cl.Starter(label="Qual o saldo total em aberto?", message="Qual o saldo total em aberto?"),
    cl.Starter(
        label="Mostre o aging por faixa de atraso", message="Mostre o aging por faixa de atraso"
    ),
    cl.Starter(
        label="Quais os 5 clientes com maior saldo a receber?",
        message="Quais os 5 clientes com maior saldo a receber?",
    ),
    cl.Starter(label="Qual o DSO atual?", message="Qual o DSO atual?"),
    cl.Starter(
        label="Evolução do saldo em aberto nos últimos 90 dias",
        message="Evolução do saldo em aberto nos últimos 90 dias",
    ),
]

FABRIC_STARTERS = [
    cl.Starter(label="Qual o Revenue Won total?", message="Qual o Revenue Won total?"),
    cl.Starter(label="Como está o Win/Loss Ratio?", message="Como está o Win/Loss Ratio?"),
    cl.Starter(
        label="Qual o forecast do pipeline atual?", message="Qual o forecast do pipeline atual?"
    ),
]


@cl.password_auth_callback
def auth_callback(username: str, password: str) -> cl.User | None:
    if APP_USERNAME and APP_PASSWORD and username == APP_USERNAME and password == APP_PASSWORD:
        return cl.User(identifier=username)
    return None


@cl.data_layer
def data_layer() -> None:
    # Chainlit auto-enables its own chat-persistence data layer whenever
    # DATABASE_URL is set, which collides with this app's own Postgres
    # connection (used for views/audit_log, not Chainlit's schema).
    # Registering this callback short-circuits that auto-detection.
    return None


@cl.set_chat_profiles
async def chat_profiles(_user: cl.User | None) -> list[cl.ChatProfile]:
    return [
        cl.ChatProfile(
            name="ar",
            markdown_description="Contas a Receber",
            default=True,
            starters=AR_STARTERS,
        ),
        cl.ChatProfile(
            name="fabric",
            markdown_description="Fabric — Pipeline de Vendas",
            starters=FABRIC_STARTERS,
        ),
    ]


@cl.on_chat_start
async def on_chat_start() -> None:
    domain = cl.user_session.get("chat_profile") or "ar"
    cl.user_session.set("domain", domain)


def _render_chart(chart_spec: dict[str, Any]) -> cl.Plotly | None:
    data = chart_spec.get("data") or []
    if not data:
        return None
    df = pd.DataFrame(data)
    x = chart_spec.get("x_key")
    y = chart_spec.get("y_key")
    title = chart_spec.get("title", "")
    chart_type = chart_spec.get("chart_type", "bar")

    if chart_type == "pie":
        fig = px.pie(df, names=x, values=y, title=title)
    elif chart_type == "line":
        fig = px.line(df, x=x, y=y, title=title, markers=True)
    else:
        fig = px.bar(df, x=x, y=y, title=title)
    return cl.Plotly(name="grafico", figure=fig, display="inline")


def _render_lineage_markdown(lineage: dict[str, Any] | None) -> str | None:
    # Chainlit's markdown renderer does not interpret raw HTML (no <details>
    # disclosure widget), so this renders as a plain, always-visible section —
    # matching the old Streamlit expander's default (expanded=True) behavior.
    if not lineage:
        return None
    views = lineage.get("views") or []
    views_md = "\n".join(f"- `{v.get('view')}` — {v.get('description') or ''}" for v in views)
    sql_md = f"\n\n```sql\n{lineage['sql']}\n```" if lineage.get("sql") else ""
    note_md = f"\n\n{lineage['note']}" if lineage.get("note") else ""
    return (
        "---\n**📍 Origem do dado (linhagem)**\n\n"
        f"**Camada:** `{lineage.get('layer', '—')}`\n\n"
        f"**Sistema de origem:** {lineage.get('source_system', '—')}\n\n"
        f"{views_md}{sql_md}{note_md}"
    )


@cl.on_message
async def on_message(message: cl.Message) -> None:
    session_id = cl.user_session.get("id")
    domain = cl.user_session.get("domain", "ar")

    handler = cl.LangchainCallbackHandler(stream_final_answer=True)
    result = await run_agent(
        user_message=message.content,
        session_id=session_id,
        domain=domain,
        config={"callbacks": [handler]},
    )

    elements: list[Any] = []
    if result.get("data"):
        elements.append(
            cl.Dataframe(name="dados", data=pd.DataFrame(result["data"]), display="inline")
        )
    chart_spec = result.get("chart_spec")
    if chart_spec:
        chart_element = _render_chart(chart_spec)
        if chart_element:
            elements.append(chart_element)

    answer = result.get("answer") or "Não foi possível gerar uma resposta."
    lineage_md = _render_lineage_markdown(result.get("lineage"))
    if lineage_md:
        answer = f"{answer}\n\n{lineage_md}"

    await cl.Message(content=answer, elements=elements).send()

    write_audit(
        session_id=session_id,
        user_message=message.content,
        agent_plan=result.get("plan"),
        tools_called=result.get("tools_called"),
        final_sql=result.get("final_sql"),
        response_summary=(result.get("answer") or "")[:500],
        lineage=result.get("lineage"),
        latency_ms=result.get("latency_ms"),
    )
