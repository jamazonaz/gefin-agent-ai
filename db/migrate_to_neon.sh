#!/usr/bin/env bash
# Uso: NEON_DATABASE_URL="postgresql://user:pass@host/db?sslmode=require" ./db/migrate_to_neon.sh
set -euo pipefail

: "${NEON_DATABASE_URL:?Defina NEON_DATABASE_URL antes de rodar este script}"

if ! command -v psql &>/dev/null; then
  echo "Erro: psql não encontrado no PATH. Instale o cliente PostgreSQL antes de continuar." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Aviso: 01_schema.sql usa CREATE TABLE sem IF NOT EXISTS e 02_sample_data.sql usa INSERT puro sem proteção contra duplicação."
echo "Rodar este script mais de uma vez contra o mesmo banco Neon vai falhar em 01_schema.sql (tabelas já existem)"
echo "ou, se o schema for alterado para permitir reexecução, vai duplicar os dados de exemplo em 02_sample_data.sql."
echo "Use este script apenas para a migração inicial (uma única vez) por banco Neon."

for f in 01_schema.sql 02_sample_data.sql 03_views.sql; do
  echo "==> Aplicando $f no Neon..."
  psql "$NEON_DATABASE_URL" -v ON_ERROR_STOP=1 -f "$SCRIPT_DIR/init/$f"
done

echo "==> Verificando contagens..."
psql "$NEON_DATABASE_URL" -c \
  "SELECT (SELECT COUNT(*) FROM customers) customers, (SELECT COUNT(*) FROM invoices) invoices, (SELECT COUNT(*) FROM payments) payments;"

echo "==> Migração concluída."
