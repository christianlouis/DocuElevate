import os
import pytest

os.environ['DATABASE_URL'] = 'sqlite:///test.db'
os.environ['REDIS_URL'] = 'redis://'
os.environ['OPENAI_API_KEY'] = 'test'
os.environ['WORKDIR'] = '/tmp'
os.environ['AZURE_AI_KEY'] = 'test'
os.environ['AZURE_REGION'] = 'test'
os.environ['AZURE_ENDPOINT'] = 'test'
os.environ['GOTENBERG_URL'] = 'test'
os.environ['AUTH_ENABLED'] = 'False'
os.environ['SESSION_SECRET'] = 'x' * 32

pytest.main(['tests/test_url_upload.py', '--cov=app/api/url_upload', '--cov-report=term-missing'])
