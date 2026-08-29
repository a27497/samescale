# Widget update contract

`WidgetApi.update(UpdateRequest)` maps validation to 400, missing records to 404, stale versions
to 409, and successful durable updates to 200. Versions begin at 1 and increment per update.
