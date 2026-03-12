targetScope = 'subscription'

@description('Principal ID of the Function App managed identity.')
param principalId string

@description('Stable seed used to generate deterministic role assignment names.')
param assignmentSeed string

var readerRoleDefinitionId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'acdd72a7-3385-48ef-bd42-f606fba81ae7')
var vmContributorRoleDefinitionId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '9980e02c-c2be-4d73-94e8-173b1dc7cf3c')

resource readerAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(subscription().subscriptionId, assignmentSeed, 'reader')
  properties: {
    roleDefinitionId: readerRoleDefinitionId
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

resource vmContributorAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(subscription().subscriptionId, assignmentSeed, 'vm-contributor')
  properties: {
    roleDefinitionId: vmContributorRoleDefinitionId
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}
