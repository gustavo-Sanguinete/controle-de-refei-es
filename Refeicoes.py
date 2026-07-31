import flet as ft
import sqlite3
import os
import base64
from io import BytesIO
from datetime import datetime
import calendar

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

# Em produção (Railway/Render/etc.) essas variáveis vêm do ambiente.
# Localmente, os valores padrão abaixo são usados.
DB_PATH = os.environ.get("DB_PATH", "refeicoes.db")
PORT = int(os.environ.get("PORT", 8550))

# ---------------------------------------------------------------------------
# Identidade visual ARCOM (ARCOM Design System)
# ---------------------------------------------------------------------------
COR_VERDE_ESCURO = "#1F4033"   # fundos escuros, texto primário, autoridade
COR_VERDE_ARCOM = "#007840"    # ações primárias, botões, destaques
COR_VERDE_LIMA = "#BAE64F"     # acentos, friso decorativo
COR_BRANCO = "#FFFFFF"
COR_CINZA_TEXTO = "#636466"
COR_DANGER = "#D13D29"
COR_FUNDO_PAGINA = "#F6F6F6"
COR_BORDA_CARD = "#E6E7E8"

LOGO_ARCOM_URL = "https://www.arcom.com.br/imagens/produtos/Logo_Fundo_Branco.png"

RAIO_PADRAO = 8

MESES_PT = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
]

# Turnos/tipos de refeição disponíveis. Lanche é pouco frequente, mas fica
# disponível na lista normalmente (só aparece nos relatórios com valor 0
# nos dias em que não houve registro).
TURNOS = {
    "almoco": "Almoço",
    "jantar": "Jantar",
    "marmita_almoco": "Marmita do Almoço",
    "marmita_jantar": "Marmita da Janta",
    "lanche": "Lanche",
}


# ---------------------------------------------------------------------------
# Geração de PDF (relatórios para impressão)
# ---------------------------------------------------------------------------

def gerar_pdf_relatorio(titulo, subtitulo, cabecalhos, linhas, rodape_linhas):
    """Gera um PDF em memória com o padrão visual ARCOM e retorna os bytes."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=2 * cm, bottomMargin=2 * cm,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
    )
    estilos = getSampleStyleSheet()

    estilo_marca = ParagraphStyle(
        "Marca", parent=estilos["Heading1"],
        textColor=colors.HexColor(COR_VERDE_ESCURO), fontSize=16, spaceAfter=2,
    )
    estilo_titulo = ParagraphStyle(
        "Titulo", parent=estilos["Heading2"],
        textColor=colors.HexColor(COR_VERDE_ARCOM), fontSize=14, spaceAfter=2,
    )
    estilo_sub = ParagraphStyle(
        "Sub", parent=estilos["Normal"],
        textColor=colors.HexColor(COR_CINZA_TEXTO), fontSize=10, spaceAfter=10,
    )
    estilo_total = ParagraphStyle(
        "Total", parent=estilos["Heading3"],
        textColor=colors.HexColor(COR_VERDE_ESCURO), fontSize=12, spaceBefore=4,
    )

    elementos = [
        Paragraph("ARCOM — Controle de Refeições", estilo_marca),
        Paragraph(titulo, estilo_titulo),
        Paragraph(subtitulo, estilo_sub),
    ]

    dados_tabela = [cabecalhos] + linhas
    tabela = Table(dados_tabela, repeatRows=1)
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(COR_VERDE_ARCOM)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor(COR_BORDA_CARD)),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(COR_FUNDO_PAGINA)]),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    elementos.append(tabela)
    elementos.append(Spacer(1, 14))

    for linha_texto in rodape_linhas:
        elementos.append(Paragraph(linha_texto, estilo_total))

    elementos.append(Spacer(1, 20))
    elementos.append(Paragraph(
        f"Gerado em {datetime.now().strftime('%d/%m/%Y às %H:%M')} — Desenvolvido por G.SANGUINETE",
        ParagraphStyle("Rodape", parent=estilos["Normal"], textColor=colors.HexColor(COR_CINZA_TEXTO), fontSize=8),
    ))

    doc.build(elementos)
    buffer.seek(0)
    return buffer.getvalue()


def abrir_pdf_no_navegador(page: ft.Page, pdf_bytes: bytes):
    """Codifica o PDF em base64 e abre em nova aba (o navegador oferece a opção de imprimir)."""
    b64 = base64.b64encode(pdf_bytes).decode("ascii")
    page.launch_url(f"data:application/pdf;base64,{b64}")


# ---------------------------------------------------------------------------
# Banco de dados
# ---------------------------------------------------------------------------


def get_connection():
    return sqlite3.connect(DB_PATH)


def criar_tabela():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS refeicoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,        -- formato AAAA-MM-DD
            turno TEXT NOT NULL,       -- 'almoco', 'jantar', 'marmita' ou 'lanche'
            inicial INTEGER,
            reposicoes INTEGER,
            pratos_unidade INTEGER,
            unidades_extra INTEGER,
            sobras_pratos INTEGER,
            total INTEGER,
            UNIQUE(data, turno)
        )
    """)
    conn.commit()
    conn.close()


def salvar_refeicao(data, turno, inicial, reposicoes, pratos_unidade,
                     unidades_extra, sobras_pratos, total):
    conn = get_connection()
    conn.execute("""
        INSERT INTO refeicoes
            (data, turno, inicial, reposicoes, pratos_unidade,
             unidades_extra, sobras_pratos, total)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(data, turno) DO UPDATE SET
            inicial=excluded.inicial,
            reposicoes=excluded.reposicoes,
            pratos_unidade=excluded.pratos_unidade,
            unidades_extra=excluded.unidades_extra,
            sobras_pratos=excluded.sobras_pratos,
            total=excluded.total
    """, (data, turno, inicial, reposicoes, pratos_unidade,
          unidades_extra, sobras_pratos, total))
    conn.commit()
    conn.close()


def buscar_ultimos(limite=10):
    conn = get_connection()
    cursor = conn.execute("""
        SELECT data, turno, total FROM refeicoes
        ORDER BY data DESC, turno
        LIMIT ?
    """, (limite,))
    rows = cursor.fetchall()
    conn.close()
    return rows


def buscar_mes(ano, mes):
    conn = get_connection()
    cursor = conn.execute("""
        SELECT data, turno, total FROM refeicoes
        WHERE strftime('%Y', data) = ? AND strftime('%m', data) = ?
        ORDER BY data, turno
    """, (str(ano), f"{mes:02d}"))
    rows = cursor.fetchall()
    conn.close()
    return rows


def buscar_ano(ano):
    conn = get_connection()
    cursor = conn.execute("""
        SELECT
            strftime('%m', data) as mes,
            SUM(CASE WHEN turno IN ('almoco', 'jantar', 'marmita_almoco', 'marmita_jantar') THEN total ELSE 0 END) as total_refeicoes,
            SUM(CASE WHEN turno = 'lanche' THEN total ELSE 0 END) as total_lanches
        FROM refeicoes
        WHERE strftime('%Y', data) = ?
        GROUP BY mes
        ORDER BY mes
    """, (str(ano),))
    rows = cursor.fetchall()
    conn.close()
    return rows


# ---------------------------------------------------------------------------
# Helpers de formatação de data
# ---------------------------------------------------------------------------

def data_br_para_iso(data_br):
    """Converte 'DD/MM/AAAA' para 'AAAA-MM-DD'. Lança ValueError se inválida."""
    dt = datetime.strptime(data_br.strip(), "%d/%m/%Y")
    return dt.strftime("%Y-%m-%d")


def data_iso_para_br(data_iso):
    dt = datetime.strptime(data_iso, "%Y-%m-%d")
    return dt.strftime("%d/%m/%Y")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

def construir_interface(page: ft.Page):
    # ---------------- ABA 1: REGISTRO DIÁRIO ----------------

    turno_dd = ft.Dropdown(
        label="Turno",
        options=[
            ft.dropdown.Option(key=chave, text=nome)
            for chave, nome in TURNOS.items()
        ],
        value="almoco",
        width=200,
    )
    data_field = ft.TextField(
        label="Data (DD/MM/AAAA)",
        value=datetime.now().strftime("%d/%m/%Y"),
        width=200,
    )
    inicial = ft.TextField(label="Quantidade inicial de refeições")
    reposicoes = ft.TextField(label="Quantidade de reposições")
    pratos_unidade = ft.TextField(label="Quantidade de pratos por unidade")
    unidades_extra = ft.TextField(label="Quantidade de unidades extras")
    sobras_pratos = ft.TextField(label="Quantidade de sobras de prato")
    campos_formula = [inicial, reposicoes, pratos_unidade, unidades_extra, sobras_pratos]

    quantidade_simples = ft.TextField(label="Quantidade", visible=False)

    total_refeicoes = ft.TextField(
        label="Total de refeições", disabled=True, color="red"
    )
    mensagem = ft.Text("", color="red", size=16, weight="bold")

    LABELS_SIMPLES = {
        "marmita_almoco": "Quantidade de marmitas (Almoço)",
        "marmita_jantar": "Quantidade de marmitas (Janta)",
        "lanche": "Quantidade de lanches",
    }

    def turno_mudou(e):
        eh_formula = turno_dd.value in ("almoco", "jantar")
        for campo in campos_formula:
            campo.visible = eh_formula
        quantidade_simples.visible = not eh_formula
        if not eh_formula:
            quantidade_simples.label = LABELS_SIMPLES.get(turno_dd.value, "Quantidade")
        page.update()

    turno_dd.on_change = turno_mudou
    turno_dd.on_select = turno_mudou

    historico_col = ft.Column(spacing=4)

    def atualizar_historico():
        historico_col.controls.clear()
        historico_col.controls.append(
            ft.Text("Últimos registros", weight="bold", size=16)
        )
        for data_iso, turno, total in buscar_ultimos(10):
            turno_label = TURNOS.get(turno, turno)
            historico_col.controls.append(
                ft.Text(f"{data_iso_para_br(data_iso)} - {turno_label}: {total}")
            )

    def calcular_e_salvar(e):
        # Validação da data
        try:
            data_iso = data_br_para_iso(data_field.value)
        except (ValueError, AttributeError):
            mensagem.value = "Data inválida. Use o formato DD/MM/AAAA."
            page.update()
            return

        eh_formula = turno_dd.value in ("almoco", "jantar")

        if eh_formula:
            if not inicial.value:
                mensagem.value = "Informe a quantidade inicial."
                page.update()
                return

            for campo in (reposicoes, pratos_unidade, unidades_extra, sobras_pratos):
                if campo.value == "":
                    campo.value = "0"

            try:
                inicial_v = int(inicial.value)
                reposicoes_v = int(reposicoes.value)
                pratos_unidade_v = int(pratos_unidade.value)
                unidades_extra_v = int(unidades_extra.value)
                sobras_pratos_v = int(sobras_pratos.value)
            except ValueError:
                mensagem.value = "Por favor, insira apenas números nos campos."
                page.update()
                return

            total_v = (
                inicial_v
                + reposicoes_v * pratos_unidade_v
                + unidades_extra_v
                - sobras_pratos_v
            )

            salvar_refeicao(
                data_iso, turno_dd.value, inicial_v, reposicoes_v,
                pratos_unidade_v, unidades_extra_v, sobras_pratos_v, total_v
            )
        else:
            if not quantidade_simples.value:
                mensagem.value = "Informe a quantidade."
                page.update()
                return
            try:
                total_v = int(quantidade_simples.value)
            except ValueError:
                mensagem.value = "Por favor, insira apenas números."
                page.update()
                return

            # Marmita/Lanche não usam a fórmula, só registram a quantidade.
            salvar_refeicao(
                data_iso, turno_dd.value, None, None, None, None, None, total_v
            )

        total_refeicoes.value = str(total_v)
        mensagem.value = f"Salvo com sucesso! Total: {total_v}"
        mensagem.color = "green"
        atualizar_historico()
        page.update()

    def limpar(e):
        inicial.value = ""
        reposicoes.value = ""
        pratos_unidade.value = ""
        unidades_extra.value = ""
        sobras_pratos.value = ""
        quantidade_simples.value = ""
        total_refeicoes.value = ""
        mensagem.value = ""
        page.update()

    tab_registro = ft.Column(
        [
            ft.Text("Registro Diário", size=24, weight="bold", color=COR_VERDE_ESCURO),
            ft.Row([turno_dd, data_field]),
            inicial,
            reposicoes,
            pratos_unidade,
            unidades_extra,
            sobras_pratos,
            quantidade_simples,
            ft.Row(
                [
                    ft.ElevatedButton("Calcular e Salvar", on_click=calcular_e_salvar, style=ft.ButtonStyle(bgcolor=COR_VERDE_ARCOM, color=COR_BRANCO, shape=ft.RoundedRectangleBorder(radius=RAIO_PADRAO))),
                    ft.ElevatedButton("Limpar", on_click=limpar),
                ]
            ),
            total_refeicoes,
            mensagem,
            ft.Divider(),
            historico_col,
        ],
        spacing=12,
        scroll=ft.ScrollMode.AUTO,
    )

    # ---------------- ABA 2: RELATÓRIO MENSAL ----------------

    ano_atual = datetime.now().year
    anos_opcoes = [ft.dropdown.Option(str(a)) for a in range(ano_atual - 2, ano_atual + 2)]
    meses_opcoes = [ft.dropdown.Option(key=str(i + 1), text=nome) for i, nome in enumerate(MESES_PT)]

    mes_dd = ft.Dropdown(label="Mês", options=meses_opcoes, value=str(datetime.now().month), width=180)
    ano_mensal_dd = ft.Dropdown(label="Ano", options=anos_opcoes, value=str(ano_atual), width=120)

    tabela_mensal = ft.Column(spacing=2)
    total_mensal_text = ft.Text("", size=18, weight="bold", color=COR_VERDE_ESCURO)
    dados_pdf_mensal = {"linhas": [], "titulo": "", "subtitulo": "", "rodape": []}

    def gerar_relatorio_mensal(e):
        ano = int(ano_mensal_dd.value)
        mes = int(mes_dd.value)
        rows = buscar_mes(ano, mes)

        dias = {}
        for data_iso, turno, total in rows:
            dias.setdefault(data_iso, {chave: 0 for chave in TURNOS})
            dias[data_iso][turno] = total

        tabela_mensal.controls.clear()
        tabela_mensal.controls.append(
            ft.Row(
                [
                    ft.Text("Data", width=90, weight="bold"),
                    ft.Text("Almoço", width=65, weight="bold"),
                    ft.Text("Jantar", width=65, weight="bold"),
                    ft.Text("Marmita\nAlmoço", width=75, weight="bold"),
                    ft.Text("Marmita\nJanta", width=75, weight="bold"),
                    ft.Text("Total Refeições", width=110, weight="bold"),
                    ft.Text("Lanche", width=65, weight="bold"),
                ]
            )
        )

        linhas_pdf = []
        total_mes_refeicoes = 0
        total_mes_lanches = 0
        for data_iso in sorted(dias.keys()):
            almoco_v = dias[data_iso]["almoco"]
            jantar_v = dias[data_iso]["jantar"]
            marmita_almoco_v = dias[data_iso]["marmita_almoco"]
            marmita_jantar_v = dias[data_iso]["marmita_jantar"]
            lanche_v = dias[data_iso]["lanche"]
            total_refeicoes_dia = almoco_v + jantar_v + marmita_almoco_v + marmita_jantar_v
            total_mes_refeicoes += total_refeicoes_dia
            total_mes_lanches += lanche_v
            tabela_mensal.controls.append(
                ft.Row(
                    [
                        ft.Text(data_iso_para_br(data_iso), width=90),
                        ft.Text(str(almoco_v), width=65),
                        ft.Text(str(jantar_v), width=65),
                        ft.Text(str(marmita_almoco_v), width=75),
                        ft.Text(str(marmita_jantar_v), width=75),
                        ft.Text(str(total_refeicoes_dia), width=110),
                        ft.Text(str(lanche_v), width=65),
                    ]
                )
            )
            linhas_pdf.append([
                data_iso_para_br(data_iso), str(almoco_v), str(jantar_v),
                str(marmita_almoco_v), str(marmita_jantar_v),
                str(total_refeicoes_dia), str(lanche_v),
            ])

        if not dias:
            tabela_mensal.controls.append(ft.Text("Nenhum registro neste mês."))

        total_mensal_text.value = (
            f"Total de refeições do mês (Almoço + Jantar + Marmitas): {total_mes_refeicoes}\n"
            f"Total de lanches do mês: {total_mes_lanches}"
        )

        dados_pdf_mensal["linhas"] = linhas_pdf
        dados_pdf_mensal["titulo"] = f"Relatório Mensal — {MESES_PT[mes - 1]}/{ano}"
        dados_pdf_mensal["subtitulo"] = "Detalhamento diário de refeições, marmitas e lanches"
        dados_pdf_mensal["rodape"] = [
            f"Total de refeições do mês (Almoço + Jantar + Marmitas): {total_mes_refeicoes}",
            f"Total de lanches do mês: {total_mes_lanches}",
        ]
        page.update()

    def imprimir_relatorio_mensal(e):
        if not dados_pdf_mensal["linhas"]:
            gerar_relatorio_mensal(e)
        if not dados_pdf_mensal["linhas"]:
            return
        pdf_bytes = gerar_pdf_relatorio(
            titulo=dados_pdf_mensal["titulo"],
            subtitulo=dados_pdf_mensal["subtitulo"],
            cabecalhos=["Data", "Almoço", "Jantar", "Marmita\nAlmoço", "Marmita\nJanta", "Total Refeições", "Lanche"],
            linhas=dados_pdf_mensal["linhas"],
            rodape_linhas=dados_pdf_mensal["rodape"],
        )
        abrir_pdf_no_navegador(page, pdf_bytes)

    tab_mensal = ft.Column(
        [
            ft.Text("Relatório Mensal", size=24, weight="bold", color=COR_VERDE_ESCURO),
            ft.Row([
                mes_dd, ano_mensal_dd,
                ft.ElevatedButton(
                    "Gerar Relatório", on_click=gerar_relatorio_mensal,
                    style=ft.ButtonStyle(bgcolor=COR_VERDE_ARCOM, color=COR_BRANCO, shape=ft.RoundedRectangleBorder(radius=RAIO_PADRAO)),
                ),
                ft.ElevatedButton(
                    "Imprimir", on_click=imprimir_relatorio_mensal,
                    style=ft.ButtonStyle(bgcolor=COR_VERDE_ESCURO, color=COR_BRANCO, shape=ft.RoundedRectangleBorder(radius=RAIO_PADRAO)),
                ),
            ]),
            ft.Divider(),
            tabela_mensal,
            total_mensal_text,
        ],
        spacing=12,
        scroll=ft.ScrollMode.AUTO,
    )

    # ---------------- ABA 3: RELATÓRIO ANUAL ----------------

    ano_anual_dd = ft.Dropdown(label="Ano", options=anos_opcoes, value=str(ano_atual), width=120)
    tabela_anual = ft.Column(spacing=2)
    total_anual_text = ft.Text("", size=18, weight="bold", color=COR_VERDE_ESCURO)
    dados_pdf_anual = {"linhas": [], "titulo": "", "subtitulo": "", "rodape": []}

    def gerar_relatorio_anual(e):
        ano = int(ano_anual_dd.value)
        rows = buscar_ano(ano)  # [(mes_str, total_refeicoes, total_lanches), ...]
        somas = {mes_str: (ref, lan) for mes_str, ref, lan in rows}

        tabela_anual.controls.clear()
        tabela_anual.controls.append(
            ft.Row(
                [
                    ft.Text("Mês", width=150, weight="bold"),
                    ft.Text("Total de Refeições", width=150, weight="bold"),
                    ft.Text("Total de Lanches", width=150, weight="bold"),
                ]
            )
        )

        linhas_pdf = []
        total_ano_refeicoes = 0
        total_ano_lanches = 0
        for i in range(1, 13):
            chave = f"{i:02d}"
            ref_v, lan_v = somas.get(chave, (0, 0))
            ref_v = ref_v or 0
            lan_v = lan_v or 0
            total_ano_refeicoes += ref_v
            total_ano_lanches += lan_v
            tabela_anual.controls.append(
                ft.Row(
                    [
                        ft.Text(MESES_PT[i - 1], width=150),
                        ft.Text(str(ref_v), width=150),
                        ft.Text(str(lan_v), width=150),
                    ]
                )
            )
            linhas_pdf.append([MESES_PT[i - 1], str(ref_v), str(lan_v)])

        total_anual_text.value = (
            f"Total de refeições do ano: {total_ano_refeicoes}\n"
            f"Total de lanches do ano: {total_ano_lanches}"
        )

        dados_pdf_anual["linhas"] = linhas_pdf
        dados_pdf_anual["titulo"] = f"Relatório Anual — {ano}"
        dados_pdf_anual["subtitulo"] = "Totais mensais de refeições e lanches"
        dados_pdf_anual["rodape"] = [
            f"Total de refeições do ano: {total_ano_refeicoes}",
            f"Total de lanches do ano: {total_ano_lanches}",
        ]
        page.update()

    def imprimir_relatorio_anual(e):
        if not dados_pdf_anual["linhas"]:
            gerar_relatorio_anual(e)
        if not dados_pdf_anual["linhas"]:
            return
        pdf_bytes = gerar_pdf_relatorio(
            titulo=dados_pdf_anual["titulo"],
            subtitulo=dados_pdf_anual["subtitulo"],
            cabecalhos=["Mês", "Total de Refeições", "Total de Lanches"],
            linhas=dados_pdf_anual["linhas"],
            rodape_linhas=dados_pdf_anual["rodape"],
        )
        abrir_pdf_no_navegador(page, pdf_bytes)

    tab_anual = ft.Column(
        [
            ft.Text("Relatório Anual", size=24, weight="bold", color=COR_VERDE_ESCURO),
            ft.Row([
                ano_anual_dd,
                ft.ElevatedButton(
                    "Gerar Relatório", on_click=gerar_relatorio_anual,
                    style=ft.ButtonStyle(bgcolor=COR_VERDE_ARCOM, color=COR_BRANCO, shape=ft.RoundedRectangleBorder(radius=RAIO_PADRAO)),
                ),
                ft.ElevatedButton(
                    "Imprimir", on_click=imprimir_relatorio_anual,
                    style=ft.ButtonStyle(bgcolor=COR_VERDE_ESCURO, color=COR_BRANCO, shape=ft.RoundedRectangleBorder(radius=RAIO_PADRAO)),
                ),
            ]),
            ft.Divider(),
            tabela_anual,
            total_anual_text,
        ],
        spacing=12,
        scroll=ft.ScrollMode.AUTO,
    )

    # ---------------- MONTAGEM DA NAVEGAÇÃO (sem Tabs, evita bug de altura no mobile) ----------------

    atualizar_historico()

    tab_mensal.visible = False
    tab_anual.visible = False

    def estilo_botao(ativo):
        return ft.ButtonStyle(
            bgcolor=COR_VERDE_ARCOM if ativo else COR_BRANCO,
            color=COR_BRANCO if ativo else COR_VERDE_ESCURO,
            shape=ft.RoundedRectangleBorder(radius=RAIO_PADRAO),
            side=ft.BorderSide(1, COR_BORDA_CARD) if not ativo else None,
        )

    def mostrar_aba(indice):
        tab_registro.visible = indice == 0
        tab_mensal.visible = indice == 1
        tab_anual.visible = indice == 2
        btn_registro.style = estilo_botao(indice == 0)
        btn_mensal.style = estilo_botao(indice == 1)
        btn_anual.style = estilo_botao(indice == 2)
        page.update()

    btn_registro = ft.ElevatedButton(
        "Registro Diário",
        on_click=lambda e: mostrar_aba(0),
        style=estilo_botao(True),
    )
    btn_mensal = ft.ElevatedButton(
        "Relatório Mensal",
        on_click=lambda e: mostrar_aba(1),
        style=estilo_botao(False),
    )
    btn_anual = ft.ElevatedButton(
        "Relatório Anual",
        on_click=lambda e: mostrar_aba(2),
        style=estilo_botao(False),
    )

    page.add(
        ft.Container(
            content=ft.Row(
                [
                    ft.Image(src=LOGO_ARCOM_URL, width=120, fit=ft.ImageFit.CONTAIN),
                    ft.Container(width=16),
                    ft.Text(
                        "Controle de Refeições",
                        size=18,
                        weight="bold",
                        color=COR_VERDE_ESCURO,
                    ),
                ],
                alignment=ft.MainAxisAlignment.START,
            ),
            bgcolor=COR_BRANCO,
            border=ft.border.only(bottom=ft.BorderSide(1, COR_BORDA_CARD)),
            padding=16,
        ),
        ft.Container(height=10),
        ft.Row(
            [btn_registro, btn_mensal, btn_anual],
            wrap=True,
        ),
        ft.Divider(),
        tab_registro,
        tab_mensal,
        tab_anual,
        ft.Divider(),
        ft.Container(
            content=ft.Text(
                "Desenvolvido por G.SANGUINETE",
                size=12,
                color=COR_CINZA_TEXTO,
                italic=True,
            ),
            alignment=ft.Alignment.CENTER,
            padding=10,
        ),
    )



def main(page: ft.Page):
    page.title = "Controle de Refeições — ARCOM"
    page.scroll = ft.ScrollMode.AUTO
    page.bgcolor = COR_FUNDO_PAGINA
    page.theme = ft.Theme(
        color_scheme=ft.ColorScheme(
            primary=COR_VERDE_ARCOM,
            error=COR_DANGER,
        ),
    )
    criar_tabela()

    SENHA_APP = os.environ.get("APP_PASSWORD", "1234")

    senha_field = ft.TextField(
        label="Senha de acesso",
        password=True,
        can_reveal_password=True,
        width=280,
        border_radius=RAIO_PADRAO,
    )
    erro_login = ft.Text("", color=COR_DANGER)

    def entrar(e):
        if senha_field.value == SENHA_APP:
            page.controls.clear()
            construir_interface(page)
            page.update()
        else:
            erro_login.value = "Senha incorreta. Tente novamente."
            page.update()

    senha_field.on_submit = entrar

    page.add(
        ft.Column(
            [
                ft.Container(height=60),
                ft.Image(src=LOGO_ARCOM_URL, width=220, fit=ft.ImageFit.CONTAIN),
                ft.Container(height=20),
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(
                                "Controle de Refeições",
                                size=24,
                                weight="bold",
                                color=COR_VERDE_ESCURO,
                            ),
                            ft.Text(
                                "Digite a senha para acessar",
                                size=14,
                                color=COR_CINZA_TEXTO,
                            ),
                            senha_field,
                            ft.ElevatedButton(
                                "Entrar",
                                on_click=entrar,
                                style=ft.ButtonStyle(
                                    bgcolor=COR_VERDE_ARCOM,
                                    color=COR_BRANCO,
                                    shape=ft.RoundedRectangleBorder(radius=RAIO_PADRAO),
                                ),
                            ),
                            erro_login,
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=14,
                    ),
                    bgcolor=COR_BRANCO,
                    border=ft.border.all(1, COR_BORDA_CARD),
                    border_radius=12,
                    padding=30,
                    width=340,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
        )
    )



ft.run(main, view=ft.AppView.WEB_BROWSER, host="0.0.0.0", port=PORT)
