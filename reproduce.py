import sys
from unittest.mock import MagicMock
from fastapi.templating import Jinja2Templates

import os
# We don't really need a real path, but let's mock it
os.makedirs("templates", exist_ok=True)
with open("templates/files.html", "w") as f:
    f.write("Hello")

templates = Jinja2Templates(directory="templates")
original_template_response = templates.TemplateResponse

def template_response_with_version(*args, **kwargs):
    if len(args) == 2 and isinstance(args[0], str) and isinstance(args[1], dict):
        context = args[1]
        request = context.get("request")
        if request is not None:
            # THIS IS MY FIX
            print("Running fix logic")
            return original_template_response(request=request, name=args[0], context=context, **kwargs)

    print("Running original fallback logic")
    return original_template_response(*args, **kwargs)

templates.TemplateResponse = template_response_with_version

req = MagicMock()
try:
    templates.TemplateResponse("files.html", {"request": req})
    print("SUCCESS")
except Exception as e:
    import traceback
    traceback.print_exc()
