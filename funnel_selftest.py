import bot_tracked as tracked
import fantzo_analytics as analytics
import fantzo_business as business
import fantzo_funnel as funnel

# Force public Live TV only inside this isolated process so the full intended
# home layout can be validated without touching Railway variables.
tracked.LIVE_TV_MODE = "public"
tracked.SKY_ADMIN_BASE_URL = "https://example.invalid"
tracked.SKY_ADMIN_TEST_TOKEN = "test"

funnel.install()

home = funnel.funnel_main_keyboard()
labels = [button.text for row in home.inline_keyboard for button in row]
assert labels[0] == "✨ OPEN FANTZO", labels
assert "📺 WATCH LIVE TV" in labels, labels
assert "🔴 LIVE SCORES" in labels, labels
assert "🏏 CRICKET" in labels and "⚽ FOOTBALL" in labels, labels
assert "📅 FIXTURES" in labels and "🔎 FIND TEAM" in labels, labels
assert not any("MY FANTZO" in label or "MY TEAMS" in label for label in labels), labels

# Context destinations must remain tracked while sending sports users to the
# relevant Fantzo section.
live_url = analytics.destination_url("selftest_live", "live")
register_url = analytics.destination_url("selftest_join", "register")
assert "/en/live?" in live_url, live_url
assert "/en/registration?" in register_url, register_url
assert "utm_content=selftest_live" in live_url, live_url

category, _, markup = business.classify_business_dm("hello")
assert category == "greeting"
business_labels = [button.text for row in markup.inline_keyboard for button in row]
assert business_labels == [
    "🎮 PLAY FANTZO",
    "📺 WATCH LIVE TV",
    "📢 SUBSCRIBE CHANNEL",
], business_labels

join_category, _, join_markup = business.classify_business_dm("register")
assert join_category == "join"
play_url = join_markup.inline_keyboard[0][0].url
assert "/en/registration?" in play_url or "dest=register" in play_url, play_url

sports_category, _, sports_markup = business.classify_business_dm("live cricket")
assert sports_category == "sports"
sports_play_url = sports_markup.inline_keyboard[0][0].url
assert "/en/live?" in sports_play_url or "dest=live" in sports_play_url, sports_play_url

print("Fantzo funnel self-test passed")
