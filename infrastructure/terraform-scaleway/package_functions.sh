#!/usr/bin/env bash
# Package les 2 functions pour Scaleway : deps vendorées À LA RACINE du zip, à côté
# du handler (le runtime Scaleway ajoute le dossier de déploiement au sys.path ;
# il n'ajoute PAS un sous-dossier package/, d'où les deps à plat).
#
# ⚠️ Le runtime Python 3.12 de Scaleway est MUSL (Alpine), pas glibc : il faut des
# wheels musllinux, sinon les extensions C (numpy/pyarrow) ne sont pas reconnues
# (EXT_SUFFIX = .cpython-312-x86_64-linux-musl.so) → ImportError au chargement.
# Usage : bash package_functions.sh   (depuis infrastructure/terraform-scaleway/)
set -euo pipefail

cd "$(dirname "$0")"
LAMBDAS_DIR=../lambdas
BUILD_DIR=build
PYTHON_VERSION=3.12

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# Deps communes, wheels musllinux (runtime Alpine). On passe les deux tags musl :
# certains paquets ne publient que 1_1 ou que 1_2, un système musl 1.2 lit les deux.
DEPS_DIR=$(mktemp -d)
pip install \
  --target "$DEPS_DIR/package" \
  --platform musllinux_1_2_x86_64 \
  --platform musllinux_1_1_x86_64 \
  --python-version "$PYTHON_VERSION" \
  --only-binary=:all: \
  -r requirements-functions.txt

# Élagage — la limite Scaleway est de 100 MiB par zip (500 MiB décompressé),
# le package complet la dépasse légèrement.
PKG="$DEPS_DIR/package"
#  - botocore embarque les définitions de ~400 services AWS ; seul s3 est utilisé
find "$PKG/botocore/data" -mindepth 1 -maxdepth 1 -type d ! -name 's3' -exec rm -rf {} +
#  - suites de tests, caches, headers C
rm -rf "$PKG"/numpy/tests "$PKG"/numpy/*/tests \
       "$PKG"/pandas/tests \
       "$PKG"/pyarrow/tests "$PKG"/pyarrow/include "$PKG"/pyarrow/src
find "$PKG" -type d -name '__pycache__' -exec rm -rf {} +
#  - modules pyarrow non utilisés par pandas.to_parquet/read_parquet
#    (Flight RPC, Substrait — gros .so chargés seulement par pyarrow.flight/substrait)
rm -f "$PKG"/pyarrow/libarrow_flight* "$PKG"/pyarrow/libarrow_substrait* \
      "$PKG"/pyarrow/_flight* "$PKG"/pyarrow/_substrait*

package_one() {
  local src_dir=$1 handler_file=$2 zip_name=$3
  local staging
  staging=$(mktemp -d)
  cp "$LAMBDAS_DIR/$src_dir/$handler_file" "$staging/"
  cp -r "$DEPS_DIR/package/." "$staging/"   # deps à la racine, à côté du handler
  (cd "$staging" && zip -qr9 - .) > "$BUILD_DIR/$zip_name"
  rm -rf "$staging"
  echo "→ $BUILD_DIR/$zip_name ($(du -h "$BUILD_DIR/$zip_name" | cut -f1))"
}

package_one 01_odre_eco2mix          odre_eco2mix.py          odre_eco2mix.zip
package_one 02_scrape_rte_production scrape_rte_production.py scrape_rte_production.zip

rm -rf "$DEPS_DIR"
echo "OK — terraform plan/apply peut être lancé."
