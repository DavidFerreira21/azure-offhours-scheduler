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

@description('When true, enables verbose Azure SDK request/response logs.')
param enableVerboseAzureSdkLogs bool = false

@description('Controls structured resource-result logs.')
@allowed([
  'executed-and-errors'
  'all'
])
param resourceResultLogMode string = 'executed-and-errors'

@description('Cron expression used by the OffHours timer trigger.')
param timerSchedule string = '0 */15 * * * *'

@description('Azure Table Storage table name used for global scheduler configuration.')
param configTableName string = 'OffHoursSchedulerConfig'

@description('Azure Table Storage table name used for schedules.')
param scheduleTableName string = 'OffHoursSchedulerSchedules'

@description('Azure Table Storage table name used for scheduler state.')
param stateTableName string = 'OffHoursSchedulerState'

@description('Optional Microsoft Entra group object ID that will receive Storage Table Data Contributor on the scheduler storage account.')
param tableOperatorsGroupObjectId string = ''

var storageTableDataContributorRoleDefinitionId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'
)
var storageBlobDataOwnerRoleDefinitionId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
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
    allowSharedKeyAccess: false
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

var serverFarmId = useExistingPlan ? existingPlan.id : plan.id
var tableServiceUri = 'https://${storage.name}.table.${environment().suffixes.storage}'

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
      alwaysOn: true
      linuxFxVersion: 'Python|3.12'
      appSettings: [
        {
          name: 'AzureWebJobsStorage__accountName'
          value: storage.name
        }
        {
          name: 'AzureWebJobsStorage__credential'
          value: 'managedidentity'
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
          name: 'ENABLE_VERBOSE_AZURE_SDK_LOGS'
          value: toLower(string(enableVerboseAzureSdkLogs))
        }
        {
          name: 'RESOURCE_RESULT_LOG_MODE'
          value: resourceResultLogMode
        }
        {
          name: 'TIMER_SCHEDULE'
          value: timerSchedule
        }
        {
          name: 'SCHEDULER_TABLE_SERVICE_URI'
          value: tableServiceUri
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

resource functionStorageBlobOwnerAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, functionApp.name, storageBlobDataOwnerRoleDefinitionId)
  scope: storage
  properties: {
    roleDefinitionId: storageBlobDataOwnerRoleDefinitionId
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource functionStorageTableContributorAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, functionApp.name, storageTableDataContributorRoleDefinitionId)
  scope: storage
  properties: {
    roleDefinitionId: storageTableDataContributorRoleDefinitionId
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

output functionAppName string = functionApp.name
output functionAppId string = functionApp.id
output principalId string = functionApp.identity.principalId
output storageAccountName string = storage.name
output configTableName string = configTableName
output scheduleTableName string = scheduleTableName
output stateTableName string = stateTableName
