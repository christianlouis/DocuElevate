import time
import os
import sys
import asyncio

# Mock settings before app imports to bypass validation
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost:6379"
os.environ["OPENAI_API_KEY"] = "mock_key"
os.environ["WORKDIR"] = "/tmp/workdir"
os.environ["AZURE_AI_KEY"] = "mock"
os.environ["AZURE_REGION"] = "mock"
os.environ["AZURE_ENDPOINT"] = "http://mock"
os.environ["GOTENBERG_URL"] = "http://mock"
os.environ["SESSION_SECRET"] = "mock_secret_mock_secret_mock_secret_mock_secret"

# Ensure app package is accessible
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import FileRecord
from app.api.duplicates import list_duplicate_groups

# Mocking Request object
class MockRequest:
    def __init__(self):
        self.session = {"user": {"username": "testuser"}}
        self.state = type('State', (), {'user': {"username": "testuser"}})()

    class MockURL:
        def include_query_params(self, **kwargs):
            return f"http://testserver/api/duplicates?page={kwargs.get('page')}"
    url = MockURL()

def setup_db():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    return db

def populate_data(db, num_groups, duplicates_per_group):
    for i in range(num_groups):
        filehash = f"hash_{i}"
        # Original
        original = FileRecord(
            filehash=filehash,
            local_filename=f"orig_{i}.txt",
            file_size=100,
            is_duplicate=False
        )
        db.add(original)
        # Duplicates
        for j in range(duplicates_per_group):
            dup = FileRecord(
                filehash=filehash,
                local_filename=f"dup_{i}_{j}.txt",
                file_size=100,
                is_duplicate=True
            )
            db.add(dup)
    db.commit()

async def run_benchmark(db):
    request = MockRequest()
    start_time = time.time()

    # Run the function we want to benchmark
    result = list_duplicate_groups(request=request, db=db, page=1, per_page=500)
    if asyncio.iscoroutine(result):
        result = await result

    end_time = time.time()
    return end_time - start_time, result

async def main():
    db = setup_db()
    # 500 groups, each with 20 duplicates = 10500 records total
    print("Populating data...")
    populate_data(db, 500, 20)
    print("Data populated. Running baseline benchmark...")

    # Warmup
    result = list_duplicate_groups(request=MockRequest(), db=db, page=1, per_page=500)
    if asyncio.iscoroutine(result):
        await result

    # Benchmark
    total_time = 0
    iterations = 10
    for _ in range(iterations):
        time_taken, _ = await run_benchmark(db)
        total_time += time_taken

    avg_time = total_time / iterations
    print(f"Average time over {iterations} iterations: {avg_time:.4f} seconds")

if __name__ == "__main__":
    asyncio.run(main())
