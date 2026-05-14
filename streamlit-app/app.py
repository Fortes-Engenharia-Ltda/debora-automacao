import streamlit as st
import time
import sys

# Startup logs to help remote health checks / deployment debugging
print(f"APP_START {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
import re
import io
import os
import traceback
from pathlib import Path

st.set_page_config(
    page_title="Consolidador de Reembolsos - Projeto Sucuriú",
    page_icon="📄",
    layout="wide"
)

st.title("📄 Consolidador de Reembolso de Despesas")
st.markdown("**Projeto Sucuriú** — Faça upload dos PDFs e baixe a planilha consolidada.")

st.divider()


from extractor import extrair_dados_pdf_bytes, COLUNAS


def gerar_excel(df):
    """Gera o arquivo Excel em memória e retorna os bytes."""
    import pandas as pd
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Reembolsos")

        workbook = writer.book
        worksheet = writer.sheets["Reembolsos"]

        # Formatos
        header_fmt = workbook.add_format({
            "bold": True,
            "bg_color": "#1F4E79",
            "font_color": "#FFFFFF",
            "border": 1,
            "align": "center",
            "valign": "vcenter",
        })
        cell_fmt = workbook.add_format({
            "border": 1,
            "align": "left",
            "valign": "vcenter",
        })
        num_fmt = workbook.add_format({
            "border": 1,
            "align": "right",
            "valign": "vcenter",
            "num_format": "#,##0.00",
        })
        qtd_fmt = workbook.add_format({
            "border": 1,
            "align": "center",
            "valign": "vcenter",
            "num_format": "#,##0",
        })

        # Cabeçalho
        colunas = list(df.columns)
        col_widths = {
            "ID": 10,
            "Empresa Referência": 30,
            "Tipo Despesa": 45,
            "Qtd": 10,
            "Valor Total": 18,
        }
        for col_idx, col_nome in enumerate(colunas):
            worksheet.write(0, col_idx, col_nome, header_fmt)
            width = col_widths.get(col_nome, 20)
            worksheet.set_column(col_idx, col_idx, width)

        # Dados
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

    output.seek(0)
    return output.getvalue()


# ---------- Interface ----------

col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("📂 Upload dos Arquivos PDF")
    arquivos = st.file_uploader(
        "Arraste e solte os PDFs aqui (ou clique para selecionar)",
        type=["pdf"],
        accept_multiple_files=True,
        help="Selecione quantos arquivos PDF desejar de uma vez"
    )

with col2:
    st.subheader("⚙️ Opções")
    incluir_zeros = st.checkbox(
        "Incluir linhas com Qtd = 0",
        value=False,
        help="Se marcado, inclui na planilha itens sem consumo (Qtd = 0 e Valor = 0)"
    )
    st.caption(f"📁 PDFs carregados: **{len(arquivos) if arquivos else 0}**")

st.divider()

if arquivos:
    if st.button("🚀 Processar e Gerar Planilha", type="primary", use_container_width=True):
        import pandas as pd
        todos_dados = []
        todos_erros = []

        barra = st.progress(0, text="Iniciando processamento...")
        container_log = st.container()

        for i, arquivo in enumerate(arquivos):
            barra.progress(
                (i + 1) / len(arquivos),
                text=f"Processando {i+1}/{len(arquivos)}: {arquivo.name}"
            )
            pdf_bytes = arquivo.read()
            linhas, erros = extrair_dados_pdf_bytes(pdf_bytes, arquivo.name)
            todos_dados.extend(linhas)
            todos_erros.extend(erros)

        barra.progress(1.0, text="✅ Processamento concluído!")

        if todos_dados:
            df = pd.DataFrame(todos_dados, columns=COLUNAS)

            if not incluir_zeros:
                df = df[~((df["Qtd"] == 0) & (df["Valor Total"] == 0))]

            df = df.sort_values(["ID", "Empresa Referência", "Tipo Despesa"]).reset_index(drop=True)

            st.success(f"✅ {len(df)} linhas extraídas de {len(arquivos)} arquivos PDF.")

            # Resumo por empresa
            st.subheader("📊 Resumo por Empresa")
            resumo = (
                df.groupby(["ID", "Empresa Referência"])["Valor Total"]
                .sum()
                .reset_index()
                .rename(columns={"Valor Total": "Total Geral (R$)"})
            )
            resumo["Total Geral (R$)"] = resumo["Total Geral (R$)"].map(
                lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            )
            st.dataframe(resumo, use_container_width=True, hide_index=True)

            # Prévia da tabela
            st.subheader("🔍 Prévia dos Dados (primeiras 50 linhas)")
            preview_df = df.head(50).copy()
            preview_df["Valor Total"] = preview_df["Valor Total"].map(
                lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            )
            st.dataframe(preview_df, use_container_width=True, hide_index=True)

            # Gerar e oferecer download
            excel_bytes = gerar_excel(df)
            st.download_button(
                label="⬇️ Baixar reembolso_consolidado.xlsx",
                data=excel_bytes,
                file_name="reembolso_consolidado.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True,
            )
        else:
            st.warning("Nenhum dado foi extraído. Verifique os arquivos enviados.")

        if todos_erros:
            with st.expander(f"⚠️ Log de Avisos/Erros ({len(todos_erros)})", expanded=True):
                for erro in todos_erros:
                    st.warning(erro)

else:
    st.info("👆 Faça o upload dos arquivos PDF acima para começar o processamento.")
    st.markdown("""
    ### Como usar:
    1. Clique em **Browse files** ou arraste os PDFs de Reembolso de Despesas
    2. Escolha se deseja incluir linhas com consumo zero
    3. Clique em **Processar e Gerar Planilha**
    4. Baixe o arquivo `reembolso_consolidado.xlsx`

    ### Dados extraídos:
    | Campo | Origem no PDF |
    |-------|--------------|
    | **ID** | Número no topo do documento |
    | **Empresa Referência** | Campo da tabela de cabeçalho |
    | **Tipo Despesa** | Coluna da tabela principal |
    | **Qtd** | Coluna de quantidade |
    | **Valor Total** | Coluna de valor em R$ |
    """)

st.divider()
st.caption("Projeto Sucuriú — Consolidador de Reembolso de Despesas | Powered by pdfplumber + pandas")
