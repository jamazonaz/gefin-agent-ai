"""GEFIN Agent - Streamlit Chat UI (prototype)."""

from __future__ import annotations

import os
from typing import Any

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

def _get_secret(key: str, default: str) -> str:
    """Lê de st.secrets (Streamlit Cloud) com fallback para os.getenv (Docker local)."""
    try:
        return st.secrets[key]
    except Exception:
        return os.getenv(key, default)


st.set_page_config(
    page_title="GEFIN Agent",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

BACKEND_URL = _get_secret("BACKEND_URL", "http://localhost:8000")

st.title("GEFIN Agent")
st.caption("Agentic Analytics · Contas a Receber · Protótipo local com governança e linhagem")

# Session state
if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "domain" not in st.session_state:
    st.session_state.domain = "ar"

DOMAIN_LABELS = {
    "ar": "Contas a Receber",
    "fabric": "Fabric — Pipeline de Vendas",
}


def call_chat(message: str) -> dict[str, Any]:
    payload = {
        "message": message,
        "session_id": st.session_state.session_id,
        "domain": st.session_state.domain,
    }
    r = requests.post(f"{BACKEND_URL}/chat", json=payload, timeout=180)
    r.raise_for_status()
    return r.json()


def render_chart(spec: dict[str, Any]):
    data = spec.get("data") or []
    if not data:
        return
    df = pd.DataFrame(data)
    x = spec.get("x_key")
    y = spec.get("y_key")
    title = spec.get("title", "")
    chart_type = spec.get("chart_type", "bar")

    if chart_type == "pie":
        fig = px.pie(df, names=x, values=y, title=title)
    elif chart_type == "line":
        fig = px.line(df, x=x, y=y, title=title, markers=True)
    else:
        fig = px.bar(df, x=x, y=y, title=title)
    st.plotly_chart(fig, use_container_width=True)


def render_lineage(lineage: dict[str, Any] | None):
    if not lineage:
        return
    with st.expander("📍 Origem do dado (linhagem)", expanded=True):
        st.markdown(f"**Camada:** `{lineage.get('layer', '—')}`")
        st.markdown(f"**Sistema de origem:** {lineage.get('source_system', '—')}")
        views = lineage.get("views") or []
        if views:
            st.markdown("**Views utilizadas:**")
            for v in views:
                st.markdown(f"- `{v.get('view')}` — {v.get('description') or ''}")
        if lineage.get("sql"):
            st.code(lineage["sql"], language="sql")
        if lineage.get("note"):
            st.info(lineage["note"])


# Sidebar
with st.sidebar:
    st.header("Assistente")
    selected_domain = st.selectbox(
        "Escolha o assistente",
        options=list(DOMAIN_LABELS.keys()),
        format_func=lambda d: DOMAIN_LABELS[d],
        index=list(DOMAIN_LABELS.keys()).index(st.session_state.domain),
    )
    if selected_domain != st.session_state.domain:
        st.session_state.domain = selected_domain
        st.session_state.session_id = None
        st.session_state.messages = []
        st.rerun()

    st.divider()
    st.header("Sobre")
    st.markdown(
        """
        **GEFIN Agent** é um protótipo de sistema **agentic** para analytics financeiro.

        - Linguagem natural → SQL governado
        - Apenas views semânticas (whitelist)
        - Linhagem visível em toda resposta
        - 100% local (Docker + Ollama)
        """
    )
    st.divider()
    st.subheader("Exemplos de perguntas")
    ar_examples = [
        "Qual o saldo total em aberto?",
        "Mostre o aging por faixa de atraso",
        "Quais os 5 clientes com maior saldo a receber?",
        "Qual o DSO atual?",
        "Evolução do saldo em aberto nos últimos 90 dias",
    ]
    fabric_examples = [
        "Qual o Revenue Won total?",
        "Como está o Win/Loss Ratio?",
        "Qual o forecast do pipeline atual?",
    ]
    examples = ar_examples if st.session_state.domain == "ar" else fabric_examples
    for ex in examples:
        if st.button(ex, use_container_width=True):
            st.session_state._pending = ex

    st.divider()
    if st.button("Nova sessão", use_container_width=True):
        st.session_state.session_id = None
        st.session_state.messages = []
        st.rerun()

    st.caption("Backend: " + BACKEND_URL)


# Render history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("data"):
            st.dataframe(pd.DataFrame(msg["data"]), use_container_width=True)
        if msg.get("chart_spec"):
            render_chart(msg["chart_spec"])
        if msg.get("lineage"):
            render_lineage(msg["lineage"])


# Handle pending example click
pending = st.session_state.pop("_pending", None)
user_input = st.chat_input("Pergunte sobre contas a receber…") or pending

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Agente pensando (plan → tools → reflect)…"):
            try:
                resp = call_chat(user_input)
                st.session_state.session_id = resp.get("session_id")

                answer = resp.get("answer", "")
                st.markdown(answer)

                data = resp.get("data")
                if data:
                    st.dataframe(pd.DataFrame(data), use_container_width=True)

                chart_spec = resp.get("chart_spec")
                if chart_spec:
                    render_chart(chart_spec)

                lineage = resp.get("lineage")
                render_lineage(lineage)

                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": answer,
                        "data": data,
                        "chart_spec": chart_spec,
                        "lineage": lineage,
                    }
                )
            except Exception as e:
                st.error(f"Erro ao falar com o backend: {e}")
                st.info("Verifique se `docker compose up` está rodando e se o modelo do Ollama foi baixado.")
