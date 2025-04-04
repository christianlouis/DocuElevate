#!/usr/bin/env python3
import os
import requests
import logging
import mimetypes
import json
from celery import shared_task
from app.config import settings
from app.tasks.process_document import process_document

logger = logging.getLogger(__name__)

@shared_task
def convert_to_pdf(file_path):
    """
    Converts a file to PDF using Gotenberg's API.
    Determines the appropriate Gotenberg endpoint based on the file's MIME type.
    On success, saves the PDF locally and enqueues it for processing.
    """
    gotenberg_url = getattr(settings, "gotenberg_url", None)
    if not gotenberg_url:
        logger.error("Gotenberg URL is not configured in settings.")
        return

    # Try to guess the MIME type based on file content and extension
    mime_type, encoding = mimetypes.guess_type(file_path)
    file_ext = os.path.splitext(file_path)[1].lower()
    logger.info(f"Guessed MIME type for '{file_path}' is: {mime_type}, extension: {file_ext}")

    # Determine which Gotenberg endpoint to use
    endpoint = None
    form_data = {}
    files = {}
    
    # Dictionary mapping file extensions to their handlers
    OFFICE_EXTENSIONS = {
        '.doc', '.docx', '.docm', '.dot', '.dotx', '.dotm',  # Word
        '.xls', '.xlsx', '.xlsm', '.xlsb', '.xlt', '.xltx', '.xlw',  # Excel
        '.ppt', '.pptx', '.pptm', '.pps', '.ppsx', '.pot', '.potx',  # PowerPoint
        '.odt', '.ods', '.odp', '.odg', '.odf',  # OpenOffice/LibreOffice
        '.rtf', '.txt', '.csv',  # Text formats
        '.pdf',  # PDF (already in PDF format but can be processed)
    }
    
    IMAGE_EXTENSIONS = {
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp', '.svg'
    }
    
    HTML_EXTENSIONS = {
        '.html', '.htm'
    }
    
    # Use LibreOffice endpoint for office documents and images
    if (mime_type and 'office' in mime_type) or \
       (mime_type and 'opendocument' in mime_type) or \
       (mime_type and mime_type.startswith('image/')) or \
       file_ext in OFFICE_EXTENSIONS or \
       file_ext in IMAGE_EXTENSIONS:
        endpoint = f"{gotenberg_url}/forms/libreoffice/convert"
        files = {'files': (os.path.basename(file_path), open(file_path, 'rb'))}
        
        # Add some quality settings for better PDF output
        form_data = {
            'landscape': 'false',
            'exportBookmarks': 'true',
            'exportNotes': 'false',
            'losslessImageCompression': 'true',  # Use lossless compression for images
            'pdfa': 'PDF/A-2b',  # Produce PDF/A-2b compatible output
        }
    
    # Use Chromium endpoint for HTML documents
    elif (mime_type and mime_type == 'text/html') or file_ext in HTML_EXTENSIONS:
        endpoint = f"{gotenberg_url}/forms/chromium/convert/html"
        # Gotenberg requires the form field to be exactly 'index.html'
        # The content filename doesn't matter, just the form field key
        files = {'index.html': ('index.html', open(file_path, 'rb'))}
        
        # Add options for better HTML to PDF conversion
        form_data = {
            'paperWidth': '8.27',  # A4 width in inches
            'paperHeight': '11.7',  # A4 height in inches
            'marginTop': '0.4',
            'marginBottom': '0.4',
            'marginLeft': '0.4',
            'marginRight': '0.4',
            'printBackground': 'true',
            'preferCssPageSize': 'false',
            'waitDelay': '2s',  # Wait for JavaScript to execute
        }
    
    # Use Markdown route for markdown files
    elif (mime_type and mime_type in ['text/markdown', 'text/x-markdown']) or file_ext in ['.md', '.markdown']:
        # For Markdown, we need both the markdown file and an HTML wrapper
        endpoint = f"{gotenberg_url}/forms/chromium/convert/markdown"
        
        # Create a simple HTML wrapper for the markdown
        # IMPORTANT: The filename in the template must match the key used in the files dictionary
        markdown_filename = os.path.basename(file_path)
        html_wrapper = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Converted Markdown</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            margin: 2em;
            max-width: 50em;
        }}
    </style>
</head>
<body>
    {{{{ toHTML "{markdown_filename}" }}}}
</body>
</html>"""
        
        # Create a temporary HTML wrapper file
        wrapper_path = os.path.join(os.path.dirname(file_path), "md_wrapper.html")
        with open(wrapper_path, 'w') as f:
            f.write(html_wrapper)
        
        try:
            files = {
                'index.html': ('index.html', open(wrapper_path, 'rb')),
                markdown_filename: (markdown_filename, open(file_path, 'rb'))
            }
            
            form_data = {
                'paperWidth': '8.27',  # A4 width in inches
                'paperHeight': '11.7',  # A4 height in inches
                'marginTop': '0.4',
                'marginBottom': '0.4',
                'marginLeft': '0.4',
                'marginRight': '0.4',
            }
        finally:
            # Clean up the temporary wrapper file after preparing the request
            if os.path.exists(wrapper_path):
                os.remove(wrapper_path)
    
    # Fallback to LibreOffice for everything else
    else:
        endpoint = f"{gotenberg_url}/forms/libreoffice/convert"
        files = {'files': (os.path.basename(file_path), open(file_path, 'rb'))}
        logger.warning(f"Using fallback conversion for unknown type: {mime_type} / {file_ext}")

    if not endpoint:
        logger.error(f"Could not determine Gotenberg endpoint for file type: {mime_type}")
        return None

    try:
        logger.info(f"Converting {file_path} using endpoint: {endpoint}")
        
        # Send the conversion request to Gotenberg
        response = requests.post(endpoint, files=files, data=form_data)
        
        if response.status_code == 200:
            # Save the converted PDF
            converted_file_path = os.path.splitext(file_path)[0] + ".pdf"
            with open(converted_file_path, "wb") as out_file:
                out_file.write(response.content)
            
            logger.info(f"Converted file saved as PDF: {converted_file_path}")
            
            # Enqueue the PDF for further processing
            process_document.delay(converted_file_path)
            
            return converted_file_path
        else:
            logger.error(
                f"Conversion failed for {file_path}. "
                f"Status code: {response.status_code}, "
                f"Response: {response.text[:500]}..."
            )
            return None
    except Exception as e:
        logger.exception(f"Error converting {file_path} to PDF: {e}")
        return None
