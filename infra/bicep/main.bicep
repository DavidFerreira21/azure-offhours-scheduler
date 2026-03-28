targetScope = 'subscription'

@description('Resource group where the scheduler resources will be deployed.')
param resourceGroupName string

@description('Azure region for the deployment.')
param location string = deployment().location

@description('Prefix used to generate resource names.')
param namePrefix string

@description('Optional override for the Function App name.')
param functionAppName string = ''

@description('Optional override for the Storage Account name (3-24 lowercase letters/numbers).')
param storageAccountName string = ''

@description('Optional override for the Log Analytics workspace name.')
param logAnalyticsName string = ''

@description('Optional override for the Application Insights name.')
param appInsightsName string = ''

@description('Optional override for the App Service plan name.')
param planName string = ''

@description('When true, reuse an existing App Service plan with planName.')
param useExistingPlan bool = false

@description('List of explicit subscription IDs scanned by the scheduler.')
param subscriptionIds array = []

@description('Optional management group IDs used to discover additional subscriptions for the scheduler scope.')
param managementGroupIds array = []

@description('Optional subscription IDs removed from the final scheduler scope after combining subscriptionIds and managementGroupIds.')
param excludeSubscriptionIds array = []

@description('Optional Azure regions scanned by the scheduler. Leave empty to scan all regions in the configured subscriptions.')
param targetResourceLocations array = []

@description('Maximum scheduler workers for controlled parallelism.')
param maxWorkers int = 5

@description('When true, enables verbose Azure SDK request/response logs. Keep false in normal production use.')
param enableVerboseAzureSdkLogs bool = false

@description('Controls structured resource-result logs. Use executed-and-errors for normal production use and all for troubleshooting.')
@allowed([
  'executed-and-errors'
  'all'
])
param resourceResultLogMode string = 'executed-and-errors'

@description('Cron expression used by the OffHours timer trigger. Default runs every 15 minutes.')
param timerSchedule string = '0 */15 * * * *'

@description('Azure Table Storage table name used for global scheduler configuration.')
param configTableName string = 'OffHoursSchedulerConfig'

@description('Azure Table Storage table name used for schedules.')
param scheduleTableName string = 'OffHoursSchedulerSchedules'

@description('Azure Table Storage table name used for scheduler state.')
param stateTableName string = 'OffHoursSchedulerState'

@description('Optional Microsoft Entra group object ID that will receive Storage Table Data Contributor on the scheduler storage account.')
param tableOperatorsGroupObjectId string = ''

var generatedSuffix = take(uniqueString(subscription().subscriptionId, resourceGroupName, namePrefix), 6)
var normalizedPrefix = toLower(replace(replace(namePrefix, '-', ''), '_', ''))
var storagePrefix = empty(normalizedPrefix) ? 'offhours' : normalizedPrefix
var effectiveFunctionAppName = !empty(functionAppName) ? functionAppName : 'func-${namePrefix}-${generatedSuffix}'
var effectiveStorageAccountName = !empty(storageAccountName) ? storageAccountName : 'st${take(storagePrefix, 16)}${generatedSuffix}'
var effectiveLogAnalyticsName = !empty(logAnalyticsName) ? logAnalyticsName : 'log-${namePrefix}-${generatedSuffix}'
var effectiveAppInsightsName = !empty(appInsightsName) ? appInsightsName : 'appi-${namePrefix}-${generatedSuffix}'
var effectivePlanName = !empty(planName) ? planName : 'asp-${namePrefix}-${generatedSuffix}'

resource resourceGroup 'Microsoft.Resources/resourceGroups@2022-09-01' = {
  name: resourceGroupName
  location: location
}

module functionStack './modules/functionApp.bicep' = {
  name: 'schedulerFunctionStack'
  scope: resourceGroup
  params: {
    location: location
    functionAppName: effectiveFunctionAppName
    storageAccountName: effectiveStorageAccountName
    logAnalyticsName: effectiveLogAnalyticsName
    appInsightsName: effectiveAppInsightsName
    planName: effectivePlanName
    useExistingPlan: useExistingPlan
    subscriptionIds: subscriptionIds
    managementGroupIds: managementGroupIds
    excludeSubscriptionIds: excludeSubscriptionIds
    targetResourceLocations: targetResourceLocations
    maxWorkers: maxWorkers
    enableVerboseAzureSdkLogs: enableVerboseAzureSdkLogs
    resourceResultLogMode: resourceResultLogMode
    timerSchedule: timerSchedule
    configTableName: configTableName
    scheduleTableName: scheduleTableName
    stateTableName: stateTableName
    tableOperatorsGroupObjectId: tableOperatorsGroupObjectId
  }
}

module subscriptionRoles './modules/subscriptionRoles.bicep' = [for subId in subscriptionIds: {
  name: 'schedulerRoles-${subId}'
  scope: subscription(subId)
  params: {
    principalId: functionStack.outputs.principalId
    assignmentSeed: effectiveFunctionAppName
  }
}]

output functionAppName string = functionStack.outputs.functionAppName
output functionAppId string = functionStack.outputs.functionAppId
output principalId string = functionStack.outputs.principalId
output storageAccountName string = functionStack.outputs.storageAccountName
