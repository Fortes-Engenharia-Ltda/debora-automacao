import streamlit as st
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


def extrair_dados_pdf(pdf_bytes, nome_arquivo):
    import pdfplumber
    """
    Extrai ID, Empresa Referência e tabela de despesas de um PDF de reembolso.
    Retorna lista de dicts com as linhas extraídas.
    """
    linhas = []
    erros = []

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            texto_completo = ""
            todas_tabelas = []

            for pagina in pdf.pages:
                texto_completo += pagina.extract_text() or ""
                tabelas = pagina.extract_tables()
                if tabelas:
                    todas_tabelas.extend(tabelas)

            # --- Extração do ID ---
            id_valor = None
            # Padrão: "ID   4310" ou "ID\n4310"
            match_id = re.search(r'\bID\b[\s\t]+(\d+)', texto_completo)
            if not match_id:
                # Tenta variação com quebra de linha
                match_id = re.search(r'\bID\b\s*\n\s*(\d+)', texto_completo)
            if match_id:
                id_valor = match_id.group(1).strip()

            # --- Extração da Empresa Referência ---
            empresa = None
            match_emp = re.search(
                r'Empresa\s+Referência\s*[:\-]?\s*(.+?)(?:\n|Ped\.|$)',
                texto_completo, re.IGNORECASE
            )
            if match_emp:
                empresa = match_emp.group(1).strip()

            if not id_valor or not empresa:
                erros.append(
                    f"⚠️ {nome_arquivo}: Não foi possível extrair ID ({id_valor}) "
                    f"ou Empresa ({empresa}). Verifique o formato do PDF."
                )

            # --- Extração da tabela de despesas ---
            # Procura tabela com colunas "Tipo Despesa", "Qtd", "Valor Total"
            tabela_encontrada = False

            for tabela in todas_tabelas:
                if not tabela:
                    continue

                # Identifica linha de cabeçalho
                cabecalho_idx = None
                for i, linha in enumerate(tabela):
                    linha_texto = " ".join(str(c).lower() for c in linha if c)
                    if "tipo despesa" in linha_texto and "qtd" in linha_texto:
                        cabecalho_idx = i
                        break

                if cabecalho_idx is None:
                    continue

                cabecalho = tabela[cabecalho_idx]

                # Identifica índices das colunas de interesse
                col_tipo = None
                col_qtd = None
                col_valor = None

                for j, col in enumerate(cabecalho):
                    col_norm = str(col).lower().strip() if col else ""
                    if "tipo" in col_norm and "despesa" in col_norm:
                        col_tipo = j
                    elif col_norm in ("qtd", "quantidade", "qtde"):
                        col_qtd = j
                    elif "valor" in col_norm and "total" in col_norm:
                        col_valor = j

                # Fallback: assume posições fixas se colunas não identificadas
                if col_tipo is None:
                    col_tipo = 0
                if col_qtd is None:
                    col_qtd = 1
                if col_valor is None:
                    col_valor = 2

                tabela_encontrada = True

                for linha in tabela[cabecalho_idx + 1:]:
                    if not linha or all(c is None or str(c).strip() == "" for c in linha):
                        continue

                    tipo = linha[col_tipo] if col_tipo < len(linha) else None
                    qtd_raw = linha[col_qtd] if col_qtd < len(linha) else None
                    valor_raw = linha[col_valor] if col_valor < len(linha) else None

                    if not tipo or str(tipo).strip() == "":
                        continue

                    tipo_str = str(tipo).strip()

                    # Ignora linhas de total
                    if re.search(r'total\s+desconto', tipo_str, re.IGNORECASE):
                        continue

                    # Limpa quantidade
                    qtd_str = str(qtd_raw).strip() if qtd_raw else "0"
                    qtd_str = re.sub(r'[^\d.,]', '', qtd_str).replace('.', '').replace(',', '.')
                    try:
                        qtd = float(qtd_str) if qtd_str else 0.0
                    except ValueError:
                        qtd = 0.0

                    # Limpa valor
                    valor_str = str(valor_raw).strip() if valor_raw else "0"
                    # Remove "R$" e todos os espaços (PDFs frequentemente inserem espaços nos números)
                    valor_str = re.sub(r'R\$\s*', '', valor_str)
                    valor_str = valor_str.replace(' ', '').strip()
                    if valor_str in ('-', '', 'None'):
                        valor_str = "0"
                    # Formato brasileiro: 1.311,03 → 1311.03
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

            if not tabela_encontrada:
                erros.append(
                    f"⚠️ {nome_arquivo}: Tabela de despesas não encontrada no PDF."
                )

    except Exception as e:
        erros.append(f"❌ {nome_arquivo}: Erro ao processar — {str(e)}\n{traceback.format_exc()}")

    return linhas, erros


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
            linhas, erros = extrair_dados_pdf(pdf_bytes, arquivo.name)
            todos_dados.extend(linhas)
            todos_erros.extend(erros)

        barra.progress(1.0, text="✅ Processamento concluído!")

        if todos_dados:
            df = pd.DataFrame(todos_dados, columns=[
                "ID", "Empresa Referência", "Tipo Despesa", "Qtd", "Valor Total"
            ])

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
