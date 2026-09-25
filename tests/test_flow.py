from bot.keyboards import BTN_DM, BTN_PLAN, BTN_POST, BTN_PROFILE, BTN_REELS, BTN_TARIFF
from tests.conftest import Harness


async def onboard(h: Harness) -> None:
    await h.send("/start")
    assert "Какая у тебя ниша" in h.bot.all_texts()
    await h.click("niche:0")
    assert "Как ты общаешься" in h.bot.all_texts()
    await h.click("tone:friend")
    assert "Какие услуги" in h.bot.all_texts()
    await h.send("наращивание, френч, педикюр")
    assert "Профиль сохранён" in h.bot.all_texts()


async def test_onboarding_and_profile(harness: Harness) -> None:
    await onboard(harness)
    await harness.send(BTN_PROFILE)
    text = harness.bot.all_texts()
    assert "Маникюр / педикюр" in text
    assert "Подружка" in text
    assert "наращивание, френч, педикюр" in text


async def test_generation_flows_and_paywall(harness: Harness) -> None:
    await onboard(harness)

    await harness.send(BTN_POST)
    await harness.send("сделала френч, клиентка грызла ногти, нарастили")
    assert "Осталось бесплатных генераций: 2 из 3" in harness.bot.all_texts()

    await harness.send(BTN_PLAN)
    await harness.click("plan:7")
    assert "Осталось бесплатных генераций: 1 из 3" in harness.bot.all_texts()

    await harness.send(BTN_REELS)
    await harness.click("reels:random")
    assert "Осталось бесплатных генераций: 0 из 3" in harness.bot.all_texts()

    harness.bot.calls.clear()
    await harness.send(BTN_DM)
    await harness.send("А почему так дорого?")
    text = harness.bot.all_texts()
    assert "Бесплатные генерации закончились" in text
    assert "990" in text and "2490" in text


async def test_free_text_is_post_draft(harness: Harness) -> None:
    await onboard(harness)
    harness.bot.calls.clear()
    await harness.send("сегодня сделала педикюр с покрытием, клиентка довольна")
    text = harness.bot.all_texts()
    assert "Режим демо" in text
    assert "Осталось бесплатных генераций: 2 из 3" in text


async def test_not_onboarded_user_is_redirected(harness: Harness) -> None:
    await harness.send(BTN_POST)
    await harness.send("какой-то текст")
    assert "Какая у тебя ниша" in harness.bot.all_texts()


async def test_admin_grant_and_tariff(harness: Harness) -> None:
    await onboard(harness)
    admin = Harness(harness.bot, harness.dp, user_id=999)
    await admin.send("/grant 1 30")
    assert "Премиум для 1 активен" in harness.bot.all_texts()

    harness.bot.calls.clear()
    await harness.send(BTN_TARIFF)
    assert "Подписка активна до" in harness.bot.all_texts()

    await admin.send("/stats")
    assert "Премиум: 1" in harness.bot.all_texts()


async def test_non_admin_cannot_grant(harness: Harness) -> None:
    await onboard(harness)
    harness.bot.calls.clear()
    await harness.send("/grant 1 30")
    assert "Премиум для" not in harness.bot.all_texts()
