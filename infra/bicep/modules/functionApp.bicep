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

@description('Path to schedules YAML inside the app package.')
param schedulesFile string = 'schedules/schedules.yaml'

@description('Enable DRY_RUN mode.')
param dryRun bool = false

@description('Default timezone used when the resource tag timezone is missing.')
param defaultTimezone string = 'America/Sao_Paulo'

@description('Tag key that contains the schedule name.')
param scheduleTagKey string = 'schedule'

@description('If true, do not stop manually started VMs outside the stop window.')
param retainRunning bool = false

@description('If true, do not start manually stopped VMs inside the start window.')
param retainStopped bool = false

@description('Maximum scheduler workers for controlled parallelism.')
param maxWorkers int = 5

@description('Azure Table Storage table name used for scheduler state.')
param stateTableName string = 'OffHoursSchedulerState'

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

resource stateTable 'Microsoft.Storage/storageAccounts/tableServices/tables@2023-05-01' = {
  name: '${storage.name}/default/${stateTableName}'
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
          name: 'SCHEDULES_FILE'
          value: schedulesFile
        }
        {
          name: 'DRY_RUN'
          value: toLower(string(dryRun))
        }
        {
          name: 'DEFAULT_TIMEZONE'
          value: defaultTimezone
        }
        {
          name: 'SCHEDULE_TAG_KEY'
          value: scheduleTagKey
        }
        {
          name: 'RETAIN_RUNNING'
          value: toLower(string(retainRunning))
        }
        {
          name: 'RETAIN_STOPPED'
          value: toLower(string(retainStopped))
        }
        {
          name: 'MAX_WORKERS'
          value: string(maxWorkers)
        }
        {
          name: 'STATE_STORAGE_CONNECTION_STRING'
          value: storageConnectionString
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
output stateTableName string = stateTableName
