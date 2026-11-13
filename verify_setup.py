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
    import services.yookassa
    import services.payment_service
    import services.referral
    import services.yookassa_webhook
    import keyboards.inline
    import keyboards.reply
    import keyboards.admin
    import states.generation
    import states.admin
    import handlers.common
    import handlers.generation
    import handlers.payments
    import handlers.admin
    import services.admin_alerts
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
    assert user["gift_balance"] == config.settings.initial_user_credits
    assert user["paid_balance"] == 0
    assert user["total_balance"] == config.settings.initial_user_credits

    # Test balance operations (paid vs gift, deduction prioritization, refund)
    await test_db_instance.add_paid_balance(12345, 10)
    u_after_paid = await test_db_instance.get_user(12345)
    assert u_after_paid["paid_balance"] == 10
    assert u_after_paid["gift_balance"] == config.settings.initial_user_credits

    # Consume (should consume from gift first)
    consumed_type = await test_db_instance.consume_generation_credit(12345, cost=1)
    assert consumed_type == "gift"

    # Refund
    await test_db_instance.refund_generation_credit(12345, balance_type=consumed_type, cost=1)
    u_after_refund = await test_db_instance.get_user(12345)
    assert u_after_refund["gift_balance"] == config.settings.initial_user_credits

    # Referral fractional balance & auto-transfer test
    await test_db_instance.get_or_create_user(88888, "ref_tester", "Ref")
    r1 = await test_db_instance.add_referral_reward(88888, 0.1)
    assert r1["earned"] == 0.1
    assert r1["transferred"] == 0
    assert r1["referral_balance"] == 0.1

    r2 = await test_db_instance.add_referral_reward(88888, 0.9)
    assert r2["earned"] == 0.9
    assert r2["transferred"] == 1
    assert r2["referral_balance"] == 0.0

    r3 = await test_db_instance.add_referral_reward(88888, 2.45)
    assert r3["transferred"] == 2
    assert r3["referral_balance"] == 0.45
    print("[OK] DB: Referral fractional piggy bank & auto-transfer check passed.")

    print("[OK] DB: Split balance, consume and refund checks passed.")

    # Record generation
    await test_db_instance.record_generation(
        user_id=12345,
        task_id="test-task-1",
        prompt="lofi chill beat",
        artist="MACAN",
        genres="Рок, Электроника",
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

    # Payments check
    await test_db_instance.create_payment_record(
        payment_id="pay-12345",
        user_id=12345,
        amount=249.0,
        credits=15,
    )
    p = await test_db_instance.get_payment_record("pay-12345")
    assert p is not None
    assert p["status"] == "pending"
    assert p["credits"] == 15

    # Mark succeeded
    rec = await test_db_instance.mark_payment_succeeded("pay-12345")
    assert rec is not None
    assert rec["status"] == "succeeded"

    # Idempotency check: second time should return None
    rec_second = await test_db_instance.mark_payment_succeeded("pay-12345")
    assert rec_second is None
    print("[OK] DB: Payment creation, status update and idempotency check passed.")

    # Check pending list
    await test_db_instance.create_payment_record(
        payment_id="pay-pending-1",
        user_id=12345,
        amount=99.0,
        credits=5,
    )
    pending_list = await test_db_instance.get_pending_payments(limit=10)
    assert len(pending_list) >= 1
    assert any(x["payment_id"] == "pay-pending-1" for x in pending_list)
    print("[OK] DB: Pending payments fetch check passed.")

    # Anti-spam checks: user pending count & stale cleanup
    p_count = await test_db_instance.get_user_pending_count(12345, max_age_minutes=15)
    assert p_count >= 1
    cleaned = await test_db_instance.cleanup_stale_payments(max_age_hours=0)  # clean all older than 0 hours
    assert cleaned >= 1
    p_count_after = await test_db_instance.get_user_pending_count(12345, max_age_minutes=15)
    assert p_count_after == 0
    print("[OK] DB: Anti-spam pending count and stale cleanup passed.")

    # Admin DB operations: tariffs, user_ids, stats, add_gift_balance
    all_users = await test_db_instance.get_all_user_ids()
    assert 12345 in all_users
    print("[OK] DB: get_all_user_ids check passed.")

    tariffs = await test_db_instance.get_all_tariffs()
    assert len(tariffs) >= 4
    pack_mini = await test_db_instance.get_tariff("pack_5")
    assert pack_mini is not None
    original_price = pack_mini["price"]

    # Update price
    await test_db_instance.update_tariff_price("pack_5", 99.0)
    updated_tariff = await test_db_instance.get_tariff("pack_5")
    assert updated_tariff["price"] == 99.0
    # Revert price
    await test_db_instance.update_tariff_price("pack_5", original_price)
    print("[OK] DB: Tariffs dynamic price update check passed.")

    # Admin gift credits addition
    new_gift_total = await test_db_instance.add_gift_balance(12345, 25)
    u_after_admin_gift = await test_db_instance.get_user(12345)
    assert u_after_admin_gift["gift_balance"] == config.settings.initial_user_credits + 25
    print("[OK] DB: Admin gift credits grant check passed.")

    stats = await test_db_instance.get_system_stats()
    assert stats["users_count"] >= 1
    assert stats["payments_count"] >= 1
    print("[OK] DB: Admin system stats check passed.")

    # Dynamic artists checks
    popular = await test_db_instance.get_popular_artists()
    assert len(popular) == 0
    extended = await test_db_instance.get_extended_artists()
    assert len(extended) == 77

    # Swap order check on extended list: swap #1 and #2
    e1_orig = extended[0]["id"]
    e2_orig = extended[1]["id"]
    await test_db_instance.swap_artist_order(e2_orig, direction="up")
    extended_after_swap = await test_db_instance.get_extended_artists()
    assert extended_after_swap[0]["id"] == e2_orig
    assert extended_after_swap[1]["id"] == e1_orig
    # Swap back
    await test_db_instance.swap_artist_order(e2_orig, direction="down")
    extended_reverted = await test_db_instance.get_extended_artists()
    assert extended_reverted[0]["id"] == e1_orig

    # Add artist check
    new_id = await test_db_instance.add_artist(
        name="Drake",
        style="трэп, R&B, автотюн, ночной вайб",
        aliases=["дрейк", "drake", "champagne papi"],
        is_popular=True,
    )
    assert new_id == "drake"
    drake = await test_db_instance.get_artist_by_id(new_id)
    assert drake is not None
    assert drake["name"] == "Drake"
    assert "drake" in drake["aliases"]
    assert drake["is_popular"] == 1
    assert (await test_db_instance.find_artist_by_name("champagne papi")) is not None

    # Update artist style & delete
    await test_db_instance.update_artist(new_id, style="новый стиль")
    assert (await test_db_instance.get_artist_by_id(new_id))["style"] == "новый стиль"
    await test_db_instance.delete_artist(new_id)
    assert await test_db_instance.get_artist_by_id(new_id) is None
    print("[OK] DB: Dynamic artists CRUD and order swap checks passed.")

    # Subscription check settings in DB
    sub_init = await test_db_instance.is_subscription_check_enabled()
    assert sub_init is False
    await test_db_instance.set_subscription_check_enabled(True)
    assert (await test_db_instance.is_subscription_check_enabled()) is True
    await test_db_instance.set_required_channel("@trivela_channel")
    await test_db_instance.set_setting("required_channel_url", "https://t.me/trivela_channel")
    ch_info = await test_db_instance.get_required_channel()
    assert ch_info["channel"] == "@trivela_channel"
    assert ch_info["url"] == "https://t.me/trivela_channel"
    await test_db_instance.set_subscription_check_enabled(False)
    assert (await test_db_instance.is_subscription_check_enabled()) is False
    print("[OK] DB: Subscription check settings passed.")

    if os.path.exists(test_db_file):
        os.remove(test_db_file)
    print("[OK] DB tests completed successfully.")


async def test_treblo_client():
    from services.treblo import TrebloClient
    client = TrebloClient(api_key="dummy_key")
    assert client.base_url == "https://api.treblo.com/v1"
    print("[OK] Treblo client initialized successfully.")


async def test_keyboards_and_catalogs():
    from keyboards.inline import (
        POPULAR_ARTISTS,
        GENRES_CATALOG,
        get_artists_keyboard,
        get_artist_by_id,
        get_genres_keyboard,
        get_genre_by_id,
        get_prompt_input_keyboard,
        get_mode_selection_keyboard,
        get_lyrics_input_keyboard,
    )
    from keyboards.inline import find_artist_by_name
    from keyboards.reply import get_main_reply_keyboard
    assert len(POPULAR_ARTISTS) == 24
    assert len(GENRES_CATALOG) >= 10
    kb = get_artists_keyboard()
    assert kb is not None
    genres_kb = get_genres_keyboard(["rock", "electronic"])
    assert genres_kb is not None
    assert get_mode_selection_keyboard() is not None
    reply_kb = get_main_reply_keyboard()
    assert reply_kb is not None
    assert reply_kb.is_persistent is True
    skrip = get_artist_by_id("skrip")
    assert skrip is not None
    assert find_artist_by_name("моргенштерн") is not None
    assert find_artist_by_name("macan") is not None
    rock = get_genre_by_id("rock")
    assert rock is not None
    assert rock["name"] == "Рок"
    print("[OK] Keyboards & catalogs (artists & genres) check passed.")


async def test_yookassa_client():
    from services.yookassa import YooKassaClient
    client = YooKassaClient(shop_id="test_shop", secret_key="test_key")
    assert client.is_configured is True
    assert client.base_url == "https://api.yookassa.ru/v3"
    print("[OK] YooKassa client initialized successfully.")


async def test_referral_tiers():
    from services.referral import (
        get_referral_tier,
        calculate_referral_reward,
        format_referral_tiers_table,
        REFERRAL_TIERS,
    )
    assert len(REFERRAL_TIERS) == 10
    assert REFERRAL_TIERS[0]["percent"] == 2
    assert REFERRAL_TIERS[-1]["percent"] == 20

    t0 = get_referral_tier(0)
    assert t0["level"] == 1
    assert t0["percent"] == 2
    assert t0["needed_for_next"] == 1

    t4 = get_referral_tier(5)
    assert t4["level"] == 4  # >= 4 and < 8
    assert t4["percent"] == 8
    assert t4["needed_for_next"] == 3  # 8 - 5

    # Max level
    t_max = get_referral_tier(300)
    assert t_max["level"] == 10
    assert t_max["percent"] == 20
    assert t_max["next_tier"] is None

    # Calculate fractional reward: 15 credits bought at 10%
    reward = calculate_referral_reward(15, 10)
    assert reward == 1.5
    # At 2% of 5 credits: 0.1
    assert calculate_referral_reward(5, 2) == 0.1

    table = format_referral_tiers_table(current_level=1)
    assert "Ур. 1" in table and "2%" in table
    print("[OK] Referral tiers (2%-20% geometric progression) checks passed.")


async def test_promo_codes():
    import aiosqlite
    from database.db import Database, get_msk_now, MSK_TZ
    from datetime import datetime, timedelta
    from keyboards.admin import (
        get_admin_promos_menu_keyboard,
        get_admin_promo_type_keyboard,
        get_admin_promo_discount_mode_keyboard,
        get_admin_promo_duration_keyboard,
        get_admin_promo_confirm_keyboard,
        get_admin_promos_list_keyboard,
        get_admin_promo_card_keyboard,
    )
    from keyboards.inline import (
        get_profile_keyboard,
        get_tariffs_keyboard,
        get_promo_replace_keyboard,
        get_promo_input_cancel_keyboard,
    )

    test_db_file = "test_promo.db"
    if os.path.exists(test_db_file):
        os.remove(test_db_file)

    tdb = Database(db_path=test_db_file)
    await tdb.init()

    # Create test users
    u1 = await tdb.get_or_create_user(1001, "u1", "User1")
    u2 = await tdb.get_or_create_user(1002, "u2", "User2")
    u3 = await tdb.get_or_create_user(1003, "u3", "User3")

    now = get_msk_now()
    exp_global = now + timedelta(days=7)

    # 1. Exact case-sensitivity test
    await tdb.create_promo_code(
        code="SUPER20",
        promo_type="discount_fixed",
        reward_data={"discount_mode": "fixed", "percent": 20},
        max_activations=2,
        expires_at=exp_global,
    )

    found_upper = await tdb.get_promo_code_by_code("SUPER20")
    assert found_upper is not None
    assert found_upper["code"] == "SUPER20"

    found_lower = await tdb.get_promo_code_by_code("super20")
    assert found_lower is None, "Promo code MUST be case-sensitive (COLLATE BINARY)"
    print("[OK] Promo: Strict case-sensitivity check passed.")

    # 2. Credits promo code
    await tdb.create_promo_code(
        code="FREE5",
        promo_type="credits",
        reward_data={"credits": 5},
        max_activations=5,
        expires_at=exp_global,
    )
    p_credits = await tdb.get_promo_code_by_code("FREE5")
    success, status, data = await tdb.activate_promo_code_for_user(1001, p_credits)
    assert success is True
    assert status == "credits_success"
    assert data["credits"] == 5
    u1_updated = await tdb.get_user(1001)
    assert u1_updated["gift_balance"] == u1["gift_balance"] + 5

    # Check that same user cannot activate again
    s_repeat, st_repeat, _ = await tdb.activate_promo_code_for_user(1001, p_credits)
    assert s_repeat is False
    assert st_repeat == "already_used"
    print("[OK] Promo: Bonus credits promo activation and duplicate prevention passed.")

    # 3. Fair 24-hour window test
    success_disc, _, data_disc = await tdb.activate_promo_code_for_user(1001, found_upper)
    assert success_disc is True
    act_exp = datetime.strptime(data_disc["expires_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=MSK_TZ)
    # Expiration must be approximately now + 24 hours
    diff_hours = (act_exp - now).total_seconds() / 3600
    assert 23.9 <= diff_hours <= 24.1, f"Expected 24h window, got {diff_hours} hours"

    active_disc = await tdb.get_user_active_discount(1001)
    assert active_disc is not None
    assert active_disc["discount_data"]["percent"] == 20
    assert "ч." in active_disc["remaining_time_str"] or "мин." in active_disc["remaining_time_str"]
    print("[OK] Promo: Fair 24-hour window calculation passed.")

    # 4. Activation limit atomicity (max_activations=2)
    s2, _, _ = await tdb.activate_promo_code_for_user(1002, found_upper)
    assert s2 is True
    s3, st3, _ = await tdb.activate_promo_code_for_user(1003, found_upper)
    assert s3 is False
    assert st3 == "limit_reached"
    print("[OK] Promo: Max activations limit check passed.")

    # 5. Non-stacking & Replacement test
    await tdb.create_promo_code(
        code="BIG50",
        promo_type="discount_fixed",
        reward_data={"discount_mode": "fixed", "percent": 50},
        max_activations=10,
        expires_at=exp_global,
    )
    p_big = await tdb.get_promo_code_by_code("BIG50")

    # User 1 already has active discount (SUPER20). If user attempts regular activate:
    s_conflict, st_conflict, _ = await tdb.activate_promo_code_for_user(1001, p_big)
    assert s_conflict is False
    assert st_conflict == "already_has_discount"

    # User confirms replacement:
    s_rep, _, data_rep = await tdb.replace_active_discount_with_promo(1001, p_big)
    assert s_rep is True
    current_disc = await tdb.get_user_active_discount(1001)
    assert current_disc is not None
    assert current_disc["discount_data"]["percent"] == 50
    print("[OK] Promo: Non-stacking & replacement confirmation check passed.")

    # 6. Payment price calculation & discount consumption
    # Suppose tariff is 299 RUB with 50% discount -> round(299 * 0.5) = 150 RUB
    orig_price = 299.0
    final_price = round(orig_price * (1 - 50 / 100))
    assert final_price == 150

    await tdb.create_payment_record(
        payment_id="pay_promo_1",
        user_id=1001,
        amount=final_price,
        credits=45,
        promo_activation_id=current_disc["id"],
    )
    # Stale pending payments cancellation check
    await tdb.create_payment_record(
        payment_id="pay_promo_old",
        user_id=1001,
        amount=299.0,
        credits=45,
    )
    await tdb.cancel_user_pending_payments(1001)
    p_old = await tdb.get_payment_record("pay_promo_old")
    assert p_old["status"] == "canceled"
    print("[OK] Promo: Pending invoices cancellation check passed.")

    # Payment succeeded: consume promo
    await tdb.mark_user_promo_used(current_disc["id"], "pay_promo_1")
    used_disc = await tdb.get_user_active_discount(1001)
    assert used_disc is None, "Discount must be consumed after successful payment"
    print("[OK] Promo: Discount consumption on payment check passed.")

    # 7. Background push reminder check (<= 2 hours before expiration)
    # Create an activation expiring in 1 hour
    exp_1h = (now + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(test_db_file) as c:
        await c.execute(
            """
            INSERT INTO user_promo_activations (user_id, promo_code_id, promo_type, discount_data, expires_at, is_used, reminder_sent)
            VALUES (1002, 1, 'discount_fixed', '{"discount_mode": "fixed", "percent": 20}', ?, 0, 0)
            """,
            (exp_1h,),
        )
        await c.commit()

    pending_reminders = await tdb.get_pending_discount_reminders()
    assert len(pending_reminders) == 1
    assert pending_reminders[0]["user_id"] == 1002

    await tdb.mark_discount_reminder_sent(pending_reminders[0]["id"])
    reminders_after = await tdb.get_pending_discount_reminders()
    assert len(reminders_after) == 0
    print("[OK] Promo: 2-hour expiring reminder query & mark check passed.")

    # 8. Admin promo list, card and deactivation
    all_promos = await tdb.get_all_promo_codes()
    assert len(all_promos) >= 3
    # Deactivate BIG50
    await tdb.deactivate_promo_code(p_big["id"])
    p_big_deact = await tdb.get_promo_code_by_id(p_big["id"])
    assert p_big_deact["is_active"] == 0
    print("[OK] Promo: Admin listing and deactivation check passed.")

    # 9. Keyboards compilation check
    assert get_admin_promos_menu_keyboard() is not None
    assert get_admin_promo_type_keyboard() is not None
    assert get_admin_promo_discount_mode_keyboard() is not None
    assert get_admin_promo_duration_keyboard() is not None
    assert get_admin_promo_confirm_keyboard() is not None
    assert get_admin_promos_list_keyboard(all_promos, 1, 1) is not None
    assert get_admin_promo_card_keyboard(1, True, 1) is not None
    assert get_profile_keyboard(has_discount=True) is not None
    assert get_promo_replace_keyboard("CODE") is not None
    assert get_promo_input_cancel_keyboard() is not None
    kb_disc = get_tariffs_keyboard([{"id": "p1", "title": "P1", "price": 100, "credits": 10, "emoji": "👑", "discount_percent": 20}])
    assert kb_disc is not None
    btn_text = kb_disc.inline_keyboard[0][0].text
    assert "-20%" in btn_text and "₽ за трек" in btn_text, f"Unexpected button text: {btn_text}"
    print("[OK] Promo: Tariff button shows both discount percent and price per track.")
    print("[OK] Promo: All user & admin promo keyboards compiled successfully.")

    if os.path.exists(test_db_file):
        os.remove(test_db_file)


async def test_admin_module():
    from keyboards.admin import (
        get_admin_main_keyboard,
        get_admin_sub_keyboard,
        get_admin_broadcast_confirm_keyboard,
        get_admin_tariffs_keyboard,
        get_admin_cancel_keyboard,
    )
    from keyboards.inline import get_subscription_gate_keyboard
    from handlers.admin import is_admin
    from config import settings

    # Keyboard generators
    assert get_admin_main_keyboard(sub_enabled=True) is not None
    assert get_admin_main_keyboard(sub_enabled=False) is not None
    assert get_admin_sub_keyboard(sub_enabled=True) is not None
    assert get_subscription_gate_keyboard("https://t.me/test") is not None
    assert get_admin_broadcast_confirm_keyboard() is not None
    dummy_tariffs = [
        {"id": "pack_5", "title": "5 треков", "price": 10.0, "credits": 5, "emoji": "🌱"}
    ]
    assert get_admin_tariffs_keyboard(dummy_tariffs) is not None
    assert get_admin_cancel_keyboard() is not None

    # is_admin check logic
    if settings.admin_ids_list:
        first_admin = settings.admin_ids_list[0]
        assert is_admin(first_admin) is True
    assert is_admin(-999999999) is False

    # Check router order in main
    from main import setup_dispatcher
    test_dp = setup_dispatcher()
    routers = test_dp.sub_routers
    assert len(routers) >= 4
    # Ensure admin_router is first
    from handlers.admin import admin_router
    assert routers[0] == admin_router
    print("[OK] Admin keyboards, authorization and router priority check passed.")


async def run_all():
    await test_db()
    await test_promo_codes()
    await test_treblo_client()
    await test_yookassa_client()
    await test_referral_tiers()
    await test_keyboards_and_catalogs()
    await test_admin_module()
    print("\nALL LOCAL COMPONENT CHECKS PASSED!")


if __name__ == "__main__":
    asyncio.run(run_all())
