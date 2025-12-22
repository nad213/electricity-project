#!/bin/bash
# Check if an argument is provided
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <folder_prefix>"
    exit 1
fi
PREFIX="$1"
LAMBDA_DIR=$(ls lambda/ | grep "^${PREFIX}_" | head -n 1)
if [ -z "$LAMBDA_DIR" ]; then
    echo "Error: No folder in lambda/ starts with ${PREFIX}_"
    exit 1
fi
LAMBDA_DIR="lambda/$LAMBDA_DIR"
PY_FILE=$(ls "$LAMBDA_DIR"/*.py | head -n 1)
if [ -z "$PY_FILE" ]; then
    echo "Error: No .py file found in $LAMBDA_DIR"
    exit 1
fi
# Name of the zip file = name of the .py file (without the .py extension)
ZIP_NAME="${LAMBDA_DIR}/$(basename "$PY_FILE" .py).zip"
# Create the zip archive with only the .py file
zip -j "$ZIP_NAME" "$PY_FILE"
echo "File $ZIP_NAME created successfully!"
