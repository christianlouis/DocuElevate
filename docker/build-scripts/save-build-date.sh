#!/bin/bash

# Get current date in Month DD, YYYY format (e.g., May 15, 2024)
BUILD_DATE=$(date +"%B %d, %Y")

# Save it to the BUILD_DATE file
echo $BUILD_DATE > /app/BUILD_DATE

# Also set it as an environment variable
echo "Setting BUILD_DATE=$BUILD_DATE"
export BUILD_DATE
