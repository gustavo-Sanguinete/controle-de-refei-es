import flet as ft
import sqlite3
import os
from datetime import datetime
import calendar

# Em produção (Railway/Render/etc.) essas variáveis vêm do ambiente.
# Localmente, os valores padrão abaixo são usados.
DB_PATH = os.environ.get("DB_PATH", "refeicoes.db")
PORT = int(os.environ.get("PORT", 8550))

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
            ft.Text("Registro Diário", size=24, weight="bold"),
            ft.Row([turno_dd, data_field]),
            inicial,
            reposicoes,
            pratos_unidade,
            unidades_extra,
            sobras_pratos,
            quantidade_simples,
            ft.Row(
                [
                    ft.ElevatedButton("Calcular e Salvar", on_click=calcular_e_salvar),
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
    total_mensal_text = ft.Text("", size=18, weight="bold", color="blue")

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

        if not dias:
            tabela_mensal.controls.append(ft.Text("Nenhum registro neste mês."))

        total_mensal_text.value = (
            f"Total de refeições do mês (Almoço + Jantar + Marmitas): {total_mes_refeicoes}\n"
            f"Total de lanches do mês: {total_mes_lanches}"
        )
        page.update()

    tab_mensal = ft.Column(
        [
            ft.Text("Relatório Mensal", size=24, weight="bold"),
            ft.Row([mes_dd, ano_mensal_dd, ft.ElevatedButton("Gerar Relatório", on_click=gerar_relatorio_mensal)]),
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
    total_anual_text = ft.Text("", size=18, weight="bold", color="blue")

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

        total_anual_text.value = (
            f"Total de refeições do ano: {total_ano_refeicoes}\n"
            f"Total de lanches do ano: {total_ano_lanches}"
        )
        page.update()

    tab_anual = ft.Column(
        [
            ft.Text("Relatório Anual", size=24, weight="bold"),
            ft.Row([ano_anual_dd, ft.ElevatedButton("Gerar Relatório", on_click=gerar_relatorio_anual)]),
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

    def mostrar_aba(indice):
        tab_registro.visible = indice == 0
        tab_mensal.visible = indice == 1
        tab_anual.visible = indice == 2
        btn_registro.style = ft.ButtonStyle(bgcolor="blue" if indice == 0 else None)
        btn_mensal.style = ft.ButtonStyle(bgcolor="blue" if indice == 1 else None)
        btn_anual.style = ft.ButtonStyle(bgcolor="blue" if indice == 2 else None)
        page.update()

    btn_registro = ft.ElevatedButton(
        "Registro Diário",
        on_click=lambda e: mostrar_aba(0),
        style=ft.ButtonStyle(bgcolor="blue"),
    )
    btn_mensal = ft.ElevatedButton(
        "Relatório Mensal",
        on_click=lambda e: mostrar_aba(1),
    )
    btn_anual = ft.ElevatedButton(
        "Relatório Anual",
        on_click=lambda e: mostrar_aba(2),
    )

    page.add(
        ft.Row(
            [btn_registro, btn_mensal, btn_anual],
            wrap=True,
        ),
        ft.Divider(),
        tab_registro,
        tab_mensal,
        tab_anual,
    )


def main(page: ft.Page):
    page.title = "Controle de Refeições"
    page.scroll = ft.ScrollMode.AUTO
    criar_tabela()

    SENHA_APP = os.environ.get("APP_PASSWORD", "1234")

    senha_field = ft.TextField(
        label="Senha de acesso",
        password=True,
        can_reveal_password=True,
        width=280,
    )
    erro_login = ft.Text("", color="red")

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
                ft.Container(height=100),
                ft.Text("Controle de Refeições", size=28, weight="bold"),
                ft.Text("Digite a senha para acessar", size=14),
                senha_field,
                ft.ElevatedButton("Entrar", on_click=entrar),
                erro_login,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
        )
    )



ft.run(main, view=ft.AppView.WEB_BROWSER, host="0.0.0.0", port=PORT)
