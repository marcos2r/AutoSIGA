"""
Conciliação bancária no modelo do formulário FOR.TES.02 (IT.TES.06), a partir da prova real.

O formulário parte do saldo do extrato e chega ao saldo contábil (SIGA) somando e
subtraindo o que só aparece de um dos lados. Na prova real isso já existe: as sobras
(lançamentos do SIGA sem par no banco) e as faltas (movimentos do banco sem lançamento).
Aqui só se distribui cada item na linha certa do formulário. Nada é lançado.

Convenções do formulário (as mesmas da IT.TES.06):
- do lado do SIGA (contábil), entrada na conta do banco é DÉBITO e saída é CRÉDITO;
- do lado do extrato, vale a visão do banco: crédito é entrada e débito é saída.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from controllers.classificador_extrato import DEPOSITO, classificar, normalizar
from controllers.prova_real import NAO_CONFERIDO, TOLERANCIA, MovimentoBanco, MovimentoSiga, ResultadoExtrato

# Linhas do FOR.TES.02 (número → rótulo do formulário)
LINHAS = {
    1: "Saldo do extrato bancário",
    2: "Cheques contabilizados e não compensados",
    3: "Depósitos contabilizados que não constam no extrato",
    4: "Depósitos que constam do extrato não contabilizados",
    5: "Débitos no extrato não contabilizados",
    6: "Débitos contabilizados que não constam do extrato",
    7: "Créditos contabilizados que não constam do extrato",
    8: "Créditos no extrato não contabilizados",
    9: "Saldo conta corrente (SIGA)",
    10: "Diferença sem explicação (zero = conciliado)",
}


@dataclass(frozen=True)
class Item:
    """Um movimento sem par, com o efeito que tem do saldo do extrato até o saldo do SIGA."""

    data: str
    descricao: str
    valor: float   # valor com sinal, como na origem (saída negativa)
    efeito: float  # quanto soma ao saldo do extrato para chegar ao do SIGA


@dataclass
class Conciliacao:
    """O formulário de uma conta, pronto para o Excel."""

    localidade: str
    conta_siga: str
    conta_banco: str
    periodo: str
    saldo_extrato: float
    saldo_siga: float
    itens: dict[int, list[Item]] = field(default_factory=lambda: {n: [] for n in range(2, 9)})

    @property
    def sem_explicacao(self) -> float:
        """Linha 10: o que os itens não explicam (saldo inicial diferente, item fora do período)."""
        explicado = sum(i.efeito for lista in self.itens.values() for i in lista)
        resto = round(self.saldo_siga - self.saldo_extrato - explicado, 2)
        return resto if abs(resto) > TOLERANCIA else 0.0

    @property
    def conciliado(self) -> bool:
        return self.sem_explicacao == 0.0


def linha_da_sobra(s: MovimentoSiga) -> int:
    """Lançamento do SIGA sem par no banco: cheque (2), depósito (3), outra entrada (6) ou saída (7)."""
    historico = normalizar(s.historico)
    if s.valor < 0:
        return 2 if "CHEQUE" in historico or historico.startswith("CH ") else 7
    return 3 if "DEP" in historico else 6


def linha_da_falta(f: MovimentoBanco) -> int:
    """Movimento do banco sem lançamento: depósito (4), outra entrada (8) ou saída (5)."""
    if f.valor < 0:
        return 5
    return 4 if classificar({"descricao": f.descricao, "valor": f.valor}).categoria == DEPOSITO else 8


def montar(r: ResultadoExtrato) -> Conciliacao | None:
    """Monta o FOR.TES.02 de um extrato; None quando a prova real não conferiu os saldos."""
    if r.saldo.status == NAO_CONFERIDO or r.saldo.saldo_banco is None or r.saldo.saldo_siga is None:
        return None
    c = Conciliacao(r.localidade, r.conta_siga, r.conta_id, r.periodo, r.saldo.saldo_banco, r.saldo.saldo_siga)
    for s in r.sobras or []:
        c.itens[linha_da_sobra(s)].append(Item(s.data, s.historico, s.valor, s.valor))
    for f in r.faltas or []:
        c.itens[linha_da_falta(f)].append(Item(f.data, f.descricao, f.valor, -f.valor))
    return c


def escrever_aba(wb, conciliacoes: list[Conciliacao], cor_header, fonte_header, fonte_normal):
    """Aba "Conciliação FOR.TES.02": um bloco por conta, com as 10 linhas do formulário."""
    from openpyxl.styles import Font

    ws = wb.create_sheet(title="Conciliação FOR.TES.02")
    moeda = 'R$ #,##0.00'
    linha = 1
    for c in conciliacoes:
        titulo = f"{c.localidade} · Conta SIGA {c.conta_siga} · Banco {c.conta_banco} · {c.periodo}"
        for col, texto in enumerate([titulo, "Data", "Descrição", "Valor", "Efeito"], start=1):
            cell = ws.cell(row=linha, column=col, value=texto)
            cell.fill, cell.font = cor_header, fonte_header
        linha += 1
        for numero, rotulo in LINHAS.items():
            if numero == 1:
                total = c.saldo_extrato
            elif numero == 9:
                total = c.saldo_siga
            elif numero == 10:
                total = c.sem_explicacao
            else:
                total = sum(i.efeito for i in c.itens[numero])
            ws.cell(row=linha, column=1, value=f"{numero} - {rotulo}").font = Font(bold=True)
            cell = ws.cell(row=linha, column=5, value=total)
            cell.number_format, cell.font = moeda, Font(bold=True)
            linha += 1
            for item in c.itens.get(numero, []):
                for col, valor in enumerate([None, item.data, item.descricao, item.valor, item.efeito], start=1):
                    ws.cell(row=linha, column=col, value=valor).font = fonte_normal
                ws.cell(row=linha, column=4).number_format = moeda
                ws.cell(row=linha, column=5).number_format = moeda
                linha += 1
        situacao = "Conciliado" if c.conciliado else "NÃO conciliado: confira o saldo inicial e itens fora do período"
        ws.cell(row=linha, column=1, value=situacao).font = Font(bold=True)
        linha += 2
    return ws
