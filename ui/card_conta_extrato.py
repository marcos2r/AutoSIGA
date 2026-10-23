"""
Card de uma conta de extrato no lote: escolha guiada das contas do SIGA e selo de estado.

O card mostra listas fechadas com as contas do catálogo (código · finalidade), já
preenchidas pela sugestão. O usuário reconhece e confirma em vez de digitar; "Editar"
libera a digitação, que continua validada. A regra de negócio (sugestão, validação e
estado) fica em controllers/; aqui só se desenha o resultado.
"""

from tkinter import messagebox

import customtkinter as ctk

from controllers.catalogo_contas import (
    GRUPO_APLICACAO,
    GRUPO_CORRENTE,
    Catalogo,
    ContaSiga,
    mesma_localidade,
    separar_localidade,
)
from controllers.estado_card import CONFIRMADO, EDITADO, SUGERIDO, avaliar_card, codigo_do_combo
from controllers.sugestao_contas import sugerir
from ui import tema


class CardContaExtrato(ctk.CTkFrame):
    """Mapeamento de um extrato para a localidade, a C. Corrente e a C. Aplicação do SIGA."""

    def __init__(self, parent, dados_extrato, config_manager, on_change_callback, catalogo=None, on_remover=None):
        super().__init__(parent, fg_color=tema.BRANCO, border_width=1, border_color=tema.CINZA_BORDA, corner_radius=6)
        self.dados_extrato = dados_extrato
        self.config_manager = config_manager
        self.on_change_callback = on_change_callback
        self.on_remover = on_remover

        self.conta_id = dados_extrato.get("conta_id", "")
        self.produto = dados_extrato.get("produto")
        self.tipo_extrato = dados_extrato.get("tipo_extrato")
        self.is_aplicacao = (self.tipo_extrato == "APLICACAO")

        self.catalogo = catalogo or Catalogo()
        self.sugestao = None  # Sugestao | None
        self.confirmado = False
        self.origem_sugestao = False
        self.modo_edicao = False
        self.estado = None
        self._ultimo = ("", "", "")

        self.inicializando = True
        self.construir_widgets()
        self.carregar_mapeamento()
        self.inicializando = False

    # ------------------------------------------------------------------ widgets
    def construir_widgets(self):
        fonte = (tema.FONTE, 11)
        tipo_desc = f"Aplicação: {self.produto}" if self.is_aplicacao else "Conta Corrente"
        self.lbl_titulo = ctk.CTkLabel(self, text=f"Conta Bancária: {self.conta_id} ({tipo_desc})",
                                       font=(tema.FONTE, 12, "bold"), text_color=tema.AZUL_TITULO)
        self.lbl_titulo.grid(row=0, column=0, columnspan=4, padx=10, pady=(6, 2), sticky="w")

        frame_topo = ctk.CTkFrame(self, fg_color="transparent")
        frame_topo.grid(row=0, column=4, padx=10, pady=(6, 2), sticky="e")
        self.lbl_selo = ctk.CTkLabel(frame_topo, text="", font=(tema.FONTE, 11, "bold"), corner_radius=10, height=24)
        self.lbl_selo.pack(side="left")
        # Tira só este extrato do lote (o mapeamento salvo continua): útil para conta que não existe no SIGA
        self.btn_remover = ctk.CTkButton(frame_topo, text="✕ Tirar do lote", width=100, height=24,
                                         font=(tema.FONTE, 11), fg_color=tema.BRANCO, hover_color=tema.VERMELHO_FUNDO,
                                         text_color=tema.VERMELHO_TEXTO, border_width=1, border_color=tema.CINZA_BORDA,
                                         command=lambda: self.on_remover(self) if self.on_remover else None)
        self.btn_remover.pack(side="left", padx=(8, 0))

        ctk.CTkLabel(self, text="Localidade:", font=fonte).grid(row=1, column=0, padx=(10, 4), pady=2, sticky="e")
        self.combo_local = ctk.CTkComboBox(self, values=[], width=300, height=28, font=fonte,
                                           command=lambda v: self._ao_mudar_localidade())
        self.combo_local.grid(row=1, column=1, columnspan=3, padx=2, pady=2, sticky="w")

        ctk.CTkLabel(self, text="C. Corrente:", font=fonte).grid(row=2, column=0, padx=(10, 4), pady=2, sticky="e")
        self.combo_cc = ctk.CTkComboBox(self, values=[], width=210, height=28, font=fonte,
                                        command=lambda v: self._ao_mudar_conta())
        self.combo_cc.grid(row=2, column=1, padx=2, pady=2, sticky="w")

        ctk.CTkLabel(self, text="C. Aplicação:", font=fonte).grid(row=2, column=2, padx=(10, 4), pady=2, sticky="e")
        self.combo_ca = ctk.CTkComboBox(self, values=[], width=210, height=28, font=fonte,
                                        command=lambda v: self._ao_mudar_conta())
        self.combo_ca.grid(row=2, column=3, padx=2, pady=2, sticky="w")

        # Em modo Editar, o texto digitado é avaliado ao sair do campo ou ao teclar Enter
        for combo, acao in ((self.combo_local, self._ao_mudar_localidade), (self.combo_cc, self._ao_mudar_conta),
                            (self.combo_ca, self._ao_mudar_conta)):
            combo.bind("<FocusOut>", lambda e, a=acao: a() if self.modo_edicao else None)
            combo.bind("<Return>", lambda e, a=acao: a() if self.modo_edicao else None)

        self.lbl_msg = ctk.CTkLabel(self, text="", font=fonte, text_color=tema.CINZA_TEXTO,
                                    wraplength=430, justify="left", anchor="w")
        self.lbl_msg.grid(row=3, column=0, columnspan=4, padx=10, pady=(2, 6), sticky="w")

        frame_botoes = ctk.CTkFrame(self, fg_color="transparent")
        frame_botoes.grid(row=2, column=4, rowspan=2, padx=10, pady=(2, 6), sticky="se")
        secundario = dict(height=28, font=(tema.FONTE, 11), fg_color=tema.BRANCO, hover_color=tema.CINZA_HOVER,
                          text_color=tema.AZUL_NAVBAR, border_width=1, border_color=tema.CINZA_BORDA)
        self.btn_limpar = ctk.CTkButton(frame_botoes, text="Limpar", width=60, command=self.limpar_mapeamento,
                                        **secundario)
        self.btn_limpar.pack(side="left", padx=2)
        self.btn_editar = ctk.CTkButton(frame_botoes, text="Editar", width=60, command=self.alternar_edicao,
                                        **secundario)
        self.btn_editar.pack(side="left", padx=2)
        self.btn_confirmar = ctk.CTkButton(frame_botoes, text="Confirmar", width=84, height=28,
                                           font=(tema.FONTE, 11, "bold"), fg_color=tema.AZUL_NAVBAR,
                                           hover_color=tema.AZUL_NAVBAR_HOVER, text_color=tema.BRANCO,
                                           text_color_disabled=tema.CINZA_TEXTO, command=self.confirmar)
        self.btn_confirmar.pack(side="left", padx=2)

        if self.is_aplicacao:
            self.combo_cc.set("N/A")
            self.combo_cc.configure(state="disabled")
        self.grid_columnconfigure(4, weight=1)

    # ------------------------------------------------------------------ dados
    def _set(self, combo, valor):
        if combo is self.combo_cc and self.is_aplicacao:
            return  # extrato de aplicação não usa C. Corrente: o campo fica "N/A"
        combo.set(valor or "")

    def _valores(self):
        return (self._localidade_atual(), self._codigo(self.combo_cc), self._codigo(self.combo_ca))

    def _rotulo(self, codigo, grupo):
        """Valor do combo para um código: "10130 · CAPTAÇÃO" se o catálogo conhece a conta."""
        if not codigo:
            return ""
        conta = next((c for c in self.catalogo.contas_de(grupo) if c.codigo == codigo), None)
        return conta.rotulo_curto if conta else codigo

    def _localidade_atual(self):
        return " ".join(self.combo_local.get().upper().split())

    def _opcoes(self, grupo, sugeridas: list[ContaSiga]):
        """Opções do combo: as sugeridas pela CC primeiro, depois as demais da localidade."""
        local = self._localidade_atual()
        da_localidade = self.catalogo.contas_de(grupo, local or None)
        ordem = [c for c in sugeridas if not local or mesma_localidade(c.localidade, local)]
        ordem += [c for c in da_localidade if c not in ordem]
        return [c.rotulo_curto for c in ordem]

    def _atualizar_listas(self):
        """Recarrega as opções dos combos conforme o catálogo, a sugestão e a localidade."""
        s = self.sugestao
        locais = self.catalogo.localidades()
        tipo_geral, nome_geral = self.config_manager.get_geral()
        geral = f"{tipo_geral} - {nome_geral}".upper() if nome_geral else ""
        for loc in [s.localidade if s else "", *self.config_manager.localidades_mapeadas(), geral,
                    self._localidade_atual()]:
            if loc and not any(mesma_localidade(loc, l) for l in locais):
                locais.append(loc)
        self.combo_local.configure(values=locais)
        self.combo_cc.configure(values=[] if self.is_aplicacao else self._opcoes(GRUPO_CORRENTE, s.corrente.opcoes if s else []))
        self.combo_ca.configure(values=self._opcoes(GRUPO_APLICACAO, s.aplicacao.opcoes if s else []))

    def carregar_mapeamento(self):
        """Preenche o card com o mapeamento confirmado ou, na falta dele, com a sugestão do catálogo."""
        tipo_adm, nome_adm = self.config_manager.get_geral()
        novo_tipo, novo_nome, dados = self.config_manager.get_mapeamento_conta(
            self.conta_id, tipo_adm, nome_adm, produto=self.produto)

        self.sugestao = sugerir(self.catalogo, self.conta_id, self.is_aplicacao, self.produto or "",
                                self.config_manager.localidade_preferida(self.conta_id))
        self.confirmado = "conta_id" in dados  # o fallback do ConfigManager não traz conta_id
        self.origem_sugestao = False

        if self.confirmado:
            self._set(self.combo_local, f"{novo_tipo} - {novo_nome}".upper())
            corrente, aplicacao = dados.get("corrente", ""), dados.get("aplicacao", "")
        else:
            s = self.sugestao
            self.origem_sugestao = True
            # Sem catálogo, parte da última localidade usada, como antes da descoberta
            local_padrao = f"{tipo_adm} - {nome_adm}".upper() if self.catalogo.vazio and nome_adm else ""
            self._set(self.combo_local, s.localidade or local_padrao)
            corrente = s.corrente.escolhida.codigo if s.corrente.escolhida else ""
            aplicacao = s.aplicacao.escolhida.codigo if s.aplicacao.escolhida else ""

        self._atualizar_listas()
        self._set(self.combo_cc, "" if self.is_aplicacao else self._rotulo(corrente, GRUPO_CORRENTE))
        self._set(self.combo_ca, self._rotulo(aplicacao, GRUPO_APLICACAO))
        # Sem catálogo não há lista para escolher: os campos começam digitáveis
        self._aplicar_modo(edicao=self.catalogo.vazio)
        self._ultimo = self._valores()
        self.atualizar_status_visual()

    def aplicar_catalogo(self, catalogo):
        """Recebe um catálogo novo (após Buscar no SIGA) e refaz a sugestão se não estiver confirmado."""
        self.catalogo = catalogo or Catalogo()
        if self.confirmado:
            self._atualizar_listas()
            self._set(self.combo_cc, "" if self.is_aplicacao else self._rotulo(self._codigo(self.combo_cc), GRUPO_CORRENTE))
            self._set(self.combo_ca, self._rotulo(self._codigo(self.combo_ca), GRUPO_APLICACAO))
            self._aplicar_modo(edicao=self.catalogo.vazio)
            self.atualizar_status_visual()
        else:
            self.inicializando = True
            self.carregar_mapeamento()
            self.inicializando = False

    @staticmethod
    def _codigo(combo):
        return codigo_do_combo(combo.get())

    # ------------------------------------------------------------------ estado
    def _avaliar(self):
        s = self.sugestao
        # Há o que escolher se a sugestão empatou ou se a localidade definida tem contas nas listas
        sugeriu_opcoes = bool(s and self.origem_sugestao and (s.aplicacao.opcoes or s.corrente.opcoes))
        listas_cheias = bool(self.combo_ca.cget("values")) and (self.is_aplicacao or bool(self.combo_cc.cget("values")))
        tem_opcoes = sugeriu_opcoes or (bool(self._localidade_atual()) and listas_cheias)
        return avaliar_card(
            self.catalogo, self.is_aplicacao, self._localidade_atual(),
            "" if self.is_aplicacao else self._codigo(self.combo_cc), self._codigo(self.combo_ca),
            self.confirmado, self.origem_sugestao, tem_opcoes, s.motivo if s and self.origem_sugestao else "")

    def atualizar_status_visual(self):
        """Redesenha o selo, a mensagem, a borda e o botão Confirmar conforme o estado."""
        self.estado = self._avaliar()
        fundo, texto = tema.SELO[self.estado.chave]
        self.lbl_selo.configure(text=f"  {self.estado.texto}  ", fg_color=fundo, text_color=texto)
        self.lbl_msg.configure(text=self.estado.mensagem)
        self.configure(border_color=texto if self.estado.chave != CONFIRMADO else tema.CINZA_BORDA)
        pode_confirmar = self.estado.chave in (SUGERIDO, EDITADO)
        self.btn_confirmar.configure(state="normal" if pode_confirmar else "disabled",
                                     fg_color=tema.AZUL_NAVBAR if pode_confirmar else tema.CINZA_BORDA)
        # Sem catálogo não há listas: os campos já são digitáveis e "Editar" não faz sentido
        if self.catalogo.vazio:
            self.btn_editar.pack_forget()
        else:
            self.btn_editar.configure(text="Listas" if self.modo_edicao else "Editar")
            self.btn_editar.pack(side="left", padx=2, before=self.btn_confirmar)

    def _aplicar_modo(self, edicao):
        self.modo_edicao = edicao
        estado = "normal" if edicao else "readonly"
        self.combo_local.configure(state=estado)
        if not self.is_aplicacao:
            self.combo_cc.configure(state=estado)
        self.combo_ca.configure(state=estado)

    def alternar_edicao(self):
        """Editar libera a digitação; "Listas" volta para as opções fechadas do catálogo."""
        self._aplicar_modo(not self.modo_edicao)
        self.atualizar_status_visual()

    def _marcar_alterado(self):
        # Sair do campo sem mudar nada não desfaz a confirmação
        if self.inicializando or self._valores() == self._ultimo:
            return
        self._ultimo = self._valores()
        self.confirmado = False
        self.origem_sugestao = False
        self.atualizar_status_visual()
        if self.on_change_callback:
            self.on_change_callback()

    def _ao_mudar_localidade(self):
        local = self._localidade_atual()
        self._set(self.combo_local, local)
        self._atualizar_listas()
        # Conta de outra localidade não serve mais: limpa para o usuário escolher de novo
        for combo, grupo in ((self.combo_cc, GRUPO_CORRENTE), (self.combo_ca, GRUPO_APLICACAO)):
            if self.is_aplicacao and grupo == GRUPO_CORRENTE:
                continue
            codigo = self._codigo(combo)
            mesmas = [c for c in self.catalogo.contas if c.ativa and c.codigo == codigo]
            if mesmas and not any(mesma_localidade(c.localidade, local) for c in mesmas):
                self._set(combo, "")
        self._marcar_alterado()

    def _ao_mudar_conta(self):
        for combo, grupo in ((self.combo_cc, GRUPO_CORRENTE), (self.combo_ca, GRUPO_APLICACAO)):
            if not (self.is_aplicacao and grupo == GRUPO_CORRENTE):
                self._set(combo, self._rotulo(self._codigo(combo), grupo))
        self._marcar_alterado()

    # ------------------------------------------------------------------ ações
    def confirmar(self):
        """Salva o mapeamento mostrado; só é possível com os campos válidos."""
        if self._avaliar().chave not in (SUGERIDO, EDITADO, CONFIRMADO):
            return
        tipo_adm, nome_adm = separar_localidade(self._localidade_atual())
        corrente = "" if self.is_aplicacao else self._codigo(self.combo_cc)
        self.config_manager.salvar_mapeamento_conta(
            self.conta_id, tipo_adm, nome_adm, corrente, self._codigo(self.combo_ca), produto=self.produto)
        self.config_manager.salvar_geral(tipo_adm, nome_adm)
        self.confirmado = True
        self.origem_sugestao = False
        self._ultimo = self._valores()
        self._aplicar_modo(edicao=self.catalogo.vazio)
        self.atualizar_status_visual()
        if self.on_change_callback:
            self.on_change_callback()

    def salvar_e_notificar(self):
        """Regrava o mapeamento confirmado (chamado antes da conciliação e do TXT de ofertas)."""
        if getattr(self, "inicializando", False) or not self.confirmado:
            return
        if self._avaliar().valido:
            self.confirmar()

    def limpar_mapeamento(self):
        tipo_adm, nome_adm = separar_localidade(self._localidade_atual())
        if self.config_manager.limpar_conta(self.conta_id, tipo_adm, nome_adm, produto=self.produto):
            self.inicializando = True
            self.carregar_mapeamento()
            self.inicializando = False
            if self.on_change_callback:
                self.on_change_callback()
            messagebox.showinfo("Limpeza", f"O mapeamento da conta {self.conta_id} foi apagado.")

    def obter_dados_mapeados(self):
        tipo_adm, nome_adm = separar_localidade(self._localidade_atual())
        estado = self._avaliar()
        return {
            "tipo_adm": tipo_adm,
            "nome_adm": nome_adm,
            "corrente": "" if self.is_aplicacao else self._codigo(self.combo_cc),
            "aplicacao": self._codigo(self.combo_ca),
            "valido": estado.valido,
            "estado": estado.chave,
        }
