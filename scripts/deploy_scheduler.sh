#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./scripts/deploy_scheduler.sh [options]

Optional:
  --parameters-file <file>   Default: infra/bicep/main.parameters.json
  --deployment-name <name>   Default: offhours-scheduler-deploy
  --no-validate              Skip az deployment sub validate before create
  --no-publish               Deploy infra, but skip Function publish

Pre-requisites checked automatically:
  - az CLI installed and authenticated
  - active Azure subscription selected
  - access to the effective scheduler scope resolved from subscriptionIds + managementGroupIds - excludeSubscriptionIds
EOF
}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PARAMETERS_FILE="$ROOT_DIR/infra/bicep/main.parameters.json"
DEPLOYMENT_NAME="offhours-scheduler-deploy"
PUBLISH_FUNCTION=true
VALIDATE_DEPLOYMENT=true
DEPLOY_LOCATION=""
RESOURCE_GROUP_NAME=""
RESOURCE_GROUP_NAME_GENERATED=false
NAME_PREFIX=""
TABLE_OPERATORS_GROUP_OBJECT_ID=""
EXPLICIT_SUBSCRIPTIONS=()
MANAGEMENT_GROUP_IDS=()
EXCLUDE_SUBSCRIPTIONS=()
EFFECTIVE_SUBSCRIPTIONS=()
TARGET_RESOURCE_LOCATIONS=()
RESOLVED_PARAMETERS_FILE=""
OFFHOURS_CONTEXT_FILE=""
CURRENT_SUBSCRIPTION_ID=""
FUNCTION_PACKAGE_PATH=""

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

require_command() {
  local command_name="$1"
  command -v "$command_name" >/dev/null 2>&1 || fail "Missing required command '$command_name'."
}

generate_random_suffix() {
  python3 - <<'PY'
import secrets

alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
print("".join(secrets.choice(alphabet) for _ in range(6)))
PY
}

generate_resource_group_name() {
  local normalized_prefix="${NAME_PREFIX,,}"
  normalized_prefix="${normalized_prefix//_/-}"
  normalized_prefix="${normalized_prefix// /-}"

  if [[ -z "$normalized_prefix" ]]; then
    normalized_prefix="offhours"
  fi

  printf 'rg-%s-%s\n' "$normalized_prefix" "$(generate_random_suffix)"
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
  CURRENT_SUBSCRIPTION_ID="$current_subscription"
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

  [[ -n "$NAME_PREFIX" ]] || fail "Parameter 'namePrefix' is required in $PARAMETERS_FILE."

  if [[ -z "$DEPLOY_LOCATION" ]]; then
    DEPLOY_LOCATION="eastus"
  fi

  if [[ -z "$RESOURCE_GROUP_NAME" ]]; then
    RESOURCE_GROUP_NAME="$(generate_resource_group_name)"
    RESOURCE_GROUP_NAME_GENERATED=true
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

  python3 - "$PARAMETERS_FILE" "$RESOLVED_PARAMETERS_FILE" "$RESOURCE_GROUP_NAME" "${EFFECTIVE_SUBSCRIPTIONS[@]}" <<'PY'
import json
import sys
from pathlib import Path

source_path = Path(sys.argv[1])
target_path = Path(sys.argv[2])
resource_group_name = sys.argv[3]
effective_subscriptions = sys.argv[4:]

with source_path.open("r", encoding="utf-8") as handle:
    data = json.load(handle)

parameters = data.setdefault("parameters", {})
parameters["resourceGroupName"] = {"value": resource_group_name}
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
  if [[ -n "$FUNCTION_PACKAGE_PATH" && -f "$FUNCTION_PACKAGE_PATH" ]]; then
    rm -f "$FUNCTION_PACKAGE_PATH"
  fi
}

write_offhours_context() {
  local storage_suffix
  local table_service_uri

  storage_suffix="$(
    az cloud show \
      --query suffixes.storageEndpoint \
      -o tsv
  )"

  [[ -n "$storage_suffix" ]] || fail "Unable to resolve Azure storage endpoint suffix."

  table_service_uri="https://${STORAGE_ACCOUNT_NAME}.table.${storage_suffix}"
  OFFHOURS_CONTEXT_FILE="$ROOT_DIR/.offhours.env"

  cat >"$OFFHOURS_CONTEXT_FILE" <<EOF
OFFHOURS_RESOURCE_GROUP=$RESOURCE_GROUP
OFFHOURS_FUNCTION_APP_NAME=$FUNCTION_APP_NAME
OFFHOURS_STORAGE_ACCOUNT_NAME=$STORAGE_ACCOUNT_NAME
OFFHOURS_TABLE_SERVICE_URI=$table_service_uri
EOF

  echo "Wrote CLI context to $OFFHOURS_CONTEXT_FILE"
}

validate_deployment() {
  echo "Validating subscription-scope deployment..."
  az deployment sub validate \
    --name "${DEPLOYMENT_NAME}-validate" \
    --location "$DEPLOY_LOCATION" \
    --template-file "$ROOT_DIR/infra/bicep/main.bicep" \
    --parameters @"$RESOLVED_PARAMETERS_FILE" \
    --only-show-errors \
    -o none || fail "Bicep validation failed. Check permissions and parameter values."
}

build_function_package() {
  echo "Building Function App zip package..."
  FUNCTION_PACKAGE_PATH="$("$ROOT_DIR/scripts/build_function_app_package.sh" /tmp/offhours-function-package.zip)"
  [[ -f "$FUNCTION_PACKAGE_PATH" ]] || fail "Function App package was not created."
  echo "Function App package: $FUNCTION_PACKAGE_PATH"
}

publish_function_package() {
  printf '%s\n' "Publishing Function App $FUNCTION_APP_NAME with zip deploy..."
  printf '%s\n' "This step may take several minutes because Azure performs remote build, package extraction, and trigger registration."
  az functionapp deployment source config-zip \
    --resource-group "$RESOURCE_GROUP" \
    --name "$FUNCTION_APP_NAME" \
    --src "$FUNCTION_PACKAGE_PATH" \
    --build-remote true \
    --timeout 600 \
    --only-show-errors \
    -o none || fail "Function App zip deployment failed."
}

sync_function_triggers() {
  local max_attempts=6
  local attempt=1

  while [[ "$attempt" -le "$max_attempts" ]]; do
    echo "Synchronizing Function App triggers (attempt $attempt/$max_attempts)..."
    if az rest \
      --method post \
      --url "https://management.azure.com/subscriptions/$CURRENT_SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Web/sites/$FUNCTION_APP_NAME/syncfunctiontriggers?api-version=2024-04-01" \
      --only-show-errors \
      -o none; then
      return 0
    fi

    if [[ "$attempt" -lt "$max_attempts" ]]; then
      echo "Trigger sync is not ready yet; waiting before retry."
      sleep 10
    fi

    attempt=$((attempt + 1))
  done

  echo "Trigger sync did not succeed after $max_attempts attempts; continuing with function registration checks."
  return 1
}

query_published_function_name() {
  local expected_function_name="$1"

  timeout 10s \
    az functionapp function list \
      --resource-group "$RESOURCE_GROUP" \
      --name "$FUNCTION_APP_NAME" \
      --query "[?ends_with(name, '/$expected_function_name')].name | [0]" \
      --only-show-errors \
      -o tsv 2>/dev/null || true
}

wait_for_published_function() {
  local expected_function_name="OffHoursTimer"
  local max_attempts=24
  local attempt=1
  local published_name=""

  while [[ "$attempt" -le "$max_attempts" ]]; do
    published_name="$(query_published_function_name "$expected_function_name")"

    if [[ -n "$published_name" ]]; then
      echo "Function '$expected_function_name' is registered."
      return 0
    fi

    echo "Function '$expected_function_name' is not registered yet (attempt $attempt/$max_attempts)."

    if [[ "$attempt" -eq 3 || "$attempt" -eq 9 || "$attempt" -eq 18 || "$attempt" -eq 27 ]]; then
      sync_function_triggers || true
    fi

    sleep 10
    attempt=$((attempt + 1))
  done

  fail "Function '$expected_function_name' was not registered after publish."
}

print_preflight_summary() {
  echo "Preflight summary:"
  if [[ "$RESOURCE_GROUP_NAME_GENERATED" == "true" ]]; then
    echo "  - Resource group: $RESOURCE_GROUP_NAME (auto-generated)"
  else
    echo "  - Resource group: $RESOURCE_GROUP_NAME"
  fi
  echo "  - Location: $DEPLOY_LOCATION"
  echo "  - Name prefix: $NAME_PREFIX"
  echo "  - Publish Function App: $PUBLISH_FUNCTION"
  echo "  - Validate deployment: $VALIDATE_DEPLOYMENT"
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
    --no-validate)
      VALIDATE_DEPLOYMENT=false
      shift
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

require_command realpath
require_command python3
require_command az

trap cleanup EXIT

PARAMETERS_FILE="$(realpath "$PARAMETERS_FILE")"
[[ -f "$PARAMETERS_FILE" ]] || fail "Parameters file not found: $PARAMETERS_FILE"

load_parameters
check_azure_login
resolve_effective_subscriptions
build_resolved_parameters_file
check_target_subscriptions
print_preflight_summary

if [[ "$VALIDATE_DEPLOYMENT" == "true" ]]; then
  validate_deployment
else
  echo "Skipping subscription-scope validation."
fi

printf '%s\n' "Deploying infrastructure..."
printf '%s\n' "This step may take several minutes, especially when Azure needs to create RBAC assignments and platform resources."
az deployment sub create \
  --name "$DEPLOYMENT_NAME" \
  --location "$DEPLOY_LOCATION" \
  --template-file "$ROOT_DIR/infra/bicep/main.bicep" \
  --parameters @"$RESOLVED_PARAMETERS_FILE" \
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

write_offhours_context

if [[ "$PUBLISH_FUNCTION" == "false" ]]; then
  echo "Skipping Function publish."
  echo "Deployment completed."
  echo "Resource group: $RESOURCE_GROUP"
  echo "Function App: $FUNCTION_APP_NAME"
  echo "Storage Account: $STORAGE_ACCOUNT_NAME"
  echo "Next steps:"
  echo "  1. If table RBAC was created during this deploy, you may need to refresh Azure CLI credentials:"
  echo "     az logout"
  echo "     az login"
  echo "  2. Apply the initial scheduler configuration:"
  echo "     ./offhours config apply --file runtime.yaml --execute"
  echo "  3. Apply the initial schedule:"
  echo "     ./offhours schedule apply --file business-hours.yaml --execute"
  exit 0
fi

printf '%s\n' "Preparing Function App publish bundle..."
"$ROOT_DIR/scripts/prepare_function_app_publish.sh"
build_function_package
publish_function_package
sync_function_triggers
wait_for_published_function

echo "Deployment completed."
echo "Resource group: $RESOURCE_GROUP"
echo "Function App: $FUNCTION_APP_NAME"
echo "Storage Account: $STORAGE_ACCOUNT_NAME"
echo "Next steps:"
echo "  1. If table RBAC was created during this deploy, you may need to refresh Azure CLI credentials:"
echo "     az logout"
echo "     az login"
echo "  2. Apply the initial scheduler configuration:"
echo "     ./offhours config apply --file runtime.yaml --execute"
echo "  3. Apply the initial schedule:"
echo "     ./offhours schedule apply --file business-hours.yaml --execute"
