#!/usr/bin/env python3
"""
Lê as credenciais do Google do .env ou .env.example e gera um arquivo
para você copiar as variáveis para a Vercel (produção).

Uso (na raiz do backend):
  python scripts/copiar_google_para_vercel.py

Gera: vercel_env_google.txt (no .gitignore) com nome e valor de cada variável.
Depois: Vercel Dashboard → projeto backend → Settings → Environment Variables
        → adicione cada linha em Production.
"""

import os
from pathlib import Path

# Raiz do backend (onde está .env / .env.example)
ROOT = Path(__file__).resolve().parent.parent
OUT_FILE = ROOT / "vercel_env_google.txt"

VARIAVEIS = [
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "GOOGLE_REDIRECT_URI",
]


def carregar_env() -> dict[str, str]:
    """Carrega variáveis de .env.example e depois .env (local sobrescreve)."""
    env = {}
    # Ordem: .env.example primeiro (geralmente tem valores de produção),
    # depois .env (sobrescreve se existir)
    for nome_arquivo in (".env.example", ".env"):
        path = ROOT / nome_arquivo
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key in VARIAVEIS:
                        env[key] = value
    return env


def main():
    os.chdir(ROOT)
    env = carregar_env()

    faltando = [v for v in VARIAVEIS if v not in env or not env[v]]
    if faltando:
        print("Aviso: variáveis não encontradas ou vazias:", ", ".join(faltando))
        print("Use .env ou .env.example com essas chaves preenchidas.\n")

    lines = [
        "# Copie as variáveis abaixo para a Vercel (Production)",
        "# Vercel Dashboard → projeto backend → Settings → Environment Variables",
        "# Adicione cada variável com o nome e o valor correspondente.",
        "# Depois faça Redeploy do projeto.",
        "",
    ]
    for var in VARIAVEIS:
        valor = env.get(var, "")
        lines.append(f"{var}={valor}")
        lines.append("")

    OUT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"Arquivo gerado: {OUT_FILE}")
    print("Abra o arquivo e copie cada variável para a Vercel (Environment Variables).")
    print("Guia completo: docs/VERCEL_GOOGLE_PRODUCAO.md")


if __name__ == "__main__":
    main()
