import logging

import ibetin_liveline_v23_stable_feed as v23

logger = logging.getLogger(__name__)
app = v23.app

logger.info("IBETIN V22 compatibility entrypoint: launching V23 stable feed")

if __name__ == "__main__":
    app.base.ibetin_start.main()
