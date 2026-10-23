# Plano: descoberta automática das contas do SIGA

Status: **implementado na v1.8.0** (fases 1 a 4). Decisões: busca pelo botão "Buscar no SIGA" (não abre o Edge sem pedir), validade do catálogo de 30 dias, sem `hypothesis` (os casos de formatação viraram testes parametrizados). Falta o roteiro manual no SIGA real, inclusive com um usuário sem acesso à Contabilidade. Levantamento das telas em `docs/regras/siga.md` (seções CTB00301 e "Contas por localidade").

## 1. Problema e objetivo

Ao carregar um extrato, o usuário digita à mão, em cada card, a localidade (tipo + nome), a C. Corrente e a C. Aplicação do SIGA. É comum inverter os campos (corrente no lugar da aplicação), errar a localidade ou digitar um código que não existe. O erro só aparece no meio da automação, ou pior, vira lançamento na conta errada.

**Objetivo:** o próprio AutoSIGA descobre no SIGA quais contas correspondem a cada extrato e preenche o card. O usuário só **confirma**, ou escolhe entre poucas opções válidas quando houver ambiguidade. Digitar código deixa de ser o caminho normal.

**Metas mensuráveis (critérios de sucesso):**
- Lote com contas já conhecidas: zero digitação; o usuário só clica em "Conciliar".
- Conta nova com correspondência única no SIGA: preenchida sozinha, com um clique de confirmação.
- Nenhum código fora do grupo certo é aceito: a corrente precisa ser 101xx e a aplicação 103xx, ambas da localidade escolhida.
- Descoberta completa em até ~20 s via Contabilidade e ~60 s via Tesouraria (3 localidades).

**Fora do escopo:** faturas de energia (já têm fluxo próprio de UC), o TXT de ofertas (usa o código da corrente já mapeado) e a criação de contas no SIGA.

## 2. O que o SIGA oferece (resumo do levantamento)

| Fonte | Quem acessa | O que traz | Custo |
|---|---|---|---|
| **CTB00301 Plano de Contas**, busca `CC:` | Só quem tem o menu Contabilidade | Todas as contas bancárias ativas (101 e 103) **com a localidade dona**, de todas as localidades | 1 navegação, 1 página |
| **TES01701 Caixas e Bancos**, `select#f_conta` | Todo usuário da Tesouraria | Só as contas da localidade ativa; inativas num `optgroup INATIVO` | 1 troca de contexto + 1 navegação por localidade |

Fatos que moldam o desenho:
- O código da Tesouraria (`10130`) = grupo + sufixo do Cód. Reduzido da Contabilidade (`101 30`).
- Os rótulos são texto livre: `AG:0101` / `AG: 0101`, CC com e sem hífen, `CC: CONTA CAPITAL`. **Compare só os dígitos.**
- Uma CC pode ter várias contas 103 (ex.: aplicação **e** poupança). A ADM também enxerga a corrente da DR.
- A troca de localidade passa pelo modal "Outros Meses" (formulário que contém `f_estabelecimento`), redireciona para `SIS99908` e, sem `#f-mudarpadrao`, não altera a localidade padrão do usuário.

## 3. Visão de cada profissional

### 3.1 Produto e usabilidade (UX)

Princípio: **reconhecer em vez de lembrar** (Nielsen). O usuário não deve saber de cor que a aplicação da conta X é 10396; deve reconhecer a opção certa numa lista curta, com o nome que ele vê no SIGA.

Leis e heurísticas aplicadas:
- **Prevenção de erro** (Nielsen #5) em vez de mensagem de erro: o campo só oferece códigos válidos para aquele grupo e localidade, então a inversão corrente/aplicação fica impossível.
- **Lei de Hick e efeito padrão:** quando há uma só opção válida, ela vem preenchida; quando há duas ou três, vem a lista com a mais provável pré-selecionada e marcada como "sugerida".
- **Carga cognitiva:** o card mostra o rótulo humano (`10396 · APLICACAO · ADM - DOURADOS - MS`), não só o número. O detalhe técnico (Cód. Contábil, agência) fica num tooltip ou linha secundária.
- **Visibilidade do estado do sistema** (Nielsen #1): cada card tem um selo com ícone **e** texto, nunca só cor:
  - ✔ **Confirmado**: mapeamento salvo pelo usuário.
  - ★ **Sugerido pelo SIGA**: preenchido pela descoberta e ainda não confirmado.
  - ? **Escolha necessária**: há mais de uma opção válida.
  - ✖ **Não encontrado**: nenhuma conta do SIGA bate, com o motivo.
- **Lei de Jakob:** os rótulos, as cores e a ordem dos campos imitam o SIGA (Localidade, Conta), que é o que o usuário já conhece.
- **Controle e liberdade:** um botão "Editar" abre os campos manualmente, mas eles continuam validados. Dá para desfazer a sugestão e voltar ao estado anterior.
- **Divulgação progressiva:** a descoberta roda sozinha quando falta algo; existe um botão discreto "Atualizar contas do SIGA" para forçar uma nova leitura. O usuário comum nunca precisa dele.

Fluxo principal (caminho feliz):
1. O usuário seleciona os extratos.
2. Os cards aparecem e o catálogo salvo já preenche o que der, como sugestão.
3. Se algum card ficar sem correspondência e o catálogo tiver mais de 30 dias ou não tiver aquela conta, aparece uma faixa no topo do lote: "2 contas não estão no catálogo. **Buscar no SIGA**".
4. A busca roda em segundo plano, com o progresso na barra de status ("Lendo Plano de Contas... 24 contas encontradas").
5. Os cards se atualizam. O usuário revisa os selos e clica em **Confirmar sugestões** (um clique para o lote inteiro) e depois em **Conciliar**.

Microtexto (claro, sem jargão, com a ação para resolver):
- Não encontrado: "A conta 58xxx não aparece nas localidades que você acessa no SIGA. Confira se o extrato é da Sicredi certa ou peça à administração para cadastrar a conta."
- Escolha: "Esta conta tem 2 aplicações no SIGA. Escolha a que corresponde ao extrato."
- Sem acesso: "Sem acesso à localidade PIA. As contas dela não puderam ser verificadas."

### 3.2 Design visual (paleta do SIGA)

O SIGA usa o tema **Ace (Bootstrap 3)**. O app já usa quase a mesma família de cores. A regra é **não inventar cor**: só tokens tirados do SIGA, centralizados num módulo `ui/tema.py`, em vez de hex soltos (hoje há ~25 hex espalhados em `ui/*.py`).

| Token | Cor | Origem no SIGA | Uso no card |
|---|---|---|---|
| `AZUL_TITULO` | `#3D71A8` | título de seção / widget-header (#4383B4) | título do card, links |
| `AZUL_NAVBAR` | `#2C6AA0` | barra superior | botão primário (texto branco 5,7:1) |
| `AZUL_INFO_FUNDO` / `AZUL_INFO_TEXTO` | `#D9EDF7` / `#31708F` | `.alert-info` | selo "Sugerido pelo SIGA" (4,5:1) |
| `VERDE_FUNDO` / `VERDE_TEXTO` | `#DFF0D8` / `#3C763D` | `.alert-success` | selo "Confirmado" (4,6:1) |
| `AMARELO_FUNDO` / `AMARELO_TEXTO` | `#FCF8E3` / `#8A6D3B` | `.alert-warning` | selo "Escolha necessária" (4,5:1) |
| `VERMELHO_FUNDO` / `VERMELHO_TEXTO` | `#F2DEDE` / `#A94442` | `.alert-danger` | selo "Não encontrado" (4,5:1) |
| `ROXO_MES` | `#A069C3` | chip "Mês de Trabalho" | etiqueta de competência (já usada no cabeçalho) |
| `VERDE_LOCAL` | `#69AA46` | chip "Localidade" | etiqueta de localidade no card (só borda ou ícone; 2,8:1 em texto) |
| `CINZA_TEXTO` / `CINZA_BORDA` | `#666666` / `#DDDDDD` | texto secundário, bordas de grade | linha secundária, borda neutra |

Cuidados de contraste (calculados, WCAG AA):
- O botão verde do SIGA (`#87B87F`, texto branco) tem **2,3:1** e o laranja (`#FFB752`) tem **1,7:1**: reprovam. No app, use os pares fundo claro + texto escuro dos alertas acima, ou o azul `#2C6AA0` para a ação primária.
- `#999999` em fundo branco (2,9:1) não serve para texto; use `#666666`.
- O estado nunca depende só de cor: o selo sempre tem ícone + palavra.

Layout do card (CustomTkinter, geometria dinâmica, sem coordenadas fixas):
```
┌ Conta Bancária 58xxx-2 · Conta Corrente ───────────── [★ Sugerido pelo SIGA] ┐
│ Localidade   [ADM - DOURADOS - MS            ▾]                               │
│ C. Corrente  [10130 · CAPTAÇÃO               ▾]                               │
│ C. Aplicação [10396 · APLICACAO              ▾]  (2 opções)                   │
│                                                      [Editar]  [Confirmar]    │
└───────────────────────────────────────────────────────────────────────────────┘
```
- Os combos mostram `código · finalidade`; o tooltip mostra o rótulo completo do SIGA.
- Tamanho mínimo de alvo ~32 px de altura (o padrão desktop do app). Ordem de Tab: Localidade → Corrente → Aplicação → Confirmar.
- Uma só ação primária por card (Confirmar); no lote, a primária é "Conciliar".

### 3.3 Arquitetura de software

Segue o MVC adaptado e o teto de 500 linhas. Nenhum arquivo grande cresce; entram módulos novos por responsabilidade.

| Camada | Arquivo | Responsabilidade |
|---|---|---|
| controller (puro) | `controllers/catalogo_contas.py` | `ContaSiga` (dataclass: código, grupo 101/103, localidade, banco, agência, CC em dígitos, finalidade, ativa, fonte); `ler_rotulo_tesouraria()`, `ler_linha_plano_contas()`; normalização de dígitos |
| controller (puro) | `controllers/sugestao_contas.py` | cruza `conta_id`/`produto` do extrato com o catálogo e devolve `Sugestao` (status, candidatos ordenados, motivo) |
| model | `models/config_catalogo.py` (mixin do `ConfigManager`, como `config_energia.py`) | grava/lê `catalogo_contas` no `config.json`: lista de contas, data da leitura, fonte, localidades sem acesso |
| bot | `bot/descoberta_contas.py` (mixin do `SigaBot`) | novo `tipo_lote="descoberta"`: tenta a CTB00301; se não houver acesso, percorre a TES01701 por localidade; restaura o contexto original |
| bot | `bot/sessao.py` | corrigir a troca de localidade: usar o formulário que contém `f_estabelecimento` e tornar `mudar_padrao` um parâmetro (descoberta = `False`) |
| ui | `ui/tema.py` | tokens de cor da seção 3.2 |
| ui | `ui/card_conta_extrato.py` | combos fechados, selo de estado, Confirmar/Editar; recebe a `Sugestao` pronta (sem regra de negócio na UI) |
| ui | `ui/lote_extratos.py` + `ui/acoes_siga.py` | faixa "Buscar no SIGA", disparo da thread de descoberta, "Confirmar sugestões" |

Contrato bot ↔ UI: o mesmo de sempre, dicionário de callbacks via `self.after(0, ...)`. A descoberta devolve o catálogo por um callback novo, `on_catalogo(catalogo)`, e não toca em widgets.

Formato salvo no `config.json` (compatível para trás; mapeamentos antigos continuam valendo e têm prioridade):
```json
"catalogo_contas": {
  "lido_em": "2026-10-23T14:05:00",
  "fonte": "CTB00301",
  "localidades_sem_acesso": [],
  "contas": [
    {"codigo": "10130", "grupo": "101", "localidade": "ADM - DOURADOS - MS",
     "banco": "SICREDI", "agencia": "101", "cc": "123456", "finalidade": "CAPTAÇÃO"}
  ]
}
```
A localidade é guardada como o SIGA mostra (`ADM - DOURADOS - MS`) e convertida para o par `tipo_adm`/`nome_adm` que o bot já usa (`ADM` + `DOURADOS - MS`). Isso evita duplicar a lógica de contexto.

### 3.4 Engenharia de IA (correspondência)

Não é caso de LLM. O problema é de **correspondência de registros** (record linkage) com poucas dezenas de candidatos, e precisa ser determinístico, explicável e offline. Um modelo generativo acrescentaria custo, latência, dependência de chave de API e envio de dados bancários para fora, sem ganho de acerto. O desenho usa as técnicas certas de IA clássica:

1. **Normalização** (feature engineering): só os dígitos da CC e da agência, zeros à esquerda removidos, comparação por igualdade ou por sufixo (o OFX pode vir com a agência ou o DV juntos). A finalidade é normalizada sem acento e em maiúsculas.
2. **Bloqueio** (blocking): os candidatos são só as contas cuja CC em dígitos bate com o `conta_id`. Restam de 1 a 4.
3. **Pontuação explicável**, com regras de peso fixo:
   - extrato de conta corrente → só o grupo 101; extrato de aplicação (XLS) → só o grupo 103;
   - produto `POUPANCA*` ↔ finalidade com `POUP`; `SICREDINVEST*` ↔ finalidade com `INV`/`APLIC`; sem pista, empate;
   - localidade igual à do último mapeamento confirmado dessa conta: bônus;
   - conta inativa: excluída.
4. **Decisão com limiar** (abstenção): um único candidato com a maior pontuação → "Sugerido"; empate → "Escolha necessária", com os empatados em ordem; nenhum → "Não encontrado". **O sistema nunca escolhe no empate**: em dinheiro, abster-se é melhor que errar.
5. **Aprendizado por confirmação** (human-in-the-loop): a escolha confirmada vira mapeamento salvo e vence qualquer sugestão futura. Se o catálogo novo não tiver mais aquela conta (ex.: inativada), o mapeamento confirmado é marcado como "Revisar".
6. **Explicabilidade:** cada sugestão guarda o motivo ("CC igual; grupo 103; produto POUPANCA ↔ POUPANÇA"), que aparece no tooltip do selo. Isso gera confiança e facilita o suporte.

### 3.5 Automação RPA (SIGA)

- **Ordem de tentativa:** CTB00301 primeiro. Se o menu ou a grade não abrir (sem acesso, redirecionamento ou `#grid1` ausente), cai para a TES01701.
- **CTB00301:** abrir pela URL, esperar o `#grid1`, aplicar `fnFilter('CC:')` e esperar `fnRecordsDisplay()` estabilizar (é server-side). Se passar de uma página, aumentar o `length` ou paginar. Ler as colunas por índice do `thead`, não por posição fixa.
- **TES01701 por localidade:** guardar o contexto atual (cabeçalho e mês); para cada `ADM`/`DR`/`PIA` presente no modal, trocar de localidade sem `mudar_padrao`, conferir com `_contexto_ativo_confere`, abrir a TES01701 e ler o `select#f_conta` (pulando o `optgroup INATIVO`). Se a troca não pegar ou o select vier vazio, a localidade vai para "sem acesso" e o bot segue. No fim, **restaurar sempre o contexto original**, num `finally`.
- **Esperas por condição**, não `sleep` fixo novo: elemento visível, cabeçalho com o texto esperado, contagem estável.
- **Somente leitura:** a descoberta não clica em Novo, Salvar nem em nada que grave. Falhas geram screenshot em `logs/screenshots/`, como o resto do bot.
- **Ponto já existente a corrigir:** `_ajustar_localidade_competencia` pega o primeiro botão Confirmar de `form.modal-form`, mas há dois formulários no modal; e marca `f-mudarpadrao`. Vai para a fase 2, com teste.

### 3.6 Qualidade e testes (estratégia por risco)

Risco mais alto: **lançar na conta errada** (impacto financeiro, difícil de desfazer). Por isso a correspondência e a validação recebem os testes mais fundos.

| Nível | O que cobre | Como |
|---|---|---|
| Unidade | Parser de rótulos (Tesouraria e Contabilidade) | Partição de equivalência com todos os formatos vistos: `AG:0101`, `AG: 0101`, CC com e sem hífen, `CONTA CAPITAL`, espaços duplos, acento, optgroup INATIVO |
| Unidade | Correspondência | **Tabela de decisão**: tipo de extrato × nº de candidatos × produto × mapeamento confirmado → status esperado. Inclui empate, inativa e a conta da DR visível na ADM |
| Unidade | Normalização | Testes de **propriedade** (Hypothesis, se entrar no `requirements-dev.txt`): formatação de CC com hífen/espaço/zeros não muda o resultado |
| Unidade | Persistência | `config.json` antigo sem `catalogo_contas` continua carregando; gravação atômica; mapeamento confirmado vence a sugestão |
| Bot (página falsa) | Descoberta | Como em `tests/bot_falso.py`: CTB com acesso; CTB sem acesso → TES01701; localidade que não troca → "sem acesso"; **contexto restaurado mesmo com exceção** |
| Bot (página falsa) | Troca de localidade | O botão usado é o do formulário com `f_estabelecimento`; `mudar_padrao=False` não marca o checkbox |
| UI | Estados do card | Lógica de estado extraída para função pura e testada; a tela é verificada manualmente nos 4 estados |
| Manual (exploratório) | SIGA real | Roteiro curto com usuário com Contabilidade e sem; lote misto (corrente + 2 aplicações da mesma CC) |

Critérios de aceite (Dado/Quando/Então):
- Dado um OFX de conta corrente cuja CC existe uma vez no grupo 101, quando o lote é carregado, então o card vem "Sugerido" com localidade, corrente e a única aplicação 103 da mesma CC.
- Dado um XLS de poupança cuja CC tem duas contas 103, quando o lote é carregado, então a aplicação sugerida é a de finalidade "POUPANÇA" e a outra fica disponível no combo.
- Dado um usuário sem acesso à CTB00301, quando a descoberta roda, então as contas vêm da TES01701 e, ao terminar, o cabeçalho do SIGA mostra a mesma localidade e o mesmo mês de antes.
- Dado um código digitado em Editar que não pertence ao grupo do campo, quando o campo perde o foco, então o card fica "Não encontrado" com a mensagem e o Conciliar continua bloqueado.

Fora dos testes automatizados: renderização real do CustomTkinter e o SIGA real (cobertos pelo roteiro manual). Gates: ruff, mypy (o novo `controllers/` entra no modo estrito) e pytest verdes no CI, como hoje.

### 3.7 Segurança e LGPD

- O catálogo guarda dados bancários da organização (agência e conta), não dados de pessoas físicas. Fica só no `config.json` local, que já guarda os mapeamentos, e **nunca vai para o git** (conferir no `.gitignore`).
- Nada é enviado para serviço externo (é um dos motivos para não usar LLM).
- Log: registrar só código SIGA e quantidade de contas, nunca a CC completa (mascarar como `58xxx-2`).
- A descoberta é só leitura no SIGA e não marca "mudar padrão", então não muda a configuração da conta do usuário.

### 3.8 Operação e suporte

- Primeira execução após atualizar: sem catálogo, os mapeamentos antigos continuam funcionando; a descoberta só roda quando faltar alguma conta ou quando o usuário pedir.
- Quando a descoberta falha, a barra de status e o log dizem em qual etapa (CTB, troca de localidade, TES01701), com screenshot.
- Documentar em `docs/regras/siga.md` (já feito) e registrar a novidade no `docs/CHANGELOG.md` na versão que entregar.

## 4. Fases de entrega

Cada fase é entregável sozinha, com testes, e já reduz erro.

| Fase | Entrega | Valor | Depende de |
|---|---|---|---|
| **1. Base pura** | `catalogo_contas.py` + `sugestao_contas.py` + mixin `config_catalogo.py`, com testes de unidade | Lógica pronta e provada sem tocar em UI nem no bot | — |
| **2. Bot de descoberta** | Mixin `descoberta_contas.py` (CTB → TES por localidade), correção da troca de localidade em `sessao.py`, testes com página falsa | Catálogo real salvo no `config.json` | 1 |
| **3. Card guiado** | `ui/tema.py`, card com combos fechados, selos, Confirmar/Editar, faixa "Buscar no SIGA" e "Confirmar sugestões" | O usuário para de digitar; inversão fica impossível | 1, 2 |
| **4. Validação e acabamento** | Bloqueio de Conciliar com código inválido, estado "Revisar" para mapeamento que sumiu do catálogo, CHANGELOG, roteiro manual no SIGA real | Fecha os casos de borda | 3 |

Estimativa grosseira: fase 1 pequena, fase 2 média (maior risco técnico: grade server-side e troca de contexto), fase 3 média (maior risco de UX), fase 4 pequena.

## 5. Riscos e mitigação

| Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|
| Rótulo com formato novo não previsto | Média | Conta "não encontrada" | Parser tolerante (só dígitos) + estado "Não encontrado" com edição manual validada; o formato novo vira caso de teste |
| SIGA mudar a CTB00301 ou o modal de localidade | Baixa | Descoberta falha | Fallback CTB → TES; falha clara com screenshot; os mapeamentos salvos continuam funcionando |
| Restaurar contexto falhar | Baixa | Usuário fica em outra localidade | `finally` + conferência do cabeçalho + aviso explícito na barra de status |
| Sugestão errada aceita sem ler | Média | Lançamento na conta errada | Abstenção no empate; selo "Sugerido" diferente de "Confirmado"; motivo visível; validação de grupo/localidade no Conciliar |
| Catálogo desatualizado (conta nova ou inativada) | Média | Falta de sugestão | Releitura automática quando falta conta ou o catálogo passa de 30 dias; botão de atualizar |

## 6. Decisões pendentes (para aprovar antes de codar)

1. Começar pela fase 1 (base pura) e seguir na ordem? **Recomendado.**
2. A descoberta roda **sozinha** ao carregar um lote com conta desconhecida (abre o Edge) ou só quando o usuário clica em "Buscar no SIGA"? Recomendado: faixa com o botão, sem abrir o navegador sem pedir, porque a sessão pode exigir login com reCAPTCHA.
3. Validade do catálogo: 30 dias? (as contas mudam pouco)
4. Adicionar `hypothesis` ao `requirements-dev.txt` para os testes de propriedade? (opcional)
