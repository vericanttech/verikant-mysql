"""Compatibility settings loaded from the environment."""
import os


APP_PASSWORD = os.environ.get("SMTP_APP_PASSWORD", "")
