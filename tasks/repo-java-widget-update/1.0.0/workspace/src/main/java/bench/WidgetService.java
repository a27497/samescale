package bench;

public final class WidgetService {
    public enum Status { UPDATED, BAD_REQUEST, NOT_FOUND, CONFLICT }
    public record Result(Status status, Widget widget, String error) {}

    private final WidgetRepository repository;

    public WidgetService(WidgetRepository repository) {
        this.repository = repository;
    }

    public Result update(UpdateRequest request) {
        Widget current = repository.find(request.id()).orElse(null);
        if (current == null) {
            return new Result(Status.NOT_FOUND, null, "widget not found");
        }
        WidgetRepository.Result result = repository.update(request.id(), request.name(), current.version());
        return new Result(Status.UPDATED, result.widget(), null);
    }
}
