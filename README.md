# Azure OffHours Scheduler

Azure OffHours Scheduler e uma ferramenta open source para iniciar e parar recursos Azure com base em horarios definidos por tags.
O foco principal e reduzir custos em ambientes nao produtivos, como dev, hml, sandbox e labs.
No estado atual, o scheduler executa acoes reais para Virtual Machines (`Microsoft.Compute/virtualMachines`).

## Documentacao Detalhada

- Arquitetura e camadas da aplicacao: `docs/architecture.md`
- Infraestrutura com Bicep: `infra/bicep/main.bicep`

## Problema

Em muitos ambientes Azure, recursos ficam ligados 24x7 sem necessidade:

- VMs de desenvolvimento durante a madrugada
- Ambientes de teste ociosos fora do horario comercial
- Sandbox ligado em fins de semana

Apesar de existirem alternativas (Runbooks, Logic Apps, Automation Accounts), normalmente elas exigem configuracao mais complexa e alvo manual de recursos.

Este projeto resolve isso com um modelo simples:

```text
schedule=office-hours
```

Comportamento esperado:

```text
08:00 -> START
19:00 -> STOP
```

## Visao Geral da Solucao

Fluxo de alto nivel:

```text
Timer Trigger (Azure Function)
        ->
Discovery (Azure Resource Graph)
        ->
Schedule Engine
        ->
Handlers por tipo de recurso
        ->
START / STOP / SKIP
```

Principios:

- Configuracao por tags
- Suporte multi-subscription
- Arquitetura com estado opcional (Azure Table Storage)
- Extensibilidade para novos tipos de recurso

## Estado Atual (v1)

Implementado no repositorio:

- Azure Function com timer a cada 2 minutos (`0 */2 * * * *`)
- Discovery via Azure Resource Graph
- Engine de decisao com retorno `START`, `STOP` ou `SKIP`
- Handler de Virtual Machine (`begin_start` / `begin_deallocate`)
- Configuracao de schedules em YAML
- Persistencia opcional de estado para regras `RETAIN_*`
- Testes unitarios do engine e do scheduler service

## Estrutura do Projeto

```text
azure-offhours-scheduler
├─ cmd/
│  └─ function_app/
│     ├─ host.json
│     ├─ local.settings.json.example
│     ├─ requirements.txt
│     └─ OffHoursTimer/
│        ├─ __init__.py
│        └─ function.json
├─ config/
│  └─ settings.py
├─ discovery/
│  └─ resource_graph.py
├─ handlers/
│  ├─ base_handler.py
│  ├─ registry.py
│  └─ vm_handler.py
├─ persistence/
│  └─ state_store.py
├─ scheduler/
│  ├─ engine.py
│  └─ service.py
├─ schedules/
│  └─ schedules.yaml
├─ tests/
└─ requirements.txt
```

## Configuracao por Tags

Minimo:

```text
schedule=office-hours
```

A chave `schedule` e o padrao. Se quiser usar outro nome de tag, configure `SCHEDULE_TAG_KEY` no `local.settings.json`.

Com timezone:

```text
schedule=office-hours
timezone=America/Sao_Paulo
```

Se a tag `timezone` nao existir no recurso, a Function usa `DEFAULT_TIMEZONE` do `local.settings.json`.

## Configuracao de Schedules

Arquivo: `schedules/schedules.yaml`

Exemplo:

```yaml
office-hours:
  start: "08:00"
  stop: "23:13"

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

Voce pode usar:
- formato simples: `start/stop`
- formato avancado: `periods` com multiplas janelas no mesmo schedule

## Como Testar Localmente

### 1. Preparar ambiente Python

No WSL/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

No PowerShell (Windows):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

### 2. Rodar testes unitarios

```bash
pytest -q
```

### 3. Configurar a Function App local

Entre em `cmd/function_app` e crie o arquivo de settings:

```bash
cd cmd/function_app
cp local.settings.json.example local.settings.json
```

Edite `local.settings.json` e preencha:

- `AZURE_SUBSCRIPTION_IDS`: IDs separados por virgula
- `SCHEDULES_FILE`: padrao `../../schedules/schedules.yaml`
- `DRY_RUN`: `true` para nao executar start/stop real
- `DEFAULT_TIMEZONE`: timezone padrao global (ex.: `America/Sao_Paulo`)
- `SCHEDULE_TAG_KEY`: chave da tag de agendamento (padrao `schedule`)
- `RETAIN_RUNNING`: habilita regra de manual override com persistencia
- `RETAIN_STOPPED`: habilita regra para respeitar VM parada manualmente dentro da janela de start
- `MAX_WORKERS`: concorrencia maxima do worker pool (padrao `5`)
- `STATE_STORAGE_CONNECTION_STRING`: conexao do Azure Table Storage de estado (fallback para `AzureWebJobsStorage` se vazio)
- `STATE_STORAGE_TABLE_NAME`: nome da tabela de estado (padrao `OffHoursSchedulerState`)

Observacao importante:
- se `RETAIN_RUNNING=true` ou `RETAIN_STOPPED=true` e `STATE_STORAGE_CONNECTION_STRING` nao estiver definido, o scheduler continua funcionando, mas sem persistencia real (NoopStateStore).

### 4. Instalar Azure Functions Core Tools (se necessario)

No Ubuntu 24.04 (WSL):

```bash
sudo apt update
sudo apt install -y curl gpg
curl https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor | sudo tee /usr/share/keyrings/microsoft.gpg > /dev/null
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft.gpg] https://packages.microsoft.com/ubuntu/24.04/prod noble main" | sudo tee /etc/apt/sources.list.d/microsoft-prod.list
sudo apt update
sudo apt install -y azure-functions-core-tools-4
```

Validar instalacao:

```bash
func --version
```

### 5. Subir Function local

```bash
cd cmd/function_app
func start
```

## Erros Comuns e Solucao

### 1) `source : The term 'source' is not recognized`

Voce esta no PowerShell. Use:

```powershell
.\.venv\Scripts\Activate.ps1
```

### 2) `func: command not found`

Azure Functions Core Tools nao instalado no ambiente atual.
Instale conforme secao acima.

### 3) `Connection refused (127.0.0.1:10000)`

`AzureWebJobsStorage` esta como `UseDevelopmentStorage=true` e o Azurite nao esta rodando.

Opcao A (recomendada para teste local): iniciar Azurite.

Opcao B: usar connection string real de uma Storage Account Azure em `AzureWebJobsStorage`.

### 4) `No module named 'config'`

Esse erro em Azure indica que o pacote publicado nao inclui os modulos da aplicacao.
Antes do publish, execute:

```bash
./scripts/prepare_function_app_publish.sh
```

E depois publique novamente a Function App.

## Dry Run vs Execucao Real

- `DRY_RUN=true`: calcula a decisao e registra logs, sem alterar recurso real.
- `DRY_RUN=false`: chama os handlers e executa start/stop de fato.

No modo real, para VM, o scheduler agora consulta estado antes da acao:
- se decisao for `START` e a VM ja estiver ligada, faz `SKIP`
- se decisao for `STOP` e a VM ja estiver parada, faz `SKIP`
- se `RETAIN_RUNNING=true`:
  - VM ligada manualmente fora da janela -> `SKIP`
  - VM ligada pelo scheduler fora da janela -> `STOP`
- se `RETAIN_STOPPED=true`:
  - VM parada manualmente dentro da janela -> `SKIP`
  - VM parada pelo scheduler dentro da janela -> `START`

## Deploy com Bicep (Azure)

O projeto agora possui infraestrutura como codigo em Bicep:

- `infra/bicep/main.bicep`: orquestra o deploy em escopo de subscription
- `infra/bicep/modules/functionApp.bicep`: cria os recursos da Function
- `infra/bicep/main.parameters.example.json`: exemplo de parametros

Recursos criados:

- Resource Group
- Storage Account + Table de estado
- Log Analytics + Application Insights
- App Service Plan (Dedicated Linux - B1)
- Function App com Managed Identity (SystemAssigned)
- RBAC da identidade nas subscriptions monitoradas:
  - `Reader`
  - `Virtual Machine Contributor`

### 1) Preparar parametros

Copie e ajuste o arquivo:

```bash
cp infra/bicep/main.parameters.example.json infra/bicep/main.parameters.json
```

Edite os valores no `infra/bicep/main.parameters.json` (nomes unicos e subscription IDs reais).

### 2) Executar deploy da infraestrutura

```bash
az deployment sub create \
  --name offhours-scheduler-deploy \
  --location eastus \
  --template-file infra/bicep/main.bicep \
  --parameters @infra/bicep/main.parameters.json
```

### 3) Publicar o codigo da Function

Depois da infra criada, gere o bundle de publish e publique o app:

```bash
./scripts/prepare_function_app_publish.sh
cd cmd/function_app
func azure functionapp publish <NOME_DA_FUNCTION_APP>
```

Observacao: em Azure, o `DefaultAzureCredential` vai usar Managed Identity automaticamente (quando habilitada e com RBAC correto).

Execucao:
- o scheduler processa recursos em paralelo usando worker pool (`ThreadPoolExecutor`)
- a concorrencia e controlada por `MAX_WORKERS`

## Roadmap

- v1: VM scheduler por tags (atual)
- v2: App Service / Azure SQL / VMSS
- v3: regras avancadas (feriados, datas especificas, janelas complexas)
- v4: features FinOps (detecao de ociosidade, relatorios de custo)

## Alteracoes Futuras (Planejado)

Itens alinhados para implementacao futura:

- Migrar configuracao operacional para Azure Table Storage (table-driven), removendo dependencia de arquivo YAML para schedules.
- Manter no app apenas configuracoes tecnicas/minimas de runtime (ex.: conexoes e nomes de tabelas).
- Permitir administracao de schedules diretamente por tabela, incluindo criacao e alteracao de janelas sem redeploy.
- Centralizar configuracoes globais na tabela (ex.: `DRY_RUN`, `DEFAULT_TIMEZONE`, `SCHEDULE_TAG_KEY`, `RETAIN_RUNNING`, `RETAIN_STOPPED`).
- Incluir controle de escopo dinamico por include/exclude:
  - `include_management_groups`
  - `include_subscriptions`
  - `exclude_management_groups`
  - `exclude_subscriptions`
- Definir regra explicita de precedencia para escopo (excludes vencem includes).
- Incluir validacao/auditoria das configuracoes (ex.: `Version`, `UpdatedAtUtc`, `UpdatedBy`) para seguranca operacional.

## Licenca

MIT
