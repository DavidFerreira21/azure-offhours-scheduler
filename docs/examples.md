# Exemplos

Este documento traz exemplos prontos para uso operacional com a CLI `./offhours`.
Para operacao do dia a dia, o formato recomendado e YAML. Exemplos de entidades JSON brutas ficam em `architecture.md` quando voce precisar consultar o schema de tabela.

Observacoes importantes:

- use boolean real (`true` e `false`) para `DRY_RUN`, `RETAIN_RUNNING`, `RETAIN_STOPPED` e `Enabled`
- para schedules, `Periods` e o formato preferido
- `Start` e `Stop` continuam suportados como atalho para janelas simples
- deixe `UpdatedAtUtc` e `UpdatedBy` para a CLI preencher no `apply`
- `RETAIN_RUNNING` continua temporario no comportamento atual
- `RETAIN_STOPPED` continua persistente no comportamento atual
- se o deploy acabou de criar RBAC para tabelas, pode ser necessario rodar `az logout` e `az login` antes do primeiro `apply`

## 1. Config Global Minima

Arquivo `runtime.yaml`:

```yaml
DRY_RUN: true
DEFAULT_TIMEZONE: America/Sao_Paulo
SCHEDULE_TAG_KEY: schedule
RETAIN_RUNNING: false
RETAIN_STOPPED: false
Version: "1"
```

Aplicar com preview:

```bash
./offhours config apply --file runtime.yaml
```

Aplicar de verdade:

```bash
./offhours config apply --file runtime.yaml --execute
```

Consultar depois:

```bash
./offhours config get
```

## 2. Schedule Simples

Arquivo `business-hours.yaml`:

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

Aplicar com preview:

```bash
./offhours schedule apply --file business-hours.yaml
```

Aplicar de verdade:

```bash
./offhours schedule apply --file business-hours.yaml --execute
```

Tag no recurso:

```text
schedule=business-hours
```

## 3. Schedule com Multiplas Janelas

Arquivo `office-hours.yaml`:

```yaml
RowKey: office-hours
Periods:
  - start: "08:00"
    stop: "12:00"
  - start: "13:00"
    stop: "18:00"
SkipDays:
  - saturday
  - sunday
Enabled: true
Version: "2"
```

Esse e o formato preferido para schedules novos.

## 4. Schedule com Escopo por Subscription

Arquivo `prod-office-hours.yaml`:

```yaml
RowKey: prod-office-hours
Start: "07:00"
Stop: "19:00"
IncludeSubscriptions:
  - sub-a
  - sub-b
ExcludeSubscriptions:
  - sub-b
Enabled: true
Version: "3"
```

Leitura pratica:

- `sub-a` entra
- `sub-b` fica fora porque `exclude` vence

## 5. Schedule com Escopo por Management Group

Arquivo `shared-services.yaml`:

```yaml
RowKey: shared-services
Start: "08:00"
Stop: "20:00"
IncludeManagementGroups:
  - mg-shared
  - mg-platform
ExcludeManagementGroups:
  - mg-blocked
Enabled: true
Version: "1"
```

## 6. Tags no Recurso

Tag minima:

```text
schedule=office-hours
```

Com timezone por recurso:

```text
schedule=office-hours
timezone=America/Mexico_City
```

Nesse caso:

- o schedule continua vindo da tabela
- o timezone da avaliacao vem da tag do recurso
- se a tag faltar, o fallback e `DEFAULT_TIMEZONE`

## 7. Validacao Segura Inicial

Sequencia recomendada:

1. suba a infra
2. deixe `DRY_RUN=true` em `runtime.yaml` se quiser validar sem acao real
3. aplique `runtime.yaml`
4. aplique `business-hours.yaml`
5. marque uma VM de teste com `schedule=business-hours`
6. rode `./offhours state list`
7. rode `./offhours function trigger`
8. rode `./offhours state list` novamente
9. so depois troque `DRY_RUN` para `false`

Comandos uteis:

```bash
./offhours state list
./offhours function trigger
./offhours schedule get business-hours
./offhours config get
```

## 8. Seed Inicial Pela CLI

Depois do deploy, o caminho recomendado e aplicar a configuracao e os schedules explicitamente pela CLI.

Se o deploy acabou de criar `Storage Table Data Contributor` para o grupo operador, faca antes:

```bash
az logout
az login
```

Conferir e aplicar:

```bash
./offhours config get
./offhours config apply --file runtime.yaml --execute
./offhours schedule list
./offhours schedule apply --file business-hours.yaml --execute
```

## 9. Escopo Tecnico por Subscriptions

Trecho de `infra/bicep/main.parameters.json`:

```json
{
  "parameters": {
    "subscriptionIds": {
      "value": [
        "00000000-0000-0000-0000-000000000000",
        "11111111-1111-1111-1111-111111111111"
      ]
    },
    "managementGroupIds": {
      "value": []
    },
    "excludeSubscriptionIds": {
      "value": []
    }
  }
}
```

## 10. Escopo Tecnico por Management Groups

Trecho de `infra/bicep/main.parameters.json`:

```json
{
  "parameters": {
    "subscriptionIds": {
      "value": []
    },
    "managementGroupIds": {
      "value": [
        "mg-platform-prod",
        "mg-shared-services"
      ]
    },
    "excludeSubscriptionIds": {
      "value": [
        "22222222-2222-2222-2222-222222222222"
      ]
    }
  }
}
```

## 11. Filtro Regional

Trecho de `infra/bicep/main.parameters.json`:

```json
{
  "parameters": {
    "targetResourceLocations": {
      "value": [
        "brazilsouth",
        "eastus2"
      ]
    }
  }
}
```

Com isso:

- a Function continua enxergando apenas o escopo tecnico efetivo
- dentro desse escopo, o discovery considera apenas recursos nessas regioes

Se quiser todas as regioes:

```json
{
  "parameters": {
    "targetResourceLocations": {
      "value": []
    }
  }
}
```
