import bot_tracked as tracked
import fantzo_business as business
import fantzo_funnel as funnel

tracked.LIVE_TV_MODE = "public"
tracked.SKY_ADMIN_BASE_URL = "https://example.invalid"
tracked.SKY_ADMIN_TEST_TOKEN = "test"

home = funnel.funnel_main_keyboard()
buttons = [button for row in home.inline_keyboard for button in row]
labels = [button.text for button in buttons]
styles = {button.text: button.to_dict().get("style") for button in buttons}

assert labels[0] == "✨ OPEN FANTZO", labels
assert styles["✨ OPEN FANTZO"] == "success", styles
assert styles["📺 WATCH LIVE TV"] == "primary", styles
assert styles["🔴 LIVE SCORES"] == "primary", styles
assert styles["🏏 CRICKET"] == "primary", styles
assert styles["⚽ FOOTBALL"] == "primary", styles

_, _, markup = business.classify_business_dm("hello")
biz_buttons = [button for row in markup.inline_keyboard for button in row]
biz_styles = {button.text: button.to_dict().get("style") for button in biz_buttons}
assert biz_styles == {
    "🎮 PLAY FANTZO": "success",
    "📺 WATCH LIVE TV": "primary",
    "📢 SUBSCRIBE CHANNEL": "primary",
}, biz_styles

print("Fantzo Telegram button style self-test passed")
