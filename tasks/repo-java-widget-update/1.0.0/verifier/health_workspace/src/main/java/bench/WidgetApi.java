package bench;

import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

record Widget(String id, String name, long version) {}
record UpdateRequest(String id, String name, long expectedVersion) {}
record UpdateResponse(int status, Widget widget, String error) {}

final class WidgetRepository {
    enum Status { UPDATED, NOT_FOUND, CONFLICT }
    record Result(Status status, Widget widget) {}
    private final Map<String, Widget> values = new HashMap<>();
    void insert(Widget value) { values.put(value.id(), value); }
    Optional<Widget> find(String id) { return Optional.ofNullable(values.get(id)); }
    Result update(String id, String name, long expected) {
        Widget current = values.get(id);
        if (current == null) return new Result(Status.NOT_FOUND, null);
        if (current.version() != expected) return new Result(Status.CONFLICT, current);
        Widget next = new Widget(id, name, current.version() + 1);
        values.put(id, next);
        return new Result(Status.UPDATED, next);
    }
}

final class WidgetService {
    enum Status { UPDATED, BAD_REQUEST, NOT_FOUND, CONFLICT }
    record Result(Status status, Widget widget, String error) {}
    private final WidgetRepository repository;
    WidgetService(WidgetRepository repository) { this.repository = repository; }
    Result update(UpdateRequest request) {
        if (request == null || request.name() == null || request.name().isBlank()) return new Result(Status.BAD_REQUEST, null, "invalid");
        WidgetRepository.Result result = repository.update(request.id(), request.name().trim(), request.expectedVersion());
        return switch (result.status()) {
            case UPDATED -> new Result(Status.UPDATED, result.widget(), null);
            case NOT_FOUND -> new Result(Status.NOT_FOUND, null, "missing");
            case CONFLICT -> new Result(Status.CONFLICT, result.widget(), "stale");
        };
    }
}

public final class WidgetApi {
    private final WidgetService service;
    WidgetApi(WidgetService service) { this.service = service; }
    UpdateResponse update(UpdateRequest request) {
        WidgetService.Result result = service.update(request);
        int status = switch (result.status()) { case UPDATED -> 200; case BAD_REQUEST -> 400; case NOT_FOUND -> 404; case CONFLICT -> 409; };
        return new UpdateResponse(status, result.widget(), result.error());
    }
}
