#!/bin/bash

# Vérifie qu'un argument est fourni
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <préfixe_du_dossier>"
    exit 1
fi

# Récupère le préfixe du dossier depuis l'argument
PREFIX="$1"
BUILD_DIR="build_temp"

# Trouve le dossier correspondant dans ../lambdas/
LAMBDA_DIR=$(ls ../lambdas/ | grep "^${PREFIX}_" | head -n 1)

if [ -z "$LAMBDA_DIR" ]; then
    echo "Erreur : Aucun dossier dans ../lambdas/ ne commence par ${PREFIX}_"
    exit 1
fi

LAMBDA_DIR="../lambdas/$LAMBDA_DIR"

# Trouve le fichier .py dans le dossier
PY_FILE=$(ls "$LAMBDA_DIR"/*.py | head -n 1)
if [ -z "$PY_FILE" ]; then
    echo "Erreur : Aucun fichier .py trouvé dans $LAMBDA_DIR"
    exit 1
fi

# Nom du zip = nom du fichier .py (sans le .py)
ZIP_NAME="${LAMBDA_DIR}/$(basename "$PY_FILE" .py).zip"

# Crée le dossier temporaire
mkdir -p "$BUILD_DIR"

# Installe les dépendances dans le dossier temporaire
pip install --target="$BUILD_DIR" -r "$LAMBDA_DIR/requirements.txt"

# Copie le code source
cp "$LAMBDA_DIR"/*.py "$BUILD_DIR/"

# Crée l'archive zip
cd "$BUILD_DIR" || exit 1
zip -r "../$ZIP_NAME" .
cd ..

# Nettoie
rm -rf "$BUILD_DIR"

echo "Fichier $ZIP_NAME créé avec succès !"
