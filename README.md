# Azure OffHours Scheduler

![CI](https://github.com/<OWNER>/<REPO>/actions/workflows/ci.yml/badge.svg)
![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.12-blue.svg)

Azure OffHours Scheduler e uma ferramenta open source focada em economia de custo no Azure.

A proposta e simples: manter ambientes nao produtivos, como dev, hml, sandbox e labs, desligados fora do horario comercial e liga-los apenas quando necessario.

O projeto faz isso combinando:

- tags nos recursos
- janelas operacionais em Azure Table Storage
- automacao via Azure Function
- escopo tecnico e operacional controlado

No estado atual, o projeto executa acoes reais para:

- `Microsoft.Compute/virtualMachines`

Licenca:

- Apache License 2.0

Versao atual:

- `1.0.0`

## O Que o Projeto Entrega

- Azure Function com timer
- discovery via Azure Resource Graph
- configuracao operacional table-driven
- escopo dinamico por subscription e management group
- retencao para respeitar override manual
- deploy com Bicep
- bootstrap default das tabelas

## Como Funciona

Fluxo de alto nivel:

```text
Timer Trigger
  -> le Config e Schedules no Azure Table Storage
  -> consulta Resource Graph
  -> avalia cada recurso no Schedule Engine
  -> executa o handler correto
  -> grava estado operacional quando necessario
```

Modelo de tabelas:

- `OffHoursSchedulerConfig`
- `OffHoursSchedulerSchedules`
- `OffHoursSchedulerState`

Observacao:

- para campos booleanos nas tabelas, prefira boolean real em vez de texto
- exemplos: `DRY_RUN`, `RETAIN_RUNNING`, `RETAIN_STOPPED`, `Enabled`
- use `true` / `false`, nao valores como `\"true\"`, `\"false\"` ou typos como `fase`
- para schedules, `Periods` e o formato preferido/oficial
- `Start` e `Stop` continuam suportados para janelas simples e edicao manual no Portal

Tag minima no recurso:

```text
schedule=business-hours
```

## Quick Start

1. Prepare o ambiente Python:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Copie o arquivo de parametros:

```bash
cp infra/bicep/main.parameters.example.json infra/bicep/main.parameters.json
```

3. Ajuste no `infra/bicep/main.parameters.json`:

- `resourceGroupName`
- `location`
- `namePrefix`
- `subscriptionIds` ou `managementGroupIds`
- `excludeSubscriptionIds` se necessario
- `targetResourceLocations` se quiser filtro regional
- `timerSchedule` se quiser sobrescrever o cron tecnico da Function
- `tableOperatorsGroupObjectId` se quiser operar tabelas via Entra ID

4. Faça login no Azure e selecione a subscription que deseja fazer deploy da solução:

```bash
az login
```

5. Execute o deploy completo:

```bash
./scripts/deploy_scheduler.sh \
  --parameters-file infra/bicep/main.parameters.json
```

6. Marque uma VM com:

```text
schedule=business-hours
```

7. Valide primeiro com `DRY_RUN=true`.

## Desenvolvimento Local

Rodar testes:

```bash
pytest -q
```

Preparar o host local:

```bash
cd function
cp local.settings.json.example local.settings.json
func start
```

Importante:

- em execucao local, o app usa `AZURE_SUBSCRIPTION_IDS` diretamente
- o bootstrap de `managementGroupIds` e `excludeSubscriptionIds` e resolvido pelo wrapper de deploy, nao pelo host local

## Deploy

Fluxo recomendado:

```bash
./scripts/deploy_scheduler.sh \
  --parameters-file infra/bicep/main.parameters.json
```

Esse wrapper:

- valida pre-requisitos locais
- resolve o escopo tecnico efetivo
- valida o Bicep
- executa o deploy
- faz bootstrap das tabelas
- prepara e publica a Function

Se voce usar `managementGroupIds` ou `excludeSubscriptionIds`, prefira sempre o wrapper em vez de rodar `az deployment sub create` diretamente.

Por padrao, o timer da Function executa a cada 15 minutos via `TIMER_SCHEDULE=0 */15 * * * *`.

## Documentacao

- Indice da documentacao: `docs/README.md`
- Arquitetura e fluxo completo: `docs/architecture.md`
- Guia de desenvolvimento: `docs/developer-guide.md`
- Estrutura do repositorio: `docs/repository-map.md`
- Componentes de codigo: `docs/code-components.md`
- Exemplos prontos: `docs/examples.md`
- Troubleshooting: `docs/troubleshooting.md`
- Politica de release e compatibilidade: `docs/release-policy.md`

## Comunidade

- Como contribuir: `CONTRIBUTING.md`
- Codigo de conduta: `CODE_OF_CONDUCT.md`
- Politica de seguranca: `SECURITY.md`
- Licenca: `LICENSE`

## Roadmap

- `1.0`: VM scheduler por tags com configuracao table-driven
- proximo: novos tipos de recurso
- proximo: regras mais avancadas de calendario
- proximo: melhorias voltadas para FinOps e observabilidade
