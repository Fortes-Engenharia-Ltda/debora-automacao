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

from extractor import extrair_dados_pdf, COLUNAS


# extrair_dados_pdf agora é provido por extractor.py


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

        col_widths = {
            "ID": 8,
            "Empresa Principal": 28,
            "Empresa Referência": 25,
            "Ped. de Compra": 16,
            "Área": 8,
            "Descrição Área": 30,
            "Período": 10,
            "Adm. Resp.": 25,
            "Tipo Despesa": 42,
            "Qtd": 8,
            "Valor Total": 16,
        }
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

    COLUNAS = [
        "ID", "Empresa Principal", "Empresa Referência", "Ped. de Compra",
        "Área", "Descrição Área", "Período", "Adm. Resp.",
        "Tipo Despesa", "Qtd", "Valor Total",
    ]
    df = pd.DataFrame(todos_dados, columns=COLUNAS)

    if not args.include_zeros:
        df = df[~((df["Qtd"] == 0) & (df["Valor Total"] == 0))]

    df = df.sort_values(["ID", "Empresa Principal", "Empresa Referência", "Tipo Despesa"]).reset_index(drop=True)

    gerar_excel(df, args.output)

    print(json.dumps({
        "success": True,
        "rows": len(df),
        "files": len(args.pdfs),
        "errors": todos_erros
    }))


if __name__ == "__main__":
    main()
