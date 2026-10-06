#!/usr/bin/env bash
# Deploy or tear down the Foundry resources used by the benchmark.
#
#   scripts/foundry.sh deploy  [options]
#   scripts/foundry.sh destroy [options]
#   scripts/foundry.sh models  [name filter]   list models the Foundry resource offers (format, version, SKUs)
#
# Options (also settable as environment variables of the same name in capitals):
#   -s, --subscription <id|name>   default: current az subscription
#   -g, --resource-group <name>    default: frezz-sdc-rg-airllm-bench-dev
#   -l, --location <region>        default: swedencentral
#   -n, --name <account name>      default: frezz-sdc-ais-airllm-bench-dev
#   -m, --model <name>             default: gpt-5-mini, for example Llama-3.3-70B-Instruct
#       --model-format <format>    default: resolved automatically (OpenAI for gpt-5-mini)
#       --model-version <version>  default: resolved automatically (2025-08-07 for gpt-5-mini)
#       --sku <name>               default: GlobalStandard
#   -d, --deployment-name <name>   default: bench-model (use a second name to keep several deployments)
#       --capacity <n>             default: 10 (thousand tokens per minute)
#       --no-role                  skip the role assignment (needs Owner otherwise)
#       --no-purge                 destroy only: keep the soft deleted account
#   -y, --yes                      do not ask for confirmation
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TAG_KEY="purpose"
TAG_VALUE="airllm-vs-foundry"

SUBSCRIPTION="${SUBSCRIPTION:-}"
RESOURCE_GROUP="${RESOURCE_GROUP:-frezz-sdc-rg-airllm-bench-dev}"
LOCATION="${LOCATION:-swedencentral}"
ACCOUNT_NAME="${ACCOUNT_NAME:-frezz-sdc-ais-airllm-bench-dev}"
MODEL="${MODEL:-gpt-5-mini}"
MODEL_FORMAT="${MODEL_FORMAT:-}"
MODEL_VERSION="${MODEL_VERSION:-}"
SKU="${SKU:-GlobalStandard}"
FILTER=""
CAPACITY="${CAPACITY:-10}"
DEPLOYMENT_NAME="${DEPLOYMENT_NAME:-bench-model}"
ASSIGN_ROLE=true
PURGE=true
YES=false

die() { echo "Error: $*" >&2; exit 1; }
confirm() {
  $YES && return 0
  read -r -p "$1 [y/N] " answer
  [[ "$answer" == "y" || "$answer" == "Y" ]] || { echo "Aborted."; exit 1; }
}

[[ $# -ge 1 ]] || die "usage: $0 deploy|destroy [options]"
COMMAND="$1"; shift
while [[ $# -gt 0 ]]; do
  case "$1" in
    -s|--subscription) SUBSCRIPTION="$2"; shift 2 ;;
    -g|--resource-group) RESOURCE_GROUP="$2"; shift 2 ;;
    -l|--location) LOCATION="$2"; shift 2 ;;
    -n|--name) ACCOUNT_NAME="$2"; shift 2 ;;
    -m|--model) MODEL="$2"; shift 2 ;;
    --model-format) MODEL_FORMAT="$2"; shift 2 ;;
    --model-version) MODEL_VERSION="$2"; shift 2 ;;
    --sku) SKU="$2"; shift 2 ;;
    -d|--deployment-name) DEPLOYMENT_NAME="$2"; shift 2 ;;
    --capacity) CAPACITY="$2"; shift 2 ;;
    --no-role) ASSIGN_ROLE=false; shift ;;
    --no-purge) PURGE=false; shift ;;
    -y|--yes) YES=true; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    -*) die "unknown option: $1" ;;
    *) if [[ "$COMMAND" == "models" && -z "$FILTER" ]]; then FILTER="$1"; shift; else die "unexpected argument: $1"; fi ;;
  esac
done

command -v az >/dev/null || die "Azure CLI not found"
az account show >/dev/null 2>&1 || die "not signed in, run: az login"
[[ -z "$SUBSCRIPTION" ]] || az account set --subscription "$SUBSCRIPTION"

SUB_NAME="$(az account show --query name -o tsv)"
SUB_ID="$(az account show --query id -o tsv)"
TENANT="$(az account show --query tenantId -o tsv)"
echo "Subscription : $SUB_NAME ($SUB_ID)"
echo "Tenant       : $TENANT"
echo "Resource grp : $RESOURCE_GROUP"
echo "Region       : $LOCATION"
echo "Account      : $ACCOUNT_NAME"

# Replace or append KEY=VALUE in .env (portable for macOS and Linux).
set_env() {
  local key="$1" value="$2" file="$ROOT/.env" tmp
  [[ -f "$file" ]] || cp "$ROOT/.env.example" "$file"
  tmp="$(mktemp)"
  awk -v k="$key" -v v="$value" 'BEGIN{FS=OFS="="} $1==k {print k "=" v; done=1; next} {print} END{if(!done) print k "=" v}' "$file" > "$tmp"
  mv "$tmp" "$file"
}

# Fill MODEL_FORMAT and MODEL_VERSION from the models the Foundry resource offers.
resolve_model() {
  if [[ -z "$MODEL_FORMAT" || -z "$MODEL_VERSION" ]]; then
    if [[ "$MODEL" == "gpt-5-mini" ]]; then
      : "${MODEL_FORMAT:=OpenAI}"
      : "${MODEL_VERSION:=2025-08-07}"
    else
      local found
      found="$(az cognitiveservices account list-models --resource-group "$RESOURCE_GROUP" --name "$ACCOUNT_NAME" \
        --query "[?name=='$MODEL'] | [0].[format, version]" -o tsv 2>/dev/null || true)"
      [[ -n "$found" ]] || die "could not resolve model $MODEL on $ACCOUNT_NAME, run '$0 models' and pass --model-format and --model-version"
      MODEL_FORMAT="$(printf '%s' "$found" | cut -f1)"
      MODEL_VERSION="$(printf '%s' "$found" | cut -f2)"
    fi
  fi
}

list_models() {
  az cognitiveservices account list-models --resource-group "$RESOURCE_GROUP" --name "$ACCOUNT_NAME" \
    --query "[?contains(name, '$FILTER')].{name:name, format:format, version:version, skus:join(', ', skus[].name), lifecycle:lifecycleStatus}" \
    -o table
}

deploy() {
  resolve_model
  echo
  echo "Model        : $MODEL $MODEL_VERSION (format $MODEL_FORMAT, $SKU, capacity $CAPACITY)"
  echo "Deployment   : $DEPLOYMENT_NAME"
  confirm "Create resource group and deploy?"

  echo "Validating Bicep..."
  az bicep build --file "$ROOT/infra/main.bicep" --stdout >/dev/null

  az group create --name "$RESOURCE_GROUP" --location "$LOCATION" \
    --tags "$TAG_KEY=$TAG_VALUE" --output none

  local principal_id
  principal_id="$(az ad signed-in-user show --query id -o tsv)"

  local params=(
    accountName="$ACCOUNT_NAME" location="$LOCATION" deploymentName="$DEPLOYMENT_NAME"
    modelName="$MODEL" modelVersion="$MODEL_VERSION" modelFormat="$MODEL_FORMAT" skuName="$SKU" capacity="$CAPACITY"
    principalId="$principal_id" assignRole="$ASSIGN_ROLE"
  )

  echo "What-if:"
  az deployment group what-if --resource-group "$RESOURCE_GROUP" \
    --template-file "$ROOT/infra/main.bicep" --parameters "${params[@]}"
  confirm "Apply this deployment?"

  az deployment group create --name airllm-vs-foundry --resource-group "$RESOURCE_GROUP" \
    --template-file "$ROOT/infra/main.bicep" --parameters "${params[@]}" --output none

  set_env FOUNDRY_ENDPOINT "https://${ACCOUNT_NAME}.openai.azure.com/"
  set_env FOUNDRY_DEPLOYMENT "$DEPLOYMENT_NAME"
  set_env FOUNDRY_API_VERSION "2025-04-01-preview"
  echo
  echo "Done. .env updated. Role assignments can take a few minutes to take effect."
  echo "Test with: uv run python src/bench_foundry.py --runs 1"
}

destroy() {
  local tag
  az group exists --name "$RESOURCE_GROUP" | grep -q true || die "resource group $RESOURCE_GROUP does not exist"
  tag="$(az group show --name "$RESOURCE_GROUP" --query "tags.$TAG_KEY" -o tsv)"
  [[ "$tag" == "$TAG_VALUE" ]] || die "refusing to delete $RESOURCE_GROUP, it was not created by this script (missing tag $TAG_KEY=$TAG_VALUE)"

  local accounts
  accounts="$(az cognitiveservices account list --resource-group "$RESOURCE_GROUP" --query "[].name" -o tsv)"
  echo "Resources in $RESOURCE_GROUP:"
  az resource list --resource-group "$RESOURCE_GROUP" --query "[].{name:name,type:type}" -o table
  confirm "Delete resource group $RESOURCE_GROUP and everything in it?"

  az group delete --name "$RESOURCE_GROUP" --yes
  echo "Resource group deleted."

  if $PURGE && [[ -n "$accounts" ]]; then
    while IFS= read -r acc; do
      [[ -n "$acc" ]] || continue
      echo "Purging soft deleted account $acc..."
      az cognitiveservices account purge --name "$acc" --resource-group "$RESOURCE_GROUP" --location "$LOCATION"
    done <<< "$accounts"
  fi

  set_env FOUNDRY_ENDPOINT "https://<your-resource>.openai.azure.com/"
  set_env FOUNDRY_DEPLOYMENT "<your-deployment-name>"
  echo "Done. .env reset to placeholders."
}

case "$COMMAND" in
  deploy) deploy ;;
  models) list_models ;;
  destroy) destroy ;;
  *) die "unknown command: $COMMAND (use deploy, destroy or models)" ;;
esac
