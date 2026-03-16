#!/usr/bin/env python3
"""
Script CLI para processar PDFs de Reembolso de Despesas.
Chamado pelo servidor Node.js com:
  python3 process_pdfs.py <caminho_pdf1> <caminho_pdf2> ... --output <caminho_saida.xlsx>
Retorna JSON com status e erros para stdout.
"""

import sys
import json
import re
import io
import traceback
import argparse
from pathlib import Path

try:
    import pdfplumber
    import pandas as pd
except ImportError as e:
    print(json.dumps({"success": False, "error": f"Missing dependency: {e}"}))
    sys.exit(1)


def extrair_dados_pdf(pdf_path: str):
    linhas = []
    erros = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            texto_completo = ""
            todas_tabelas = []

            for pagina in pdf.pages:
                texto_completo += pagina.extract_text() or ""
                tabelas = pagina.extract_tables()
                if tabelas:
                    todas_tabelas.extend(tabelas)

            # --- ID ---
            id_valor = None
            match_id = re.search(r'\bID\b[\s\t]+(\d+)', texto_completo)
            if not match_id:
                match_id = re.search(r'\bID\b\s*\n\s*(\d+)', texto_completo)
            if match_id:
                id_valor = match_id.group(1).strip()

            # --- Empresa Referência ---
            empresa = None
            match_emp = re.search(
                r'Empresa\s+Referência\s*[:\-]?\s*(.+?)(?:\n|Ped\.|$)',
                texto_completo, re.IGNORECASE
            )
            if match_emp:
                empresa = match_emp.group(1).strip()

            nome_arquivo = Path(pdf_path).name
            if not id_valor or not empresa:
                erros.append(
                    f"{nome_arquivo}: Não foi possível extrair ID ({id_valor}) "
                    f"ou Empresa ({empresa})."
                )

            # --- Tabela de despesas ---
            for tabela in todas_tabelas:
                if not tabela:
                    continue

                cabecalho_idx = None
                for i, linha in enumerate(tabela):
                    linha_texto = " ".join(str(c).lower() for c in linha if c)
                    if "tipo despesa" in linha_texto and "qtd" in linha_texto:
                        cabecalho_idx = i
                        break

                if cabecalho_idx is None:
                    continue

                cabecalho = tabela[cabecalho_idx]
                col_tipo, col_qtd, col_valor = 0, 1, 2

                for j, col in enumerate(cabecalho):
                    col_norm = str(col).lower().strip() if col else ""
                    if "tipo" in col_norm and "despesa" in col_norm:
                        col_tipo = j
                    elif col_norm in ("qtd", "quantidade", "qtde"):
                        col_qtd = j
                    elif "valor" in col_norm and "total" in col_norm:
                        col_valor = j

                for linha in tabela[cabecalho_idx + 1:]:
                    if not linha or all(c is None or str(c).strip() == "" for c in linha):
                        continue

                    tipo = linha[col_tipo] if col_tipo < len(linha) else None
                    qtd_raw = linha[col_qtd] if col_qtd < len(linha) else None
                    valor_raw = linha[col_valor] if col_valor < len(linha) else None

                    if not tipo or str(tipo).strip() == "":
                        continue

                    tipo_str = str(tipo).strip()
                    if re.search(r'total\s+desconto', tipo_str, re.IGNORECASE):
                        continue

                    qtd_str = str(qtd_raw).strip() if qtd_raw else "0"
                    qtd_str = re.sub(r'[^\d.,]', '', qtd_str).replace('.', '').replace(',', '.')
                    try:
                        qtd = float(qtd_str) if qtd_str else 0.0
                    except ValueError:
                        qtd = 0.0

                    valor_str = str(valor_raw).strip() if valor_raw else "0"
                    valor_str = re.sub(r'R\$\s*', '', valor_str)
                    valor_str = valor_str.replace(' ', '').strip()
                    if valor_str in ('-', '', 'None'):
                        valor_str = "0"
                    valor_str = valor_str.replace('.', '').replace(',', '.')
                    valor_str = re.sub(r'[^\d.]', '', valor_str)
                    try:
                        valor = float(valor_str) if valor_str else 0.0
                    except ValueError:
                        valor = 0.0

                    linhas.append({
                        "ID": id_valor or "",
                        "Empresa Referência": empresa or "",
                        "Tipo Despesa": tipo_str,
                        "Qtd": qtd,
                        "Valor Total": valor,
                    })

    except Exception as e:
        nome_arquivo = Path(pdf_path).name
        erros.append(f"{nome_arquivo}: Erro — {str(e)}")

    return linhas, erros


def gerar_excel(df: pd.DataFrame, output_path: str):
    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Reembolsos")
        workbook = writer.book
        worksheet = writer.sheets["Reembolsos"]

        header_fmt = workbook.add_format({
            "bold": True, "bg_color": "#1F4E79", "font_color": "#FFFFFF",
            "border": 1, "align": "center", "valign": "vcenter",
        })
        cell_fmt = workbook.add_format({"border": 1, "align": "left", "valign": "vcenter"})
        num_fmt = workbook.add_format({
            "border": 1, "align": "right", "valign": "vcenter", "num_format": "#,##0.00",
        })
        qtd_fmt = workbook.add_format({
            "border": 1, "align": "center", "valign": "vcenter", "num_format": "#,##0",
        })

        col_widths = {"ID": 10, "Empresa Referência": 30, "Tipo Despesa": 45, "Qtd": 10, "Valor Total": 18}
        colunas = list(df.columns)

        for col_idx, col_nome in enumerate(colunas):
            worksheet.write(0, col_idx, col_nome, header_fmt)
            worksheet.set_column(col_idx, col_idx, col_widths.get(col_nome, 20))

        for row_idx, row in df.iterrows():
            excel_row = row_idx + 1
            for col_idx, col_nome in enumerate(colunas):
                valor = row[col_nome]
                if col_nome == "Valor Total":
                    worksheet.write_number(excel_row, col_idx, float(valor) if valor else 0, num_fmt)
                elif col_nome == "Qtd":
                    worksheet.write_number(excel_row, col_idx, float(valor) if valor else 0, qtd_fmt)
                else:
                    worksheet.write(excel_row, col_idx, str(valor), cell_fmt)

        worksheet.freeze_panes(1, 0)
        worksheet.autofilter(0, 0, len(df), len(colunas) - 1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pdfs", nargs="+", help="Caminhos dos PDFs")
    parser.add_argument("--output", required=True, help="Caminho de saída do Excel")
    parser.add_argument("--include-zeros", action="store_true", help="Incluir linhas com Qtd=0")
    args = parser.parse_args()

    todos_dados = []
    todos_erros = []

    for pdf_path in args.pdfs:
        linhas, erros = extrair_dados_pdf(pdf_path)
        todos_dados.extend(linhas)
        todos_erros.extend(erros)

    if not todos_dados:
        print(json.dumps({
            "success": False,
            "error": "Nenhum dado extraído dos PDFs",
            "errors": todos_erros
        }))
        sys.exit(1)

    df = pd.DataFrame(todos_dados, columns=["ID", "Empresa Referência", "Tipo Despesa", "Qtd", "Valor Total"])

    if not args.include_zeros:
        df = df[~((df["Qtd"] == 0) & (df["Valor Total"] == 0))]

    df = df.sort_values(["ID", "Empresa Referência", "Tipo Despesa"]).reset_index(drop=True)

    gerar_excel(df, args.output)

    print(json.dumps({
        "success": True,
        "rows": len(df),
        "files": len(args.pdfs),
        "errors": todos_erros
    }))


if __name__ == "__main__":
    main()
