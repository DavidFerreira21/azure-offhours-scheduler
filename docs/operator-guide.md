# Guia Operacional

Este documento e voltado para quem vai operar o scheduler depois do deploy.

O caminho recomendado de operacao e a CLI repo-local `./offhours`.
O foco aqui nao e explicar a implementacao interna, e sim o que editar, como aplicar com seguranca e como validar o resultado.

## 1. O Que Normalmente Muda Depois do Deploy

No dia a dia, a operacao costuma mexer em 3 coisas:

- configuracao global do scheduler
- schedules na tabela operacional
- tags nos recursos Azure
- disparo manual da Function quando voce quiser antecipar um ciclo

Na maioria dos casos, nao e necessario redeploy para isso.

## 2. Onde Operar

No dia a dia, a forma recomendada de operar e:

```bash
./offhours ...
```

Recursos principais no Azure continuam sendo:

- Function App
  Executa o timer do scheduler.
- Storage Account
  Hospeda as tabelas operacionais.
- Azure Table Storage
  Guarda config global, schedules e state.

O Azure Portal continua util para:

- aplicar tags nos recursos
- inspecionar logs da Function
- conferir rapidamente entidades nas tabelas quando necessario

Mas a edicao operacional recomendada de config e schedules passa a ser a CLI, porque ela valida payloads antes de gravar e oferece preview por padrao.

Configuracao tecnica importante na Function App:

- `ENABLE_VERBOSE_AZURE_SDK_LOGS`
  Deve permanecer `false` no uso normal. Ative apenas para troubleshooting temporario.
- `RESOURCE_RESULT_LOG_MODE`
  O valor recomendado e `executed-and-errors`. Use `all` apenas quando precisar investigar recurso por recurso.

Tabelas principais:

- `OffHoursSchedulerConfig`
- `OffHoursSchedulerSchedules`
- `OffHoursSchedulerState`

Uso recomendado:

```bash
az login
./offhours state list
```

Depois de um deploy que acabou de criar RBAC para tabelas, pode ser necessario renovar as credenciais locais antes do primeiro `apply`:

```bash
az logout
az login
```

Ponto importante para operacao humana:

- a CLI usa Microsoft Entra ID por padrao
- para gravar `config`, `schedule` e `state`, o operador precisa de `Storage Table Data Contributor` na storage do scheduler
- no fluxo recomendado, esse acesso vem de `tableOperatorsGroupObjectId` no deploy

Modelos recomendados para `tableOperatorsGroupObjectId`:

- usar um grupo Microsoft Entra ja existente com os operadores da solucao
- criar um grupo novo, por exemplo `azure-offhours-operators`, adicionar os usuarios e informar o `objectId` no deploy

No fluxo recomendado, `./scripts/deploy_scheduler.sh` grava automaticamente `.offhours.env` na raiz do repositorio.
O wrapper `./offhours` le esse arquivo sozinho, entao voce nao precisa exportar `OFFHOURS_TABLE_SERVICE_URI` manualmente depois do deploy.

Como a CLI resolve o contexto:

1. se `OFFHOURS_TABLE_SERVICE_URI` estiver definida no shell atual, ela vence
2. se nao estiver, o wrapper tenta carregar `.offhours.env`
3. esse arquivo e criado automaticamente pelo deploy recomendado

Na pratica:

- repositorio recem-deployado: `az login` e `./offhours ...`
- repositorio sem `.offhours.env`: defina `OFFHOURS_TABLE_SERVICE_URI` manualmente
- se o deploy acabou de criar RBAC na storage: faca `az logout` e `az login` antes do primeiro `config apply` ou `schedule apply`

Para comandos que gravam `config` e `schedule`, a CLI tambem precisa resolver `UpdatedBy`.
Ela tenta usar o usuario atual do Azure CLI automaticamente.
Se voce quiser um valor fixo, pode sobrescrever uma vez:

```bash
export OFFHOURS_UPDATED_BY=seu-email@exemplo.com
```

## 3. Config Global

Entidade principal:

- `PartitionKey=GLOBAL`
- `RowKey=runtime`

Campos mais importantes:

- `DRY_RUN`
  Quando `true`, o scheduler avalia e registra, mas nao executa `start` ou `stop`.
- `DEFAULT_TIMEZONE`
  Timezone padrao usada quando o recurso nao informa override proprio.
- `SCHEDULE_TAG_KEY`
  Nome da tag que aponta para o schedule. O padrao e `schedule`.
- `RETAIN_RUNNING`
  Respeita uma ligacao manual fora da janela. No comportamento atual, esse retain e temporario.
- `RETAIN_STOPPED`
  Respeita um desligamento manual dentro da janela. No comportamento atual, esse retain e persistente.

Recomendacao pratica:

- prefira boolean real (`true` e `false`) para campos booleanos
- mantenha `Version` preenchido no arquivo
- deixe `UpdatedAtUtc` e `UpdatedBy` para a CLI preencher no `apply`
- use `OFFHOURS_UPDATED_BY` apenas quando voce quiser sobrescrever o usuario detectado automaticamente

Comandos uteis:

```bash
./offhours config get
./offhours config apply --file runtime.yaml
./offhours config apply --file runtime.yaml --execute
```

Arquivos de referencia no repositorio:

- `runtime.yaml`
- `business-hours.yaml`

Exemplo de `runtime.yaml`:

```yaml
DRY_RUN: true
DEFAULT_TIMEZONE: America/Sao_Paulo
SCHEDULE_TAG_KEY: schedule
RETAIN_RUNNING: false
RETAIN_STOPPED: false
Version: "2"
```

## 4. Criar ou Editar um Schedule

Cada schedule fica em uma entidade da tabela `OffHoursSchedulerSchedules`.

Campos minimos no arquivo:

- `RowKey=<nome-do-schedule>`
- `Enabled=true`
- `Version`
- `UpdatedAtUtc` e `UpdatedBy` ficam a cargo da CLI no `apply`

Para janela simples, voce pode usar:

- `Start`
- `Stop`

Para janelas mais ricas, o formato preferido e:

- `Periods`

Exemplo simples:

```yaml
RowKey: business-hours
Start: "08:00"
Stop: "18:00"
SkipDays:
  - saturday
  - sunday
Enabled: true
Version: "1"
```

Exemplo com multiplas janelas:

```yaml
RowKey: office-hours-split
Periods:
  - start: "08:00"
    stop: "12:00"
  - start: "13:00"
    stop: "18:00"
Enabled: true
Version: "1"
```

Comandos uteis:

```bash
./offhours schedule list
./offhours schedule get business-hours
./offhours schedule apply --file business-hours.yaml
./offhours schedule apply --file business-hours.yaml --execute
./offhours schedule delete business-hours
./offhours schedule delete business-hours --execute
```

Exemplo de `business-hours.yaml`:

```yaml
RowKey: business-hours
Periods:
  - start: "08:00"
    stop: "18:00"
SkipDays:
  - saturday
  - sunday
Enabled: true
Version: "3"
```

## 5. Aplicar o Schedule em um Recurso

O recurso entra no ciclo por tag.

Exemplo:

```text
schedule=business-hours
```

Tambem e possivel usar timezone por recurso, por exemplo:

```text
timezone=America/Sao_Paulo
```

## 6. Como Funciona o Retain na Pratica

Sem retain:

- fora da janela, o scheduler tende a desligar
- dentro da janela, o scheduler tende a ligar

Com `RETAIN_RUNNING=true`:

- se alguem ligar manualmente um recurso fora da janela, o scheduler respeita isso temporariamente
- depois que o recurso atravessa uma janela valida, ele volta ao ciclo normal

Com `RETAIN_STOPPED=true`:

- se alguem desligar manualmente um recurso dentro da janela, o scheduler respeita isso
- no comportamento atual, esse override permanece ate outro evento operacional mudar o estado

## 7. Como Validar se Esta Funcionando

Sinais mais uteis:

- logs da Function
- relatorio estruturado do ciclo
- tabela `OffHoursSchedulerState`

Observacao pratica:

- `./offhours state list` pode mostrar `(empty)` antes do primeiro ciclo ou antes do primeiro retain relevante
- depois que a Function processa recursos, a tabela passa a refletir `LastObservedState`, `LastAction` e as flags de retain

Comandos uteis:

```bash
./offhours state list
./offhours state get \
  --resource-id /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Compute/virtualMachines/<vm>
./offhours state delete \
  --resource-id /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Compute/virtualMachines/<vm>
./offhours state delete --execute \
  --resource-id /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Compute/virtualMachines/<vm>
```

O relatorio final de cada execucao traz:

- `run_id`
- `summary`
- `duration_sec`
- `resources`

Cada recurso processado pode informar:

- `resource_id`
- `name`
- `type`
- `action`
- `result`
- `reason`
- `duration_sec`

No modo recomendado de producao:

- o relatorio final do ciclo continua sempre
- o resumo textual do ciclo continua sempre
- logs por recurso aparecem apenas para `EXECUTED` e `FAILED`
- para troubleshooting detalhado, troque `RESOURCE_RESULT_LOG_MODE` para `all`

Sinal util para a CLI:

- se `./offhours state list` falhar logo no inicio por falta de contexto, confira se `.offhours.env` existe na raiz do repositorio

## 8. Validacao Segura Recomendada

Para primeira validacao:

1. deixe `DRY_RUN=true`
2. crie ou ajuste um schedule por arquivo YAML
3. aplique a tag em um recurso de teste
4. rode `schedule apply` sem `--execute`
5. confirme o preview final
6. repita com `--execute`
7. aguarde o ciclo do timer ou dispare a Function manualmente
8. confirme o resultado pelos logs, relatorio estruturado e state
9. so depois troque `DRY_RUN` para `false`

Comando util para disparo manual:

```bash
./offhours function trigger
```

Sequencia curta recomendada para validar:

1. `./offhours state list`
2. `./offhours function trigger`
3. `./offhours state list`

## 9. Quando Voce Precisa de Ajuda Mais Tecnica

Use estes documentos:

- `architecture.md`
  Para entender o fluxo completo.
- `examples.md`
  Para copiar exemplos validos de entidades e escopo.
- `troubleshooting.md`
  Para erros comuns de deploy, runtime e edicao manual.
- `developer-guide.md`
  Para manutencao e alteracoes de codigo.
