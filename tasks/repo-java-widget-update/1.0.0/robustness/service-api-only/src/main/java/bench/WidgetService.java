package bench;

public final class WidgetService {
    public enum Status { UPDATED, BAD_REQUEST, NOT_FOUND, CONFLICT }
    public record Result(Status status, Widget widget, String error) {}
    private final WidgetRepository repository;
    public WidgetService(WidgetRepository repository) { this.repository = repository; }
    public Result update(UpdateRequest request) {
        if (request == null || request.name() == null || request.name().isBlank()) return new Result(Status.BAD_REQUEST, null, "invalid");
        WidgetRepository.Result result = repository.update(request.id(), request.name().trim(), request.expectedVersion());
        return switch (result.status()) {
            case UPDATED -> new Result(Status.UPDATED, result.widget(), null);
            case NOT_FOUND -> new Result(Status.NOT_FOUND, null, "missing");
            case CONFLICT -> new Result(Status.CONFLICT, result.widget(), "stale");
        };
    }
}
