targetScope = 'resourceGroup'

@description('Azure region for all resources in this module.')
param location string

@description('Function App name (must be globally unique).')
param functionAppName string

@description('Storage account name (3-24 lowercase letters/numbers).')
param storageAccountName string

@description('Log Analytics workspace name.')
param logAnalyticsName string

@description('Application Insights name.')
param appInsightsName string

@description('App Service plan name (Dedicated).')
param planName string

@description('When true, reuse an existing App Service plan with planName.')
param useExistingPlan bool = false

@description('List of subscription IDs scanned by the scheduler.')
param subscriptionIds array

@description('Optional management group IDs declared for scheduler scope resolution.')
param managementGroupIds array = []

@description('Optional subscription IDs excluded from the resolved scheduler scope.')
param excludeSubscriptionIds array = []

@description('Optional Azure regions scanned by the scheduler. Leave empty to scan all regions in the configured subscriptions.')
param targetResourceLocations array = []

@description('Maximum scheduler workers for controlled parallelism.')
param maxWorkers int = 5

@description('Azure Table Storage table name used for global scheduler configuration.')
param configTableName string = 'OffHoursSchedulerConfig'

@description('Azure Table Storage table name used for schedules.')
param scheduleTableName string = 'OffHoursSchedulerSchedules'

@description('Azure Table Storage table name used for scheduler state.')
param stateTableName string = 'OffHoursSchedulerState'

@description('When true, seed the configuration tables with a safe default bootstrap.')
param bootstrapDefaults bool = true

@description('Optional Microsoft Entra group object ID that will receive Storage Table Data Contributor on the scheduler storage account.')
param tableOperatorsGroupObjectId string = ''

var storageTableDataContributorRoleDefinitionId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'
)

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
  }
}

resource configTable 'Microsoft.Storage/storageAccounts/tableServices/tables@2023-05-01' = {
  name: '${storage.name}/default/${configTableName}'
}

resource scheduleTable 'Microsoft.Storage/storageAccounts/tableServices/tables@2023-05-01' = {
  name: '${storage.name}/default/${scheduleTableName}'
}

resource stateTable 'Microsoft.Storage/storageAccounts/tableServices/tables@2023-05-01' = {
  name: '${storage.name}/default/${stateTableName}'
}

resource tableOperatorsAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(tableOperatorsGroupObjectId)) {
  name: guid(storage.id, tableOperatorsGroupObjectId, 'storage-table-data-contributor')
  scope: storage
  properties: {
    roleDefinitionId: storageTableDataContributorRoleDefinitionId
    principalId: tableOperatorsGroupObjectId
    principalType: 'Group'
  }
}

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: logAnalyticsName
  location: location
  properties: {
    retentionInDays: 30
    features: {
      searchVersion: 1
    }
    sku: {
      name: 'PerGB2018'
    }
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
  }
}

resource plan 'Microsoft.Web/serverfarms@2022-09-01' = if (!useExistingPlan) {
  name: planName
  location: location
  kind: 'functionapp'
  sku: {
    name: 'B1'
    tier: 'Basic'
  }
  properties: {
    reserved: true
  }
}

resource existingPlan 'Microsoft.Web/serverfarms@2022-09-01' existing = if (useExistingPlan) {
  name: planName
}

var storageConnectionString = 'DefaultEndpointsProtocol=https;AccountName=${storage.name};AccountKey=${storage.listKeys().keys[0].value};EndpointSuffix=${environment().suffixes.storage}'
var serverFarmId = useExistingPlan ? existingPlan.id : plan.id

resource bootstrapScriptIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = if (bootstrapDefaults) {
  name: '${functionAppName}-bootstrap-id'
  location: location
}

resource bootstrapDefaultsScript 'Microsoft.Resources/deploymentScripts@2023-08-01' = if (bootstrapDefaults) {
  name: 'bootstrap-scheduler-defaults'
  location: location
  kind: 'AzureCLI'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${bootstrapScriptIdentity.id}': {}
    }
  }
  properties: {
    azCliVersion: '2.61.0'
    cleanupPreference: 'OnSuccess'
    retentionInterval: 'P1D'
    timeout: 'PT15M'
    forceUpdateTag: deployment().name
    environmentVariables: [
      {
        name: 'BOOTSTRAP_CONNECTION_STRING'
        secureValue: storageConnectionString
      }
      {
        name: 'BOOTSTRAP_CONFIG_TABLE'
        value: configTableName
      }
      {
        name: 'BOOTSTRAP_SCHEDULE_TABLE'
        value: scheduleTableName
      }
      {
        name: 'BOOTSTRAP_UPDATED_BY'
        value: 'bicep-bootstrap'
      }
    ]
    scriptContent: '''
      set -euo pipefail

      updated_at_utc="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

      entity_exists() {
        local table_name="$1"
        local partition_key="$2"
        local row_key="$3"

        az storage entity show \
          --connection-string "$BOOTSTRAP_CONNECTION_STRING" \
          --table-name "$table_name" \
          --partition-key "$partition_key" \
          --row-key "$row_key" \
          --only-show-errors \
          -o none >/dev/null 2>&1
      }

      if ! entity_exists "$BOOTSTRAP_CONFIG_TABLE" "GLOBAL" "runtime"; then
        az storage entity insert \
          --connection-string "$BOOTSTRAP_CONNECTION_STRING" \
          --table-name "$BOOTSTRAP_CONFIG_TABLE" \
          --if-exists fail \
          --entity \
            PartitionKey=GLOBAL \
            RowKey=runtime \
            DRY_RUN=true \
            DEFAULT_TIMEZONE=America/Sao_Paulo \
            SCHEDULE_TAG_KEY=schedule \
            RETAIN_RUNNING=false \
            RETAIN_STOPPED=false \
            Version=1 \
            UpdatedAtUtc="$updated_at_utc" \
            UpdatedBy="$BOOTSTRAP_UPDATED_BY" \
          --only-show-errors \
          -o none
      fi

      if ! entity_exists "$BOOTSTRAP_SCHEDULE_TABLE" "SCHEDULE" "business-hours"; then
        az storage entity insert \
          --connection-string "$BOOTSTRAP_CONNECTION_STRING" \
          --table-name "$BOOTSTRAP_SCHEDULE_TABLE" \
          --if-exists fail \
          --entity \
            PartitionKey=SCHEDULE \
            RowKey=business-hours \
            Start=08:00 \
            Stop=18:00 \
            SkipDays=saturday,sunday \
            Enabled=true \
            Version=1 \
            UpdatedAtUtc="$updated_at_utc" \
            UpdatedBy="$BOOTSTRAP_UPDATED_BY" \
          --only-show-errors \
          -o none
      fi
    '''
  }
  dependsOn: [
    configTable
    scheduleTable
  ]
}

resource functionApp 'Microsoft.Web/sites@2022-09-01' = {
  name: functionAppName
  location: location
  kind: 'functionapp,linux'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: serverFarmId
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'Python|3.12'
      appSettings: [
        {
          name: 'AzureWebJobsStorage'
          value: storageConnectionString
        }
        {
          name: 'FUNCTIONS_EXTENSION_VERSION'
          value: '~4'
        }
        {
          name: 'FUNCTIONS_WORKER_RUNTIME'
          value: 'python'
        }
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: appInsights.properties.ConnectionString
        }
        {
          name: 'AZURE_SUBSCRIPTION_IDS'
          value: join(subscriptionIds, ',')
        }
        {
          name: 'DECLARED_MANAGEMENT_GROUP_IDS'
          value: join(managementGroupIds, ',')
        }
        {
          name: 'DECLARED_EXCLUDE_SUBSCRIPTION_IDS'
          value: join(excludeSubscriptionIds, ',')
        }
        {
          name: 'TARGET_RESOURCE_LOCATIONS'
          value: join(targetResourceLocations, ',')
        }
        {
          name: 'SCHEDULER_STORAGE_CONNECTION_STRING'
          value: storageConnectionString
        }
        {
          name: 'CONFIG_STORAGE_TABLE_NAME'
          value: configTableName
        }
        {
          name: 'SCHEDULE_STORAGE_TABLE_NAME'
          value: scheduleTableName
        }
        {
          name: 'MAX_WORKERS'
          value: string(maxWorkers)
        }
        {
          name: 'STATE_STORAGE_TABLE_NAME'
          value: stateTableName
        }
      ]
    }
  }
}

output functionAppName string = functionApp.name
output functionAppId string = functionApp.id
output principalId string = functionApp.identity.principalId
output storageAccountName string = storage.name
output configTableName string = configTableName
output scheduleTableName string = scheduleTableName
output stateTableName string = stateTableName
