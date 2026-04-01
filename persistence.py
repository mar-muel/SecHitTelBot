import logging
import pickle
from pathlib import Path

import controller

logger = logging.getLogger(__name__)


def save_games(path: str):
    if not controller.games:
        # Remove stale file when no games are active
        Path(path).unlink(missing_ok=True)
        return
    with open(path, "wb") as f:
        pickle.dump(controller.games, f)
    logger.info(f"Saved {len(controller.games)} game(s) to {path}")


def load_games(path: str):
    p = Path(path)
    if not p.exists():
        return
    try:
        with open(p, "rb") as f:
            restored = pickle.load(f)
        controller.games.update(restored)
        # Consume the file so it won't be reloaded on a subsequent crash
        p.unlink()
    except Exception:
        logger.exception(f"Failed to load game state from {path}")
        return
    logger.info(f"Restored {len(restored)} game(s) from {path}")
    for session in controller.games.values():
        if session.dateinitvote and session.config.vote_timeout:
            controller._schedule_vote_jobs(session)
            logger.info(f"Rescheduled vote timeout for chat {session.cid}")
