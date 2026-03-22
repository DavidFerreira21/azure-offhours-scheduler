#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./scripts/bootstrap_scheduler_tables.sh --resource-group <rg> --storage-account <account> [options]

Required:
  --resource-group <rg>        Resource group that contains the storage account
  --storage-account <account>  Storage account used by the scheduler

Optional:
  --config-table <name>        Default: OffHoursSchedulerConfig
  --schedule-table <name>      Default: OffHoursSchedulerSchedules
  --timezone <tz>              Default: America/Sao_Paulo
  --schedule-name <name>       Default: business-hours
  --start <HH:MM>              Default: 08:00
  --stop <HH:MM>               Default: 18:00
  --updated-by <value>         Default: current az account user, fallback bicep-bootstrap
EOF
}

RESOURCE_GROUP=""
STORAGE_ACCOUNT=""
CONFIG_TABLE="OffHoursSchedulerConfig"
SCHEDULE_TABLE="OffHoursSchedulerSchedules"
DEFAULT_TIMEZONE="America/Sao_Paulo"
SCHEDULE_NAME="business-hours"
BUSINESS_START="08:00"
BUSINESS_STOP="18:00"
UPDATED_BY=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --resource-group)
      RESOURCE_GROUP="$2"
      shift 2
      ;;
    --storage-account)
      STORAGE_ACCOUNT="$2"
      shift 2
      ;;
    --config-table)
      CONFIG_TABLE="$2"
      shift 2
      ;;
    --schedule-table)
      SCHEDULE_TABLE="$2"
      shift 2
      ;;
    --timezone)
      DEFAULT_TIMEZONE="$2"
      shift 2
      ;;
    --schedule-name)
      SCHEDULE_NAME="$2"
      shift 2
      ;;
    --start)
      BUSINESS_START="$2"
      shift 2
      ;;
    --stop)
      BUSINESS_STOP="$2"
      shift 2
      ;;
    --updated-by)
      UPDATED_BY="$2"
      shift 2
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

if [[ -z "$RESOURCE_GROUP" || -z "$STORAGE_ACCOUNT" ]]; then
  usage >&2
  exit 1
fi

if [[ -z "$UPDATED_BY" ]]; then
  UPDATED_BY="$(az account show --query user.name -o tsv 2>/dev/null || true)"
fi

if [[ -z "$UPDATED_BY" ]]; then
  UPDATED_BY="bicep-bootstrap"
fi

UPDATED_AT_UTC="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

entity_exists() {
  local table_name="$1"
  local partition_key="$2"
  local row_key="$3"

  az storage entity show \
    --account-name "$STORAGE_ACCOUNT" \
    --auth-mode login \
    --table-name "$table_name" \
    --partition-key "$partition_key" \
    --row-key "$row_key" \
    --only-show-errors \
    -o none >/dev/null 2>&1
}

insert_entity() {
  local table_name="$1"
  shift

  if ! az storage entity insert \
    --account-name "$STORAGE_ACCOUNT" \
    --auth-mode login \
    --table-name "$table_name" \
    --if-exists fail \
    --entity "$@" \
    --only-show-errors \
    -o none; then
    cat >&2 <<EOF
ERROR: Failed to write entity to table '$table_name' in storage account '$STORAGE_ACCOUNT'.
This bootstrap now uses Microsoft Entra ID, not shared keys.
Ensure the current Azure identity has Storage Table Data Contributor on the scheduler storage account and allow a few minutes for RBAC propagation after deployment.
EOF
    exit 1
  fi
}

if entity_exists "$CONFIG_TABLE" "GLOBAL" "runtime"; then
  echo "Config entity already exists in $CONFIG_TABLE; skipping bootstrap for global settings."
else
  insert_entity \
    "$CONFIG_TABLE" \
    PartitionKey=GLOBAL \
    RowKey=runtime \
    DRY_RUN=true \
    DEFAULT_TIMEZONE="$DEFAULT_TIMEZONE" \
    SCHEDULE_TAG_KEY=schedule \
    RETAIN_RUNNING=false \
    RETAIN_STOPPED=false \
    Version=1 \
    UpdatedAtUtc="$UPDATED_AT_UTC" \
    UpdatedBy="$UPDATED_BY"
  echo "Inserted default global configuration into $CONFIG_TABLE."
fi

if entity_exists "$SCHEDULE_TABLE" "SCHEDULE" "$SCHEDULE_NAME"; then
  echo "Schedule '$SCHEDULE_NAME' already exists in $SCHEDULE_TABLE; skipping bootstrap schedule."
else
  insert_entity \
    "$SCHEDULE_TABLE" \
    PartitionKey=SCHEDULE \
    RowKey="$SCHEDULE_NAME" \
    Start="$BUSINESS_START" \
    Stop="$BUSINESS_STOP" \
    SkipDays=saturday,sunday \
    Enabled=true \
    Version=1 \
    UpdatedAtUtc="$UPDATED_AT_UTC" \
    UpdatedBy="$UPDATED_BY"
  echo "Inserted default schedule '$SCHEDULE_NAME' into $SCHEDULE_TABLE."
fi

echo "Bootstrap completed."
