// Minimal Microsoft Foundry setup for the benchmark (Entra ID only, no API keys).
// Model availability depends on region, check before changing the defaults.
targetScope = 'resourceGroup'

@description('Name of the Foundry (AI Services) resource. Also used as custom subdomain, must be globally unique.')
param accountName string

param location string = resourceGroup().location

@description('Deployment name used by the benchmark.')
param deploymentName string = 'bench-model'

@description('Model to deploy. GPT 5 family models are reasoning models.')
param modelName string = 'gpt-5-mini'

param modelVersion string = '2025-08-07'

@description('Model format: OpenAI for GPT models, Meta for Llama. Run scripts/foundry.sh models to see what your account offers.')
param modelFormat string = 'OpenAI'

@description('Deployment SKU, for example GlobalStandard.')
param skuName string = 'GlobalStandard'

@description('Capacity in thousands of tokens per minute.')
param capacity int = 10

@description('Object id of the user or group that runs the benchmark.')
param principalId string

@description('Assign the Cognitive Services OpenAI User role. Needs Owner or User Access Administrator on the resource group.')
param assignRole bool = true

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: accountName
  location: location
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    customSubDomainName: accountName
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: true // Entra ID only, no API keys
  }
}

resource deployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: account
  name: deploymentName
  sku: { name: skuName, capacity: capacity }
  properties: {
    model: { format: modelFormat, name: modelName, version: modelVersion }
  }
}

// Cognitive Services OpenAI User
var openAiUserRole = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'

resource roleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (assignRole) {
  scope: account
  name: guid(account.id, principalId, openAiUserRole)
  properties: {
    principalId: principalId
    principalType: 'User'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', openAiUserRole)
  }
}

output accountName string = account.name
output deploymentName string = deployment.name
