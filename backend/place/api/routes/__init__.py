"""Route registry. app.create_app includes everything in `all_routers`."""

from __future__ import annotations

from place.api.routes import (
    admin,
    auth,
    events,
    feed,
    places,
    push,
    saves,
    trips,
    verdicts,
)

all_routers = [
    feed.router,
    places.router,
    saves.router,
    trips.router,
    verdicts.router,
    auth.router,
    push.router,
    events.router,
    admin.router,
]
