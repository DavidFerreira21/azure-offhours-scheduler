targetScope = 'subscription'

@description('Resource group where the scheduler resources will be deployed.')
param resourceGroupName string

@description('Azure region for the deployment.')
param location string = deployment().location

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

@description('Default timezone used when resource tag timezone is missing.')
param defaultTimezone string = 'America/Sao_Paulo'

@description('Tag key that contains the schedule name.')
param scheduleTagKey string = 'schedule'

@description('If true, do not stop manually started VMs outside stop window.')
param retainRunning bool = false

@description('If true, do not start manually stopped VMs inside start window.')
param retainStopped bool = false

@description('Maximum scheduler workers for controlled parallelism.')
param maxWorkers int = 5

@description('Azure Table Storage table name used for scheduler state.')
param stateTableName string = 'OffHoursSchedulerState'

resource resourceGroup 'Microsoft.Resources/resourceGroups@2022-09-01' = {
  name: resourceGroupName
  location: location
}

module functionStack './modules/functionApp.bicep' = {
  name: 'schedulerFunctionStack'
  scope: resourceGroup
  params: {
    location: location
    functionAppName: functionAppName
    storageAccountName: storageAccountName
    logAnalyticsName: logAnalyticsName
    appInsightsName: appInsightsName
    planName: planName
    useExistingPlan: useExistingPlan
    subscriptionIds: subscriptionIds
    schedulesFile: schedulesFile
    dryRun: dryRun
    defaultTimezone: defaultTimezone
    scheduleTagKey: scheduleTagKey
    retainRunning: retainRunning
    retainStopped: retainStopped
    maxWorkers: maxWorkers
    stateTableName: stateTableName
  }
}

module subscriptionRoles './modules/subscriptionRoles.bicep' = [for subId in subscriptionIds: {
  name: 'schedulerRoles-${subId}'
  scope: subscription(subId)
  params: {
    principalId: functionStack.outputs.principalId
    assignmentSeed: functionAppName
  }
}]

output functionAppName string = functionStack.outputs.functionAppName
output functionAppId string = functionStack.outputs.functionAppId
output principalId string = functionStack.outputs.principalId
