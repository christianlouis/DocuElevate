#!/bin/bash
pytest tests/ -k "not test_e2e_full_stack and not test_upload_tasks and not test_slow" -m "not slow" -n 4
