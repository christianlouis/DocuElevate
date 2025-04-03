# User Guide

This guide helps you get started with using DocuElevate for document management and processing.

## Getting Started

DocuElevate offers an intuitive web interface for uploading, managing, and processing your documents.

### Accessing the System

1. Navigate to your DocuElevate instance (typically at `http://your-server-address:8000`)
2. If authentication is enabled, you'll be prompted to log in using your credentials

### Main Interface

DocuElevate features a simple navigation system with the following main sections:
- **Home**: Dashboard and overview
- **Upload**: For adding new documents to the system
- **Files**: For viewing and managing processed documents
- **About**: Information about DocuElevate

## Uploading Documents

### Web Upload

1. Navigate to the **Upload** page
2. Drag and drop files onto the upload area, or click to browse your files
3. Select files to upload (supported formats include PDF, Word documents, images, etc.)
4. Click "Upload" to begin the process
5. Your documents will be processed automatically according to the system configuration

### Email Attachments

If configured, DocuElevate can automatically fetch documents from email attachments:

1. Send an email with attachments to the configured email account
2. DocuElevate will poll the mailbox at the configured interval
3. Attachments will be automatically downloaded and processed
4. No further action is required

## Managing Documents

The **Files** page provides access to all processed documents:

1. Navigate to the **Files** page
2. Use the search box to find specific documents
3. Click on any file to view its details
4. Sort the list by any column by clicking on the column header

## Document Processing Features

Depending on the system configuration, DocuElevate can perform:

- **OCR** - Extract text from images and scanned PDFs
- **Metadata Extraction** - Automatically identify document types, dates, and other key information
- **PDF Conversion** - Convert various file formats to PDF
- **Document Distribution** - Store documents in Dropbox, Nextcloud, or Paperless NGX

## API Access

For programmatic access, DocuElevate provides a comprehensive REST API:

1. Navigate to `/docs` on your DocuElevate instance
2. The interactive Swagger documentation allows you to test API endpoints directly
3. Obtain an API token if authentication is enabled

## Troubleshooting

If you encounter issues while using DocuElevate, please refer to the [Troubleshooting Guide](Troubleshooting.md).
