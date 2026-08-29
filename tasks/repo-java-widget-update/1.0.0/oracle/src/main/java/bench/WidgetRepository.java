package bench;

import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

public final class WidgetRepository {
    public enum Status { UPDATED, NOT_FOUND, CONFLICT }
    public record Result(Status status, Widget widget) {}

    private final Map<String, Widget> widgets = new HashMap<>();

    public void insert(Widget widget) {
        widgets.put(widget.id(), widget);
    }

    public Optional<Widget> find(String id) {
        return Optional.ofNullable(widgets.get(id));
    }

    public Result update(String id, String name, long expectedVersion) {
        Widget current = widgets.get(id);
        if (current == null) {
            return new Result(Status.NOT_FOUND, null);
        }
        if (current.version() != expectedVersion) {
            return new Result(Status.CONFLICT, current);
        }
        Widget updated = new Widget(id, name, current.version() + 1);
        widgets.put(id, updated);
        return new Result(Status.UPDATED, updated);
    }
}
