# Mapa do Repositorio

Este documento descreve a estrutura atual do repositorio, o papel de cada diretório e onde o time deve editar o codigo.

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

Os arquivos que devem ser editados no dia a dia ficam em:

- `src/`
- `infra/`
- `scripts/`
- `tests/`
- `docs/`

O diretório `function/` contem o host da Azure Function e o ponto de entrada do timer. Durante o publish, ele tambem recebe uma copia dos modulos de `src/`.

Regra pratica:

- se a mudanca for de regra de negocio ou integracao da aplicacao, edite `src/`
- se a mudanca for de host/publish da Azure Function, edite `function/`

## Diretorios e Arquivos

### `function/`

Contem o host da Azure Function.

Arquivos principais:

- `function/OffHoursTimer/__init__.py`
  Bootstrap do runtime no timer trigger.
- `function/OffHoursTimer/function.json`
  Definicao do timer trigger.
- `function/host.json`
  Configuracao base do host Functions.
- `function/local.settings.json.example`
  Exemplo de configuracao para execucao local.

Observacao:

- os modulos `config/`, `discovery/`, `handlers/`, `persistence/` e `scheduler/` nao ficam mais versionados dentro de `function/`
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
  Exemplo de parametros.
- `infra/bicep/main.parameters.json`
  Parametros reais do ambiente local.
- `infra/bicep/main.json`
  ARM compilado.

### `scripts/`

Automacao de deploy, bootstrap e publish.

Arquivos principais:

- `scripts/deploy_scheduler.sh`
  Wrapper recomendado de deploy.
- `scripts/bootstrap_scheduler_tables.sh`
  Seed default das tabelas.
- `scripts/prepare_function_app_publish.sh`
  Copia os modulos de `src/` para `function/`.

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

## Fluxos de Manutencao

### Mudar regra de negocio

Arquivos provaveis:

- `src/scheduler/models.py`
- `src/scheduler/engine.py`
- `src/scheduler/service.py`
- `tests/test_engine.py`
- `tests/test_scheduler_service.py`

### Mudar leitura das tabelas

Arquivos provaveis:

- `src/persistence/config_store.py`
- `src/persistence/state_store.py`
- `tests/test_config_store.py`

### Adicionar novo tipo de recurso

Arquivos provaveis:

- `src/handlers/base_handler.py`
- novo handler em `src/handlers/`
- `src/handlers/registry.py`
- possivelmente `src/discovery/resource_graph.py`

### Mudar host da Function

Arquivos provaveis:

- `function/OffHoursTimer/__init__.py`
- `function/OffHoursTimer/function.json`
- `function/host.json`
- `function/local.settings.json.example`

### Mudar deploy

Arquivos provaveis:

- `infra/bicep/main.bicep`
- `infra/bicep/modules/functionApp.bicep`
- `infra/bicep/modules/subscriptionRoles.bicep`
- `scripts/deploy_scheduler.sh`

## Regra de Trabalho

Se voce for alterar o comportamento do scheduler:

1. edite o codigo em `src/`
2. atualize os testes em `tests/`
3. rode `scripts/prepare_function_app_publish.sh` apenas quando precisar montar o bundle de publish

Essa separacao evita duplicacao de codigo e deixa mais claro o que e host da Function e o que e codigo fonte da aplicacao.
