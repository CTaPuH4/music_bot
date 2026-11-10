import asyncio
import os
import sys

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Test imports
try:
    import config
    import database.db
    import services.treblo
    import keyboards.inline
    import states.generation
    import handlers.common
    import handlers.generation
    import main
    print("[OK] All imports passed successfully.")
except Exception as e:
    print(f"[FAIL] Import failed: {e}")
    sys.exit(1)


async def test_db():
    from database.db import Database
    test_db_file = "test_test.db"
    if os.path.exists(test_db_file):
        os.remove(test_db_file)

    test_db_instance = Database(db_path=test_db_file)
    await test_db_instance.init()

    # Create user
    user = await test_db_instance.get_or_create_user(
        user_id=12345,
        username="testuser",
        first_name="Test",
        referred_by=None,
    )
    assert user["user_id"] == 12345
    assert user["balance"] == config.settings.initial_user_credits
    print("[OK] DB: User creation and initial balance check passed.")

    # Record generation
    await test_db_instance.record_generation(
        user_id=12345,
        task_id="test-task-1",
        prompt="lofi chill beat",
        instrumental=True,
    )
    await test_db_instance.update_generation_status(
        task_id="test-task-1",
        status="SUCCESS",
        audio_url="https://example.com/audio.mp3",
        duration=120.0,
    )

    stats = await test_db_instance.get_user_stats(12345)
    assert stats["total_generations"] == 1
    assert stats["success_generations"] == 1
    print("[OK] DB: Record generation and stats check passed.")

    if os.path.exists(test_db_file):
        os.remove(test_db_file)
    print("[OK] DB tests completed successfully.")


async def test_treblo_client():
    from services.treblo import TrebloClient
    client = TrebloClient(api_key="dummy_key")
    assert client.base_url == "https://api.treblo.com/v1"
    print("[OK] Treblo client initialized successfully.")


async def test_artists():
    from keyboards.inline import POPULAR_ARTISTS, get_artists_keyboard, get_artist_by_id
    assert len(POPULAR_ARTISTS) == 10
    kb = get_artists_keyboard()
    assert kb is not None
    macan = get_artist_by_id("macan")
    assert macan is not None
    assert macan["name"] == "MACAN"
    print("[OK] Artists keyboard & mapping check passed.")


async def run_all():
    await test_db()
    await test_treblo_client()
    await test_artists()
    print("\nALL LOCAL COMPONENT CHECKS PASSED!")


if __name__ == "__main__":
    asyncio.run(run_all())
