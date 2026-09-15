import sqlite3
import tempfile
from pathlib import Path

import bot as core
import fantzo_growth as growth
import fantzo_personalization as p


with tempfile.TemporaryDirectory() as tmp:
    db_path = Path(tmp) / "fantzo_personalization_test.db"
    core.DB_PATH = str(db_path)

    core.init_db()
    growth.ensure_tables()

    user_id = 123456
    assert p.get_favourites(user_id) == []

    growth.add_favourite(user_id, "cricket:42:India")
    growth.add_favourite(user_id, "football:99:Arsenal")

    favs = p.get_favourites(user_id)
    assert len(favs) == 2, favs
    assert {x["team_name"] for x in favs} == {"India", "Arsenal"}

    keyboard = p.personalized_home_keyboard(user_id)
    callbacks = [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert "my_fantzo" in callbacks
    assert "myteam:cricket:42" in callbacks
    assert "myteam:football:99" in callbacks
    assert "live_now" in callbacks

    text = p.personalized_home_text(user_id, "en")
    assert "Your teams" in text
    assert "India" in text and "Arsenal" in text

    assert p.remove_favourite(user_id, "cricket", "42") is True
    favs_after = p.get_favourites(user_id)
    assert len(favs_after) == 1
    assert favs_after[0]["team_name"] == "Arsenal"

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM growth_events WHERE event='unfavourite_team'"
        ).fetchone()
        assert row[0] == 1

print("Fantzo personalization self-test passed")
