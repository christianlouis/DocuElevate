"""
Module for masking sensitive information in configuration values
"""


def mask_sensitive_value(value):
    """
    Masks sensitive values like API keys in logs and output
    """
    # Return masked value for sensitive data
    if value and isinstance(value, str) and len(value) > 8:
        return value[:4] + "*" * (len(value) - 4)
    return value
