import re
import io
from pathlib import Path

try:
    import pdfplumber
except Exception:
    pdfplumber = None

# Colunas padrão usadas pelo processamento em lote e pela UI
COLUNAS = [
    "ID", "Empresa Principal", "Empresa Referência", "Ped. de Compra",
    "Área", "Descrição Área", "Período", "Adm. Resp.",
    "Tipo Despesa", "Qtd", "Valor Total",
]


def _open_pdf_source(source):
    """Abre um objeto pdfplumber a partir de caminho ou bytes."""
    if pdfplumber is None:
        raise RuntimeError("pdfplumber não está disponível")

    if isinstance(source, (bytes, bytearray)):
        return pdfplumber.open(io.BytesIO(source))
    else:
        # assume caminho
        return pdfplumber.open(source)


def _extrair_campos(texto_completo):
    def extrair_campo(padrao, texto, flags=re.IGNORECASE):
        m = re.search(padrao, texto, flags)
        return m.group(1).strip() if m else ""

    empresa_principal = extrair_campo(r'Empresa\s+Principal\s*[:\-]?\s*(.+?)(?:\n|$)', texto_completo)
    empresa = extrair_campo(r'Empresa\s+Referência\s*[:\-]?\s*(.+?)(?:\n|Ped\.|$)', texto_completo) or None
    ped_compra = extrair_campo(r'Ped\.?\s*de\s*Compra\s*[:\-]?\s*(.+?)(?:\n|$)', texto_completo)
    area = extrair_campo(r'(?<!\w)Área\s*[:\-]?\s*(.+?)(?:\n|$)', texto_completo)
    descricao_area = extrair_campo(r'Descrição\s+Área\s*[:\-]?\s*(.+?)(?:\n|$)', texto_completo)
    periodo = extrair_campo(r'Período\s*[:\-]?\s*(.+?)(?:\n|$)', texto_completo)
    adm_resp = extrair_campo(r'Adm\.?\s*Resp\.?\s*[:\-]?\s*(.+?)(?:\n|$)', texto_completo)

    return {
        "Empresa Principal": empresa_principal,
        "Empresa Referência": empresa,
        "Ped. de Compra": ped_compra,
        "Área": area,
        "Descrição Área": descricao_area,
        "Período": periodo,
        "Adm. Resp.": adm_resp,
    }


def _process_tables(todas_tabelas, id_valor, empresa):
    linhas = []
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
                "Empresa Principal": "",
                "Empresa Referência": empresa or "",
                "Ped. de Compra": "",
                "Área": "",
                "Descrição Área": "",
                "Período": "",
                "Adm. Resp.": "",
                "Tipo Despesa": tipo_str,
                "Qtd": qtd,
                "Valor Total": valor,
            })

    return linhas


def extrair_dados_pdf(pdf_path: str):
    """Extrai dados de um PDF dado o caminho do arquivo (compatível com process_pdfs.py)."""
    linhas = []
    erros = []

    try:
        with _open_pdf_source(pdf_path) as pdf:
            texto_completo = ""
            todas_tabelas = []

            for pagina in pdf.pages:
                texto_completo += pagina.extract_text() or ""
                tabelas = pagina.extract_tables()
                if tabelas:
                    todas_tabelas.extend(tabelas)

            # ID
            id_valor = None
            match_id = re.search(r'\bID\b[\s\t]+(\d+)', texto_completo)
            if not match_id:
                match_id = re.search(r'\bID\b\s*\n\s*(\d+)', texto_completo)
            if match_id:
                id_valor = match_id.group(1).strip()

            campos = _extrair_campos(texto_completo)

            if not id_valor or not campos.get("Empresa Referência"):
                nome_arquivo = Path(pdf_path).name
                erros.append(
                    f"{nome_arquivo}: Não foi possível extrair ID ({id_valor}) ou Empresa ({campos.get('Empresa Referência')})."
                )

            linhas = _process_tables(todas_tabelas, id_valor, campos.get("Empresa Referência"))

            # Preencher campos comuns em cada linha
            for linha in linhas:
                for k, v in campos.items():
                    if k in linha and (linha[k] == "" or linha[k] is None):
                        linha[k] = v

    except Exception as e:
        nome_arquivo = Path(pdf_path).name
        erros.append(f"{nome_arquivo}: Erro — {str(e)}")

    return linhas, erros


def extrair_dados_pdf_bytes(pdf_bytes: bytes, nome_arquivo: str):
    """Extrai dados de um PDF a partir de bytes (compatível com `app.py`)."""
    linhas = []
    erros = []

    try:
        with _open_pdf_source(pdf_bytes) as pdf:
            texto_completo = ""
            todas_tabelas = []

            for pagina in pdf.pages:
                texto_completo += pagina.extract_text() or ""
                tabelas = pagina.extract_tables()
                if tabelas:
                    todas_tabelas.extend(tabelas)

            id_valor = None
            match_id = re.search(r'\bID\b[\s\t]+(\d+)', texto_completo)
            if not match_id:
                match_id = re.search(r'\bID\b\s*\n\s*(\d+)', texto_completo)
            if match_id:
                id_valor = match_id.group(1).strip()

            campos = _extrair_campos(texto_completo)

            if not id_valor or not campos.get("Empresa Referência"):
                erros.append(
                    f"{nome_arquivo}: Não foi possível extrair ID ({id_valor}) ou Empresa ({campos.get('Empresa Referência')})."
                )

            linhas = _process_tables(todas_tabelas, id_valor, campos.get("Empresa Referência"))

            for linha in linhas:
                for k, v in campos.items():
                    if k in linha and (linha[k] == "" or linha[k] is None):
                        linha[k] = v

    except Exception as e:
        erros.append(f"{nome_arquivo}: Erro ao processar — {str(e)}")

    return linhas, erros
