# Troubleshooting

Este documento reúne problemas comuns de desenvolvimento local, publish e operacao inicial.

## 1. `source : The term 'source' is not recognized`

Voce esta no PowerShell.

Use:

```powershell
.\.venv\Scripts\Activate.ps1
```

## 2. `func: command not found`

Azure Functions Core Tools nao esta instalado no ambiente atual.

Valide:

```bash
func --version
```

Se necessario, instale o pacote correspondente ao seu sistema operacional.

## 3. `Connection refused (127.0.0.1:10000)`

`AzureWebJobsStorage` esta apontando para `UseDevelopmentStorage=true`, mas o Azurite nao esta rodando.

Opcoes:

- iniciar Azurite localmente
- usar uma connection string real de Storage Account para testes

## 4. `No module named 'config'`

No contexto atual da estrutura do projeto, esse erro normalmente indica que o bundle da Function nao foi preparado antes do publish.

Execute:

```bash
./scripts/prepare_function_app_publish.sh
```

Depois publique novamente.

## 5. O deploy funciona, mas o Portal nao deixa ler as tabelas

Normalmente isso significa falta de RBAC de data plane para o usuario humano.

Verifique se existe um grupo configurado em:

- `tableOperatorsGroupObjectId`

E se esse grupo recebeu:

- `Storage Table Data Contributor`

## 6. A Function sobe, mas nao acha recursos

Checklist:

- `AZURE_SUBSCRIPTION_IDS` esta correto
- `targetResourceLocations` nao esta filtrando demais
- a VM tem a tag de schedule esperada
- o nome da tag corresponde a `SCHEDULE_TAG_KEY`
- a identidade da Function recebeu RBAC nas subscriptions efetivas

## 7. O deploy com management groups nao trouxe as subscriptions esperadas

Use o wrapper:

```bash
./scripts/deploy_scheduler.sh \
  --parameters-file infra/bicep/main.parameters.json
```

Nao confie em `az deployment sub create` direto quando o escopo usa:

- `managementGroupIds`
- `excludeSubscriptionIds`

O wrapper resolve o escopo tecnico efetivo antes do deploy.

## 8. O scheduler nao executa nada

Verifique:

- existe entidade `GLOBAL/runtime` na tabela de config
- existe ao menos um schedule habilitado na tabela de schedules
- `DRY_RUN` pode estar ligado
- a hora atual pode estar fora da janela
- o dia atual pode estar em `SkipDays`
- o recurso pode estar fora do escopo include/exclude

## 9. Mudanca no codigo nao apareceu no ambiente publicado

Checklist:

- a mudanca foi feita em `src/`, nao em copia local temporaria
- `./scripts/prepare_function_app_publish.sh` foi executado
- a Function foi publicada novamente

## 10. Como depurar o bootstrap do runtime

Comece por:

- `function/OffHoursTimer/__init__.py`

E valide em ordem:

1. `Settings.from_env()`
2. leitura da tabela global
3. leitura da tabela de schedules
4. discovery
5. service
