#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./scripts/deploy_scheduler.sh --parameters-file <file> [options]

Required:
  --parameters-file <file>   Path to the Bicep parameters file

Optional:
  --deployment-name <name>   Default: offhours-scheduler-deploy
  --no-publish               Deploy infra and bootstrap tables, but skip Function publish

Pre-requisites checked automatically:
  - az CLI installed and authenticated
  - active Azure subscription selected
  - access to the effective scheduler scope resolved from subscriptionIds + managementGroupIds - excludeSubscriptionIds
  - Bicep subscription deployment validation succeeds
  - func Core Tools installed when publish is enabled
EOF
}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PARAMETERS_FILE=""
DEPLOYMENT_NAME="offhours-scheduler-deploy"
PUBLISH_FUNCTION=true
DEPLOY_LOCATION=""
RESOURCE_GROUP_NAME=""
NAME_PREFIX=""
TABLE_OPERATORS_GROUP_OBJECT_ID=""
EXPLICIT_SUBSCRIPTIONS=()
MANAGEMENT_GROUP_IDS=()
EXCLUDE_SUBSCRIPTIONS=()
EFFECTIVE_SUBSCRIPTIONS=()
TARGET_RESOURCE_LOCATIONS=()
RESOLVED_PARAMETERS_FILE=""

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

require_command() {
  local command_name="$1"
  command -v "$command_name" >/dev/null 2>&1 || fail "Missing required command '$command_name'."
}

read_parameter() {
  local parameter_name="$1"

  python3 - "$PARAMETERS_FILE" "$parameter_name" <<'PY'
import json
import sys
from pathlib import Path

parameters_file = Path(sys.argv[1])
parameter_name = sys.argv[2]

with parameters_file.open("r", encoding="utf-8") as handle:
    data = json.load(handle)

value = data.get("parameters", {}).get(parameter_name, {}).get("value", "")

if isinstance(value, list):
    for item in value:
        print(item)
elif isinstance(value, bool):
    print("true" if value else "false")
elif value is None:
    print("")
else:
    print(value)
PY
}

check_azure_login() {
  local current_user
  local current_subscription

  current_user="$(az account show --query user.name -o tsv 2>/dev/null || true)"
  current_subscription="$(az account show --query id -o tsv 2>/dev/null || true)"

  [[ -n "$current_user" && -n "$current_subscription" ]] || fail "Azure CLI is not authenticated. Run 'az login' and select the deployment subscription."

  echo "Azure account: $current_user"
  echo "Active subscription: $current_subscription"
}

load_parameters() {
  RESOURCE_GROUP_NAME="$(read_parameter resourceGroupName)"
  DEPLOY_LOCATION="$(read_parameter location)"
  NAME_PREFIX="$(read_parameter namePrefix)"
  TABLE_OPERATORS_GROUP_OBJECT_ID="$(read_parameter tableOperatorsGroupObjectId)"

  mapfile -t EXPLICIT_SUBSCRIPTIONS < <(read_parameter subscriptionIds)
  mapfile -t MANAGEMENT_GROUP_IDS < <(read_parameter managementGroupIds)
  mapfile -t EXCLUDE_SUBSCRIPTIONS < <(read_parameter excludeSubscriptionIds)
  mapfile -t TARGET_RESOURCE_LOCATIONS < <(read_parameter targetResourceLocations)

  [[ -n "$RESOURCE_GROUP_NAME" ]] || fail "Parameter 'resourceGroupName' is required in $PARAMETERS_FILE."
  [[ -n "$NAME_PREFIX" ]] || fail "Parameter 'namePrefix' is required in $PARAMETERS_FILE."

  if [[ -z "$DEPLOY_LOCATION" ]]; then
    DEPLOY_LOCATION="eastus"
  fi

  if [[ "${#EXPLICIT_SUBSCRIPTIONS[@]}" -eq 0 && "${#MANAGEMENT_GROUP_IDS[@]}" -eq 0 ]]; then
    fail "Configure at least one of 'subscriptionIds' or 'managementGroupIds' in $PARAMETERS_FILE."
  fi
}

resolve_management_group_subscriptions() {
  local management_group_id="$1"

  az graph query \
    --management-groups "$management_group_id" \
    -q "ResourceContainers | where type =~ 'microsoft.resources/subscriptions' | project subscriptionId" \
    --query 'data[].subscriptionId' \
    --only-show-errors \
    -o tsv || fail "Unable to resolve subscriptions for management group '$management_group_id'. Check Azure CLI access and Resource Graph permissions."
}

resolve_effective_subscriptions() {
  local explicit_subscription
  local management_group_id
  local resolved_subscription
  local excluded_subscription
  declare -A seen_subscriptions=()

  EFFECTIVE_SUBSCRIPTIONS=()

  for explicit_subscription in "${EXPLICIT_SUBSCRIPTIONS[@]}"; do
    [[ -n "$explicit_subscription" ]] || continue
    if [[ -z "${seen_subscriptions[$explicit_subscription]:-}" ]]; then
      seen_subscriptions["$explicit_subscription"]=1
      EFFECTIVE_SUBSCRIPTIONS+=("$explicit_subscription")
    fi
  done

  if [[ "${#MANAGEMENT_GROUP_IDS[@]}" -gt 0 ]]; then
    az graph query -h >/dev/null 2>&1 || fail "Azure CLI 'graph' commands are required when using managementGroupIds."

    for management_group_id in "${MANAGEMENT_GROUP_IDS[@]}"; do
      [[ -n "$management_group_id" ]] || continue

      while IFS= read -r resolved_subscription; do
        [[ -n "$resolved_subscription" ]] || continue

        if [[ -z "${seen_subscriptions[$resolved_subscription]:-}" ]]; then
          seen_subscriptions["$resolved_subscription"]=1
          EFFECTIVE_SUBSCRIPTIONS+=("$resolved_subscription")
        fi
      done < <(resolve_management_group_subscriptions "$management_group_id")
    done
  fi

  if [[ "${#EXCLUDE_SUBSCRIPTIONS[@]}" -gt 0 ]]; then
    for excluded_subscription in "${EXCLUDE_SUBSCRIPTIONS[@]}"; do
      [[ -n "$excluded_subscription" ]] || continue
      unset "seen_subscriptions[$excluded_subscription]"
    done

    EFFECTIVE_SUBSCRIPTIONS=()
    for explicit_subscription in "${!seen_subscriptions[@]}"; do
      EFFECTIVE_SUBSCRIPTIONS+=("$explicit_subscription")
    done
    IFS=$'\n' EFFECTIVE_SUBSCRIPTIONS=($(printf '%s\n' "${EFFECTIVE_SUBSCRIPTIONS[@]}" | sort))
    unset IFS
  fi

  if [[ "${#EFFECTIVE_SUBSCRIPTIONS[@]}" -eq 0 ]]; then
    fail "The effective scheduler scope is empty after applying management groups and exclusions."
  fi
}

check_target_subscriptions() {
  local target_subscription

  echo "Effective target subscriptions:"
  for target_subscription in "${EFFECTIVE_SUBSCRIPTIONS[@]}"; do
    [[ -n "$target_subscription" ]] || continue

    az account show \
      --subscription "$target_subscription" \
      --query id \
      --only-show-errors \
      -o tsv >/dev/null || fail "Current Azure identity cannot access subscription '$target_subscription'."

    echo "  - $target_subscription"
  done
}

build_resolved_parameters_file() {
  RESOLVED_PARAMETERS_FILE="$(mktemp /tmp/offhours-params.XXXXXX.json)"

  python3 - "$PARAMETERS_FILE" "$RESOLVED_PARAMETERS_FILE" "${EFFECTIVE_SUBSCRIPTIONS[@]}" <<'PY'
import json
import sys
from pathlib import Path

source_path = Path(sys.argv[1])
target_path = Path(sys.argv[2])
effective_subscriptions = sys.argv[3:]

with source_path.open("r", encoding="utf-8") as handle:
    data = json.load(handle)

parameters = data.setdefault("parameters", {})
parameters["subscriptionIds"] = {"value": effective_subscriptions}

with target_path.open("w", encoding="utf-8") as handle:
    json.dump(data, handle, indent=2)
    handle.write("\n")
PY
}

cleanup() {
  if [[ -n "$RESOLVED_PARAMETERS_FILE" && -f "$RESOLVED_PARAMETERS_FILE" ]]; then
    rm -f "$RESOLVED_PARAMETERS_FILE"
  fi
}

validate_deployment() {
  echo "Validating subscription-scope deployment..."
  az deployment sub validate \
    --name "${DEPLOYMENT_NAME}-validate" \
    --location "$DEPLOY_LOCATION" \
    --template-file "$ROOT_DIR/infra/bicep/main.bicep" \
    --parameters @"$RESOLVED_PARAMETERS_FILE" bootstrapDefaults=false \
    --only-show-errors \
    -o none || fail "Bicep validation failed. Check permissions and parameter values."
}

print_preflight_summary() {
  echo "Preflight summary:"
  echo "  - Resource group: $RESOURCE_GROUP_NAME"
  echo "  - Location: $DEPLOY_LOCATION"
  echo "  - Name prefix: $NAME_PREFIX"
  echo "  - Publish Function App: $PUBLISH_FUNCTION"
  if [[ "${#EXPLICIT_SUBSCRIPTIONS[@]}" -gt 0 ]]; then
    echo "  - Explicit subscriptions: ${EXPLICIT_SUBSCRIPTIONS[*]}"
  else
    echo "  - Explicit subscriptions: <none>"
  fi
  if [[ "${#MANAGEMENT_GROUP_IDS[@]}" -gt 0 ]]; then
    echo "  - Management groups: ${MANAGEMENT_GROUP_IDS[*]}"
  else
    echo "  - Management groups: <none>"
  fi
  if [[ "${#EXCLUDE_SUBSCRIPTIONS[@]}" -gt 0 ]]; then
    echo "  - Excluded subscriptions: ${EXCLUDE_SUBSCRIPTIONS[*]}"
  else
    echo "  - Excluded subscriptions: <none>"
  fi
  echo "  - Effective subscriptions count: ${#EFFECTIVE_SUBSCRIPTIONS[@]}"
  if [[ "${#TARGET_RESOURCE_LOCATIONS[@]}" -gt 0 ]]; then
    echo "  - Target resource locations: ${TARGET_RESOURCE_LOCATIONS[*]}"
  else
    echo "  - Target resource locations: <all>"
  fi

  if [[ -n "$TABLE_OPERATORS_GROUP_OBJECT_ID" ]]; then
    echo "  - Table operators group object ID: $TABLE_OPERATORS_GROUP_OBJECT_ID"
  else
    echo "  - Table operators group object ID: not configured"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --parameters-file)
      PARAMETERS_FILE="$2"
      shift 2
      ;;
    --deployment-name)
      DEPLOYMENT_NAME="$2"
      shift 2
      ;;
    --no-publish)
      PUBLISH_FUNCTION=false
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "$PARAMETERS_FILE" ]]; then
  usage >&2
  exit 1
fi

require_command realpath
require_command python3
require_command az
if [[ "$PUBLISH_FUNCTION" == "true" ]]; then
  require_command func
fi

trap cleanup EXIT

PARAMETERS_FILE="$(realpath "$PARAMETERS_FILE")"
[[ -f "$PARAMETERS_FILE" ]] || fail "Parameters file not found: $PARAMETERS_FILE"

load_parameters
check_azure_login
resolve_effective_subscriptions
build_resolved_parameters_file
check_target_subscriptions
print_preflight_summary
validate_deployment

echo "Deploying infrastructure with manual bootstrap fallback..."
az deployment sub create \
  --name "$DEPLOYMENT_NAME" \
  --location "$DEPLOY_LOCATION" \
  --template-file "$ROOT_DIR/infra/bicep/main.bicep" \
  --parameters @"$RESOLVED_PARAMETERS_FILE" bootstrapDefaults=false \
  --only-show-errors \
  -o none

RESOURCE_GROUP="$(
  az deployment sub show \
    --name "$DEPLOYMENT_NAME" \
    --query properties.parameters.resourceGroupName.value \
    -o tsv
)"

FUNCTION_APP_NAME="$(
  az deployment sub show \
    --name "$DEPLOYMENT_NAME" \
    --query properties.outputs.functionAppName.value \
    -o tsv
)"

STORAGE_ACCOUNT_NAME="$(
  az deployment sub show \
    --name "$DEPLOYMENT_NAME" \
    --query properties.outputs.storageAccountName.value \
    -o tsv
)"

echo "Bootstrapping scheduler tables in storage account $STORAGE_ACCOUNT_NAME..."
"$ROOT_DIR/scripts/bootstrap_scheduler_tables.sh" \
  --resource-group "$RESOURCE_GROUP" \
  --storage-account "$STORAGE_ACCOUNT_NAME"

if [[ "$PUBLISH_FUNCTION" == "false" ]]; then
  echo "Skipping Function publish."
  echo "Deployment completed."
  echo "Resource group: $RESOURCE_GROUP"
  echo "Function App: $FUNCTION_APP_NAME"
  echo "Storage Account: $STORAGE_ACCOUNT_NAME"
  exit 0
fi

echo "Preparing Function App publish bundle..."
"$ROOT_DIR/scripts/prepare_function_app_publish.sh"

echo "Publishing Function App $FUNCTION_APP_NAME..."
(
  cd "$ROOT_DIR/function"
  func azure functionapp publish "$FUNCTION_APP_NAME" --python
)

echo "Deployment completed."
echo "Resource group: $RESOURCE_GROUP"
echo "Function App: $FUNCTION_APP_NAME"
echo "Storage Account: $STORAGE_ACCOUNT_NAME"
