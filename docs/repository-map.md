# Mapa do Repositorio

Este documento descreve a estrutura atual do repositorio, a fonte da verdade de cada area e onde editar cada tipo de mudanca.

## Visao Geral

A estrutura foi organizada para separar claramente:

- host da Azure Function
- codigo fonte da aplicacao
- infraestrutura
- scripts operacionais
- testes

## Estrutura Principal

```text
azure-offhours-scheduler
├─ function/
├─ src/
├─ infra/
├─ scripts/
├─ tests/
└─ docs/
```

## Fonte da Verdade

No dia a dia, a regra pratica e esta:

- `src/`
  Codigo da aplicacao.
- `function/`
  Host da Azure Function.
- `infra/`
  Infraestrutura e app settings.
- `scripts/`
  Automacao operacional.
- `tests/`
  Validacao automatizada.
- `docs/`
  Documentacao do projeto.

O diretório `function/` contem o host da Azure Function e o ponto de entrada do timer. Durante o publish, ele tambem recebe uma copia dos modulos de `src/`. Esses modulos copiados nao sao a fonte da verdade.

Regra pratica:

- se a mudanca for de regra de negocio ou integracao da aplicacao, edite `src/`
- se a mudanca for de host/publish da Azure Function, edite `function/`

## Diretorios e Arquivos

### `function/`

Contem apenas o host da Azure Function e o ponto de entrada do timer.

Arquivos principais:

- `function/OffHoursTimer/__init__.py`
  Bootstrap do runtime no timer trigger.
- `function/OffHoursTimer/function.json`
  Timer trigger que referencia `%TIMER_SCHEDULE%`.
  Definicao do timer trigger.
- `function/host.json`
  Configuracao base do host Functions.
- `function/local.settings.json.example`
  Exemplo de configuracao para execucao local.

Observacao:

- os modulos `config/`, `discovery/`, `handlers/`, `persistence/`, `reporting/` e `scheduler/` nao ficam mais versionados dentro de `function/`
- eles sao copiados de `src/` por `scripts/prepare_function_app_publish.sh`
- `function/requirements.txt` tambem e gerado por `scripts/prepare_function_app_publish.sh`, a partir do `requirements.txt` da raiz

### `src/`

Contem o codigo fonte principal da aplicacao.

Subdiretorios:

- `src/config/`
  Configuracao tecnica de runtime.
- `src/discovery/`
  Descoberta de recursos no Azure.
- `src/handlers/`
  Execucao por tipo de recurso.
- `src/persistence/`
  Leitura e escrita em Azure Table Storage.
- `src/reporting/`
  Montagem do relatorio estruturado final.
- `src/scheduler/`
  Modelos, engine e orquestracao do scheduler.

### `infra/bicep/`

Infraestrutura como codigo.

Arquivos principais:

- `infra/bicep/main.bicep`
  Template principal em escopo de subscription.
- `infra/bicep/modules/functionApp.bicep`
  Cria Storage, tabelas, observabilidade e Function App.
- `infra/bicep/modules/subscriptionRoles.bicep`
  Atribui RBAC no escopo tecnico efetivo.
- `infra/bicep/main.parameters.example.json`
  Exemplo mais completo de parametros.
- `infra/bicep/main.parameters.json`
  Parametros reais do ambiente local. Se `resourceGroupName` ficar vazio, o wrapper gera um RG automaticamente a partir de `namePrefix`.
- `infra/bicep/main.json`
  ARM compilado.

### `scripts/`

Automacao de deploy e publish.

Arquivos principais:

- `scripts/deploy_scheduler.sh`
  Wrapper recomendado de deploy, publish, sync de triggers, geracao opcional do RG e orientacoes finais de seed operacional.
- `scripts/prepare_function_app_publish.sh`
  Copia os modulos de `src/` para `function/` e limpa artefatos antigos.
- `scripts/build_function_app_package.sh`
  Empacota o diretório `function/` em um zip deterministico para publish.

### `tests/`

Cobertura unitária do runtime.

Arquivos principais:

- `tests/conftest.py`
  Coloca `src/` no `sys.path` dos testes.
- `tests/test_settings.py`
  Testa leitura de configuracao tecnica.
- `tests/test_config_store.py`
  Testa parsing e validacao das tabelas.
- `tests/test_discovery.py`
  Testa query e filtro tecnico do discovery.
- `tests/test_engine.py`
  Testa a logica do engine.
- `tests/test_scheduler_service.py`
  Testa a orquestracao do ciclo.
- `tests/test_report_builder.py`
  Testa o formato do relatorio estruturado.
- `tests/test_state_store.py`
  Testa a estabilidade da chave da tabela de state.

## Onde Editar Cada Tipo de Mudanca

Se a mudanca for:

- regra de horario, escopo ou retencao:
  edite `src/scheduler/` e os testes relacionados
- formato das tabelas:
  edite `src/persistence/`
- discovery ou filtro tecnico:
  edite `src/discovery/`
- novo tipo de recurso:
  edite `src/handlers/` e, se necessario, `src/discovery/`
- host da Function:
  edite `function/`
- deploy e app settings:
  edite `infra/bicep/` e `scripts/deploy_scheduler.sh`
- bundle de publish:
  edite `scripts/prepare_function_app_publish.sh` e `scripts/build_function_app_package.sh`
- documentacao:
  edite `docs/` e `README.md`

## Regra de Trabalho

Se voce for alterar o comportamento do scheduler:

1. edite o codigo em `src/`
2. atualize os testes em `tests/`
3. rode `scripts/prepare_function_app_publish.sh` quando precisar sincronizar o host de publish
4. rode `scripts/build_function_app_package.sh` quando precisar inspecionar ou publicar o zip final

Essa separacao evita duplicacao de codigo e deixa claro o que e host da Function e o que e codigo fonte da aplicacao.
