# Documentacao Tecnica Detalhada

## 1. Objetivo

O Azure OffHours Scheduler automatiza start/stop de recursos Azure com base em tags e horarios definidos em YAML.

No estado atual, o foco de execucao real e VM (`Microsoft.Compute/virtualMachines`).

## 2. Visao por Camadas

```text
Azure Function (Timer)
  -> Scheduler Service (orquestracao)
    -> Discovery (Resource Graph)
    -> Schedule Engine (decisao START/STOP/SKIP)
    -> Worker Pool (ThreadPoolExecutor)
    -> Handler Registry
      -> VM Handler (acao Azure Compute)
    -> State Store (Azure Table Storage)
```

## 3. Camada: Function

Arquivo principal:
- `cmd/function_app/OffHoursTimer/__init__.py`

Responsabilidades:
- carregar configuracoes de ambiente (`Settings.from_env`)
- instanciar engine, discovery, handlers e scheduler service
- disparar o ciclo (`service.run()`)
- registrar resumo da execucao em log

Trigger:
- `cmd/function_app/OffHoursTimer/function.json`
- cron atual: `0 */5 * * * *` (a cada 5 minutos)

Observacao:
- `useMonitor: false` esta habilitado para simplificar teste local.

## 4. Camada: Discovery

Arquivo:
- `discovery/resource_graph.py`

Responsabilidades:
- consultar Azure Resource Graph
- filtrar apenas `microsoft.compute/virtualmachines` (escopo v1)
- filtrar recursos com a tag de schedule configurada
- retornar lista normalizada de `ScheduledResource`

Campos retornados por recurso:
- `id`
- `name`
- `type`
- `subscription_id`
- `resource_group`
- `tags`

Tag de schedule dinamica:
- controlada por `SCHEDULE_TAG_KEY`
- a query usa `tags['<chave>']`

## 5. Camada: Engine

Arquivo:
- `scheduler/engine.py`

Responsabilidades:
- ler `schedules.yaml`
- interpretar tag de schedule no recurso
- aplicar timezone (tag `timezone` ou `DEFAULT_TIMEZONE`)
- aplicar regras de skip por dia
- retornar decisao:
  - `START`
  - `STOP`
  - `SKIP`

Regras de formato de schedule:
- formato simples (retrocompativel):
  - `start` + `stop`
- formato avancado:
  - `periods` com uma ou mais janelas `start/stop`

Se qualquer periodo casar com a hora atual local do recurso, a decisao e `START`.

## 6. Camada: Scheduler Service

Arquivo:
- `scheduler/service.py`

Responsabilidades:
- orquestrar o ciclo fim-a-fim
- aplicar decisao do engine em cada recurso descoberto
- aplicar modo `DRY_RUN`
- processar recursos em paralelo com concorrencia controlada
- contabilizar resumo (`total`, `started`, `stopped`, `skipped`)

Regras operacionais importantes:
- sem handler para tipo de recurso -> `SKIP`
- `DRY_RUN=true` -> nao executa chamadas reais
- `MAX_WORKERS` controla o numero maximo de workers simultaneos
- checagem de estado antes da acao (via handler):
  - decisao `START` + estado `running` -> `SKIP`
  - decisao `STOP` + estado `stopped` -> `SKIP`
- `RETAIN_RUNNING=true` com persistencia:
  - fora da janela, se VM estiver `running` e foi ligada manualmente -> `SKIP`
  - fora da janela, se VM estiver `running` e foi ligada pelo scheduler -> `STOP`
- `RETAIN_STOPPED=true` com persistencia:
  - dentro da janela, se VM estiver `stopped` e foi parada manualmente -> `SKIP`
  - dentro da janela, se VM estiver `stopped` e foi parada pelo scheduler -> `START`

Persistencia de estado:
- arquivo: `persistence/state_store.py`
- backend: Azure Table Storage
- campo principal de decisao: `StartedByScheduler`

## 7. Camada: Handlers

Arquivos:
- `handlers/base_handler.py`
- `handlers/registry.py`
- `handlers/vm_handler.py`

### 7.1 Base Handler

Contrato minimo por recurso:
- `get_state(resource) -> str`
- `start(resource) -> None`
- `stop(resource) -> None`

### 7.2 Registry

Mapeia `resource_type` (lowercase) para handler concreto.

### 7.3 VM Handler

Suporta:
- `microsoft.compute/virtualmachines`

Implementa:
- `get_state`: consulta `instance_view` e normaliza para:
  - `running`
  - `stopped`
  - `unknown`
- `start`: `begin_start(...).result()`
- `stop`: `begin_deallocate(...).result()`

## 8. Camada: State Store

Arquivo:
- `persistence/state_store.py`

Implementacoes:
- `NoopStateStore` (fallback)
- `AzureTableStateStore` (persistencia real)

Dados persistidos por VM:
- `ResourceId`
- `StartedByScheduler`
- `StoppedByScheduler`
- `LastObservedState`
- `LastAction`
- `UpdatedAtUtc`

Chaves da tabela:
- `PartitionKey = subscription_id`
- `RowKey = sha1(resource_id)`

## 9. Schedules

Arquivo:
- `schedules/schedules.yaml`

Exemplo:

```yaml
office-hours:
  start: "08:00"
  stop: "19:00"

lab:
  periods:
    - start: "09:00"
      stop: "12:00"
    - start: "13:00"
      stop: "18:00"

weekend-off:
  start: "08:00"
  stop: "19:00"
  skip_days:
    - saturday
    - sunday
```

Uso por tag no recurso:
- `schedule=office-hours` (ou outra chave definida em `SCHEDULE_TAG_KEY`)

## 10. Configuracoes Alteraveis

Fonte:
- `cmd/function_app/local.settings.json`

### 9.1 Parametros de ambiente

- `AzureWebJobsStorage`
  - storage da Function Runtime
  - local: normalmente `UseDevelopmentStorage=true` (requer Azurite)

- `FUNCTIONS_WORKER_RUNTIME`
  - runtime da Function
  - valor esperado: `python`

- `AZURE_SUBSCRIPTION_IDS`
  - lista de subscriptions alvo, separadas por virgula
  - ex.: `sub1,sub2`

- `SCHEDULES_FILE`
  - caminho do YAML de schedules
  - ex. atual: `../../schedules/schedules.yaml`

- `DRY_RUN`
  - `true|false`
  - `true`: nao executa start/stop real

- `DEFAULT_TIMEZONE`
  - timezone padrao quando tag `timezone` nao existe
  - ex.: `America/Sao_Paulo`

- `SCHEDULE_TAG_KEY`
  - nome da tag de schedule nos recursos
  - padrao: `schedule`

- `RETAIN_RUNNING`
  - `true|false`
  - habilita regra de manual override com historico persistido

- `RETAIN_STOPPED`
  - `true|false`
  - habilita regra para manter VM parada manualmente mesmo dentro da janela de start

- `STATE_STORAGE_CONNECTION_STRING`
  - connection string do Azure Table Storage de estado
  - se vazio, usa fallback `AzureWebJobsStorage`

- `STATE_STORAGE_TABLE_NAME`
  - nome da tabela de persistencia
  - padrao: `OffHoursSchedulerState`

- `MAX_WORKERS`
  - inteiro > 0
  - define concorrencia maxima do worker pool (padrao: `5`)

### 9.2 Parametros de schedule (YAML)

Por schedule:
- `start` / `stop` (formato simples)
- `periods` (formato avancado)
- `skip_days` (opcional)

Regras:
- `start/stop` em `HH:MM`
- `periods` deve ser lista nao vazia
- `skip_days` deve usar nomes de dia em ingles minusculo (`saturday`, `sunday`, ...)

## 11. Fluxo de Execucao (passo a passo)

1. Timer dispara a Function.
2. Function carrega settings.
3. Discovery consulta Resource Graph por recursos com tag de schedule.
4. Para cada recurso, engine avalia horario e retorna decisao.
5. Scheduler valida handler e modo (`DRY_RUN`/real).
6. Em execucao real, scheduler consulta estado atual via handler.
7. Scheduler consulta/salva estado historico no state store.
8. Scheduler aplica regras de skip/start/stop.
9. Scheduler gera resumo e Function registra log final.

## 12. Limites Atuais

- Sem regra especifica de `stop_new_instances`
- Foco operacional atual em VM

## 13. Proximos Passos Naturais

- expandir handlers (App Service, SQL, VMSS)
- validar sobreposicao de periodos no carregamento de schedules
- adicionar metricas estruturadas por schedule/resource
