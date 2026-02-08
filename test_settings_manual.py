#!/usr/bin/env python3
"""
Manual test script to verify settings functionality
"""
import os
import sys
import tempfile
from pathlib import Path

# Set up minimal environment for testing
os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.gettempdir()}/test_settings.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("OPENAI_API_KEY", "test_key")
os.environ.setdefault("AZURE_AI_KEY", "test_key")
os.environ.setdefault("AZURE_REGION", "test")
os.environ.setdefault("AZURE_ENDPOINT", "https://test.example.com")
os.environ.setdefault("GOTENBERG_URL", "http://localhost:3000")
os.environ.setdefault("WORKDIR", tempfile.gettempdir())
os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault("SESSION_SECRET", "a" * 32)

from app.config import settings
from app.database import Base, engine, SessionLocal, init_db
from app.models import ApplicationSettings
from app.utils.settings_service import (
    get_setting_from_db,
    save_setting_to_db,
    get_all_settings_from_db,
    delete_setting_from_db,
    get_setting_metadata,
    get_settings_by_category,
    SETTING_METADATA,
)
from app.utils.config_loader import load_settings_from_db, convert_setting_value

def test_database_model():
    """Test that ApplicationSettings model is in the database"""
    print("=" * 60)
    print("Testing Database Model")
    print("=" * 60)
    
    # Initialize database
    init_db()
    
    # Check if ApplicationSettings table exists
    from sqlalchemy import inspect
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    print(f"✓ Database tables: {tables}")
    assert "application_settings" in tables, "ApplicationSettings table not found!"
    print("✓ ApplicationSettings table exists")
    
    # Check columns
    columns = [col['name'] for col in inspector.get_columns('application_settings')]
    print(f"✓ Columns: {columns}")
    assert "key" in columns
    assert "value" in columns
    print("✓ All expected columns present")
    print()

def test_settings_service():
    """Test settings service functions"""
    print("=" * 60)
    print("Testing Settings Service")
    print("=" * 60)
    
    db = SessionLocal()
    try:
        # Test save and retrieve
        print("Testing save_setting_to_db...")
        result = save_setting_to_db(db, "test_key", "test_value")
        assert result is True
        print("✓ Setting saved")
        
        value = get_setting_from_db(db, "test_key")
        assert value == "test_value"
        print(f"✓ Setting retrieved: {value}")
        
        # Test update
        print("Testing update...")
        result = save_setting_to_db(db, "test_key", "updated_value")
        assert result is True
        value = get_setting_from_db(db, "test_key")
        assert value == "updated_value"
        print(f"✓ Setting updated: {value}")
        
        # Test get all
        print("Testing get_all_settings_from_db...")
        save_setting_to_db(db, "key1", "value1")
        save_setting_to_db(db, "key2", "value2")
        all_settings = get_all_settings_from_db(db)
        print(f"✓ Retrieved {len(all_settings)} settings")
        
        # Test delete
        print("Testing delete_setting_from_db...")
        result = delete_setting_from_db(db, "test_key")
        assert result is True
        value = get_setting_from_db(db, "test_key")
        assert value is None
        print("✓ Setting deleted")
        
        print()
    finally:
        db.close()

def test_settings_metadata():
    """Test settings metadata"""
    print("=" * 60)
    print("Testing Settings Metadata")
    print("=" * 60)
    
    print(f"Total settings in metadata: {len(SETTING_METADATA)}")
    
    # Test get metadata
    metadata = get_setting_metadata("database_url")
    print(f"✓ database_url metadata: {metadata}")
    assert metadata["category"] == "Core"
    assert metadata["required"] is True
    
    # Test categories
    categories = get_settings_by_category()
    print(f"✓ Categories: {list(categories.keys())}")
    print(f"  - Core has {len(categories.get('Core', []))} settings")
    print(f"  - Authentication has {len(categories.get('Authentication', []))} settings")
    print(f"  - AI Services has {len(categories.get('AI Services', []))} settings")
    print()

def test_settings_precedence():
    """Test that database settings override environment variables"""
    print("=" * 60)
    print("Testing Settings Precedence (DB > ENV > Default)")
    print("=" * 60)
    
    db = SessionLocal()
    try:
        # Save a setting to database
        print("Saving 'debug' to database as 'true'...")
        save_setting_to_db(db, "debug", "true")
        
        # Load settings from database
        print("Loading settings from database...")
        load_settings_from_db(settings, db)
        
        # Check that database value is used
        print(f"✓ settings.debug = {settings.debug}")
        assert settings.debug is True, f"Expected True, got {settings.debug}"
        print("✓ Database setting took precedence")
        
        # Clean up
        delete_setting_from_db(db, "debug")
        print()
    finally:
        db.close()

def test_type_conversion():
    """Test type conversion for different setting types"""
    print("=" * 60)
    print("Testing Type Conversion")
    print("=" * 60)
    
    # Test boolean conversion
    assert convert_setting_value("true", bool) is True
    assert convert_setting_value("false", bool) is False
    assert convert_setting_value("1", bool) is True
    assert convert_setting_value("0", bool) is False
    print("✓ Boolean conversion works")
    
    # Test integer conversion
    assert convert_setting_value("42", int) == 42
    assert convert_setting_value("0", int) == 0
    print("✓ Integer conversion works")
    
    # Test string conversion
    assert convert_setting_value("hello", str) == "hello"
    print("✓ String conversion works")
    
    print()

def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("SETTINGS FUNCTIONALITY TEST SUITE")
    print("=" * 60 + "\n")
    
    try:
        test_database_model()
        test_settings_service()
        test_settings_metadata()
        test_type_conversion()
        test_settings_precedence()
        
        print("=" * 60)
        print("ALL TESTS PASSED! ✓")
        print("=" * 60)
        return 0
    except Exception as e:
        print("\n" + "=" * 60)
        print(f"TEST FAILED: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
