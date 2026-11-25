# AutoSIGA — regras do projeto

Fonte única de instruções para qualquer IA (Antigravity lê direto; o `CLAUDE.md` da raiz só importa este arquivo). Mantenha-o curto: detalhe longo vai para `docs/` e é lido sob demanda.

RPA desktop para Windows (CustomTkinter + Playwright/Edge) que concilia extratos bancários (`.ofx`, `.xls`/`.xlsx` Sicredi e Sicoob) e faturas de energia (PDF via Gmail ou pasta local) com o sistema web SIGA, lançando o que falta.

## Comandos

```powershell
venv\Scripts\pip install -r requirements-dev.txt                 # app + pytest, ruff e mypy
venv\Scripts\python main.py                                    # roda o app
venv\Scripts\python -m pytest -q tests/                        # suíte completa (mesma do CI)
venv\Scripts\python -m pytest -q tests/test_conciliador.py::nome_do_teste   # teste único
venv\Scripts\ruff check . --output-format=concise              # lint (--fix corrige o seguro)
venv\Scripts\mypy                                             # tipos (arquivos em pyproject.toml)
pyinstaller --noconfirm AutoSIGA.spec                          # build onedir em dist/AutoSiga/
```

A `venv` usa **Python 3.11**, igual ao CI e ao build (`uv python install 3.11`). Configuração de pytest, ruff e mypy no `pyproject.toml`; o mypy confere tudo em `controllers/` e `models/` (`check_untyped_defs`); em `bot/` e `ui/` ainda só as funções anotadas.

CI (`.github/workflows/ci_cd.yml`, Windows, Python 3.11): ruff, mypy e pytest em push/PR para `master`; tag `v*` gera o build e publica `AutoSiga_Windows.zip` (pasta inteira, com `_internal`) na Release.

## Arquitetura (MVC adaptado — o que cada arquivo faz está em `docs/arquitetura.md`, leia só a seção da camada)

- `main.py`: `sys.path`, backend do `keyring`, `.env` legado, log diário em `logs/` e abre `ui.main_window.MainWindow`.
- `models/`: só I/O, sem UI. `config_manager.py` (+ mixins `config_energia`, `config_catalogo`) persiste tudo em `config.json` com gravação atômica. Leitores de extrato (`ofx_reader`, `xls_reader`, `xls_conta_corrente`, `xls_sicoob`) devolvem o mesmo formato; `pdf_extractor` e `email_reader` cuidam das faturas.
- `controllers/`: regras de negócio puras e testáveis. `classificador_extrato` é a fonte única do que cada linha do extrato é (regras em `regras_extrato.json`); `conciliador` (tolerância de 1 centavo), `prova_real`, `baixa_energia`, `baixa_contas_pagar`, `transferencias_internas`, `exportador` etc.
- `bot/`: `SigaBot` (`siga_bot.py`) roda numa thread, por CDP num Edge à parte (`navegador.py`) que fica aberto e logado. Um mixin por rotina do SIGA (`fluxo_extratos`, `extratos`, `energia`, `provisoes_energia`, `baixa_provisoes`, `baixa_contas_pagar`, `transferencias_internas`, `tarifas`, `ofertas`, `descoberta_contas`...). Ramifica por `tipo_lote` (`extrato`, `energia`, `ofertas`, `descoberta`). Falhas geram screenshot em `logs/screenshots/`.
- `ui/`: `main_window.py` + mixins (`credenciais`, `lote_extratos`, `acoes_siga`, `catalogo_siga`, `dashboard`), `card_conta_extrato.py`, `panel_energia.py` + `modais_energia.py`. Cores só pelos tokens de `ui/tema.py`.
- Bot ↔ UI só por dicionário de **callbacks** (`update_status`, `show_message`, `update_progress`, `show_dashboard`, `on_finish`, `request_authorization`, `request_uc_mapping`, `on_localidades_siga`, `on_catalogo`). Na UI, todo callback da thread do bot passa por `self.after(0, ...)`; nunca tocar widgets direto da thread do bot.
- **Telas do SIGA** (campos `#f_*`, rotinas, menus, iframe): `docs/regras/siga.md` antes de mexer em `bot/`. É grande: busque o título da rotina (`grep -n "^## "`) e leia só aquela seção.
- **Regras da Tesouraria CCB**: índice em `docs/tesouraria/README.md`; leia só o tópico da tarefa.

## Convenções

- **Versão**: definida só em `version.py` (`VERSION`); nunca hardcoded em UI, modais, logs ou spec. Ao subir a versão: nova seção no topo de `docs/CHANGELOG.md`, e no `README.md` trocar o título e a seção "Destaques da Versão" (o README mostra só a versão atual).
- **Caminhos de dados**: usar `caminhos.diretorio_base()` para tudo que o usuário mantém entre versões (`config.json`, `.env`, `credentials.json`, `token.json`, `logs/`, `faturas_energisa/`). No executável aponta para a pasta do `AutoSiga.exe`, não para `_internal` (substituída a cada atualização); calcular a partir de `__file__` quebra isso.
- **Credenciais do SIGA**: Windows Keyring (serviço `"AutoSIGA"`) com fallback para `SIGA_USUARIO`/`SIGA_SENHA` do `.env`.
- Teto de 500 linhas por `.py`, auditado por `tests/test_tamanho_arquivos.py`. Ao adicionar funcionalidade ao bot ou à janela, crie ou estenda o mixin da responsabilidade em vez de crescer `siga_bot.py`/`main_window.py`.
- Testes em `tests/` (fixtures em `tests/fixtures/`), sem `conftest.py`; o bot é testado com páginas falsas (classes que imitam `page`), sem navegador. `*.ofx` está no `.gitignore`: fixture nova de OFX precisa de `git add -f`.

## Handoff entre ferramentas (Claude Code ↔ Antigravity)

O estado da tarefa em andamento fica em `.agents/handoff.md` (fora do git).
- Usuário diz **"handoff"** (ou os tokens estão acabando): reescreva o arquivo, curto, com: tarefa e objetivo, o que já foi feito, decisões tomadas, arquivos alterados, como verificar e próximo passo exato. Substitua o conteúdo anterior, não acumule histórico.
- Usuário diz **"continuar"**: leia `.agents/handoff.md` antes de qualquer outra coisa e retome do próximo passo, sem reexplorar o que já está registrado.
- Concluída a tarefa (commit feito), esvazie o arquivo.

## Economia de contexto

- Não ler `dist/`, `build/`, `logs/`, `venv/`, `siga_browser_data/`, `faturas_energisa/` nem os dados locais (`config.json`, `token.json`, `credentials.json`); o `.claude/settings.json` bloqueia.
- `docs/CHANGELOG.md` é grande: leia só a seção do topo (`head -40`).
- Testes e lint com saída curta: o pytest já roda com `-q --tb=short`; ruff com `--output-format=concise`. Rode o teste do arquivo mexido antes da suíte inteira.
