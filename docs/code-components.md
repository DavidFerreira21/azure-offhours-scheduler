# Componentes de Codigo

Este documento descreve os componentes de codigo do runtime e a responsabilidade de cada camada.

Se voce quiser entender a estrutura do repositorio ou onde editar cada tipo de mudanca, use `repository-map.md`.
Se voce quiser um guia de manutencao passo a passo, use `developer-guide.md`.

## Fluxo do Runtime

```text
OffHoursTimer
  -> Settings
  -> Config Stores
  -> Discovery
  -> Schedule Engine
  -> Handler Registry
  -> Resource Handlers
  -> State Store
  -> SchedulerService
  -> Report Builder
  -> Structured Report
```

## 1. Entry Point da Azure Function

Arquivo:

- `function/OffHoursTimer/__init__.py`

Responsabilidades:

- receber o disparo do timer
- gerar `run_id` para o ciclo
- montar o `sys.path` para execucao local e em Azure
- carregar `Settings.from_env()`
- carregar configuracao global e schedules das tabelas
- montar discovery, engine, registry e state store
- instanciar `SchedulerService`
- montar o relatorio final
- registrar o resumo final e o JSON estruturado do ciclo

Essa camada faz bootstrap. Ela nao concentra a logica principal de avaliacao.

## 2. Configuracao Tecnica

Arquivo:

- `src/config/settings.py`

Responsabilidades:

- ler `AZURE_SUBSCRIPTION_IDS`
- ler `TARGET_RESOURCE_LOCATIONS`
- ler connection string das tabelas
- ler nomes das tabelas
- ler `MAX_WORKERS`
- ler `ENABLE_VERBOSE_AZURE_SDK_LOGS`
- ler `RESOURCE_RESULT_LOG_MODE`

O papel desse modulo e ler apenas configuracao tecnica do ambiente. A configuracao operacional continua vindo das tabelas.

Observacao:

- o cron tecnico do timer vem da app setting `TIMER_SCHEDULE`, resolvida pelo host da Function

## 3. Modelos do Dominio

Arquivo:

- `src/scheduler/models.py`

Componentes principais:

- `SchedulePeriod`
  Janela simples de `start` e `stop`.
- `ScheduleScope`
  Escopo include/exclude por subscription e management group.
- `ScheduleDefinition`
  Schedule completo carregado da tabela.
- `GlobalSchedulerConfig`
  Configuracao global do ciclo.

Ponto importante:

- `ScheduleScope` faz normalizacao de subscription IDs e management groups para comparacao confiavel

## 4. Leitura da Configuracao em Azure Table Storage

Arquivos:

- `src/persistence/config_store.py`
- `src/persistence/state_store.py`

### `src/persistence/config_store.py`

Responsabilidades:

- ler a configuracao global `GLOBAL/runtime`
- ler todos os schedules ativos
- validar audit trail
- interpretar booleans, listas, janelas e escopo

Classes principais:

- `AzureTableGlobalConfigStore`
- `AzureTableScheduleStore`

Funcoes auxiliares importantes:

- `_parse_bool`
- `_parse_iso_datetime`
- `_parse_string_list`
- `_parse_periods`
- `_require_audit_fields`

### `src/persistence/state_store.py`

Responsabilidades:

- ler o ultimo estado operacional do recurso
- persistir se o recurso foi iniciado ou parado pelo scheduler
- suportar regras `retain_running` e `retain_stopped`

Classes principais:

- `SchedulerState`
- `NoopStateStore`
- `AzureTableStateStore`

Ponto importante:

- o `RowKey` e derivado de hash do `resource.id` canonizado para evitar duplicidade por diferenca de casing ou barra final

## 5. Discovery

Arquivo:

- `src/discovery/resource_graph.py`

Responsabilidades:

- consultar Azure Resource Graph
- buscar apenas recursos suportados
- exigir a tag de agendamento configurada
- trazer `location`, `subscriptionId`, `resourceGroup` e `tags`
- resolver `managementGroupAncestorsChain` a partir de `ResourceContainers`
- aplicar o filtro tecnico de `TARGET_RESOURCE_LOCATIONS`

Componentes principais:

- `ScheduledResource`
- `ResourceGraphDiscovery`

Metodos principais:

- `_build_query()`
- `_extract_management_group_ids()`
- `find_scheduled_resources()`

## 6. Engine de Decisao

Arquivo:

- `src/scheduler/engine.py`

Responsabilidades:

- ler a tag de schedule do recurso
- localizar o schedule correspondente
- validar se o recurso esta no escopo do schedule
- resolver timezone
- aplicar `skip_days`
- decidir se o horario atual implica `START`, `STOP` ou `SKIP`

Estruturas principais:

- `Decision`
- `EvaluationResult`
- `ScheduleEngine`

Essa e a principal camada de regra de negocio pura.

## 7. Orquestracao do Ciclo

Arquivo:

- `src/scheduler/service.py`

Responsabilidades:

- pedir recursos ao discovery
- processar recursos em paralelo
- avaliar cada recurso no `ScheduleEngine`
- localizar o handler correto
- aplicar `dry_run`
- consultar estado atual
- aplicar regras de retencao
- chamar `start()` ou `stop()`
- persistir estado quando necessario
- medir duracao total e por recurso
- propagar `run_id`
- consolidar resumo e resultados estruturados do ciclo
- aplicar a politica de emissao de logs estruturados por recurso

Estruturas principais:

- `SchedulerSummary`
- `ActionOutcome`
- `ResourceExecutionResult`
- `SchedulerRunResult`
- `SchedulerService`

Esse arquivo e o orquestrador principal do runtime.

## 8. Relatorio Estruturado

Arquivo:

- `src/reporting/report_builder.py`

Responsabilidades:

- transformar o resultado final do `SchedulerService` em um payload simples e serializavel
- manter o formato do relatorio final estavel
- separar a montagem do JSON final da logica do service

Estrutura principal do payload:

- `run_id`
- `timestamp`
- `dry_run`
- `summary`
- `duration_sec`
- `resources`

## 9. Handlers por Tipo de Recurso

Arquivos:

- `src/handlers/base_handler.py`
- `src/handlers/registry.py`
- `src/handlers/vm_handler.py`

### `src/handlers/base_handler.py`

Define o contrato minimo dos handlers:

- `get_state()`
- `start()`
- `stop()`

### `src/handlers/registry.py`

Mantem o mapeamento entre tipo de recurso Azure e handler responsavel.

### `src/handlers/vm_handler.py`

Implementacao atual para:

- `Microsoft.Compute/virtualMachines`

Responsabilidades:

- criar `ComputeManagementClient` por subscription
- consultar estado da VM via `instance_view`
- iniciar VM com `begin_start`
- desligar VM com `begin_deallocate`

## 10. Scripts Operacionais

Os scripts nao fazem parte do runtime principal, mas sustentam deploy, bootstrap e publish.

Arquivos:

- `scripts/deploy_scheduler.sh`
- `scripts/bootstrap_scheduler_tables.sh`
- `scripts/prepare_function_app_publish.sh`

### `scripts/deploy_scheduler.sh`

Responsabilidades:

- validar ferramentas locais
- validar autenticacao Azure
- resolver escopo tecnico efetivo
- validar o Bicep
- executar o deploy
- bootstrap das tabelas
- preparar o bundle da Function
- publicar a Function

### `scripts/bootstrap_scheduler_tables.sh`

Responsabilidades:

- criar a configuracao global default se ela nao existir
- criar o schedule `business-hours` se ele nao existir

### `scripts/prepare_function_app_publish.sh`

Responsabilidades:

- limpar artefatos antigos do host
- copiar `src/config`, `src/discovery`, `src/handlers`, `src/persistence`, `src/reporting` e `src/scheduler` para `function/`
- deixar o bundle pronto para publish

## 11. Infraestrutura

Infraestrutura nao faz parte do codigo de negocio, mas define o ambiente tecnico em que o runtime executa.

Arquivos:

- `infra/bicep/main.bicep`
- `infra/bicep/modules/functionApp.bicep`
- `infra/bicep/modules/subscriptionRoles.bicep`

### `infra/bicep/main.bicep`

Responsabilidades:

- receber parametros principais
- orquestrar os modulos
- expor outputs relevantes

### `infra/bicep/modules/functionApp.bicep`

Responsabilidades:

- criar Storage Account
- criar as 3 tabelas
- criar observabilidade
- criar App Service Plan e Function App
- configurar app settings
- atribuir RBAC opcional ao grupo operador das tabelas

### `infra/bicep/modules/subscriptionRoles.bicep`

Responsabilidades:

- atribuir `Reader`
- atribuir `Virtual Machine Contributor`

Esses papeis sao aplicados por subscription no escopo efetivo resolvido pelo wrapper.

## 12. Testes

Os testes refletem a divisao principal das camadas do runtime.

Arquivos:

- `tests/conftest.py`
- `tests/test_settings.py`
- `tests/test_config_store.py`
- `tests/test_discovery.py`
- `tests/test_engine.py`
- `tests/test_scheduler_service.py`

Distribuicao:

- `tests/conftest.py`
  adiciona `src/` ao `sys.path`
- `tests/test_settings.py`
  configuracao tecnica
- `tests/test_config_store.py`
  parsing e validacao das tabelas
- `tests/test_discovery.py`
  query e filtro tecnico do discovery
- `tests/test_engine.py`
  regras do engine
- `tests/test_scheduler_service.py`
  orquestracao e retencao

## Resumo

Separacao de responsabilidades:

- `function/`
  host da Azure Function
- `src/`
  codigo da aplicacao
- `scripts/`
  automacao operacional
- `infra/bicep/`
  infraestrutura
- `tests/`
  validacao automatizada
